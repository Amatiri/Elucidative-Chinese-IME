/**
 * 键位分档 —— **运行时只有两档**。
 *
 * 【2026-08-30 修正 · 依据 Amatiri 反馈与 ime.py 实测】
 * 旧实现分三档，第三档 forbidden 来自「规则文本明文禁止某位出现某字符」。
 * 但对照 ime.py 的真实行为：
 *   - ime.py:327-330  query_single_char 无候选 → 直出原编码，不拒绝
 *   - ime.py:721      空闲态（无编码字符）时 '.' 不被拦截，由系统直接输出
 *   - ime.py:777-780  其它非法字符 → 清空输入、保留原编码
 * 也就是说运行时的判定只有「有候选 / 无候选」，两条路都不会拦住用户按键。
 * 再单独维护一档「规则禁用」既无行为差异，又会给 UI 一个错误的拒绝信号
 * （把空码区画成禁用 = 砍掉规则 §六 的「可自定义」特性）。
 *
 * 因此现在只有两档：
 *   content  有内容 —— 查得到候选。键帽常态/强调，可点
 *   empty    无内容 —— 查不到候选。灰显但**仍可点**，按下后按 ime.py 语义
 *                      直出原编码，不抖动、不吞键
 *
 * 规则文本里的「禁用」知识不再参与运行时判定，但以 ruleForbiddenAt() 保留，
 * 供设计稿真值表与文档校验使用 —— 真值表对理解编码结构有帮助，予以保留。
 */

import { CODE_CHARS } from "./constants.ts";
import { getPhraseSegments } from "./compose.ts";
import { splitSequence } from "./split.ts";
import type { Dataset } from "./types.ts";

export type CharClass = "content" | "empty";

const DIGITS = "0123456789";

/**
 * 各「段内位置」上规则明文不允许的字符。**仅用于文档/真值表，不参与运行时判定。**
 *
 * 位置是**段内偏移**（最后一个 ' 之后的长度），不是整串长度 ——
 * 多字模式下 bab → ba'b，第 3 个字符其实是新段的第 1 位。
 *
 * 关于第 5 位（副码）与第 6/7 位（引导符 / 补码）的口径，见文件末 note。
 */
export function ruleForbiddenAt(posInSeg: number): string {
  switch (posInSeg) {
    // 第 1 位 声母：§二 零声母 a/o/e 统一归 o，故 a、e 不作声母。
    // 数字 / ; / ' / . 在段首均无意义。
    case 0:
      return "ae" + DIGITS + ";'.";
    // 第 2 位 韵母：; = ing（合法），' = 手动分段（合法）。
    case 1:
      return DIGITS + ".";
    // 第 3 位 声调：数字全部合法（含空码区 5-9，§六 声调缺失区）；
    // 字母会切段，由 effectivePos 改按段首规则判。
    case 2:
      return ".;";
    // 第 4 位 主码：§三.4 明文「禁用：a、e、; 不用于主码」。
    case 3:
      return "ae;.";
    // 第 5 位 副码：§四 副码只取字母。**'.' 不在此列** —— 它出现在这个位置
    // 时不是副码，而是补码引导符提前（副码省略），见文件末 note。
    case 4:
      return DIGITS;
    // 第 6/7 位 引导与补码：.F 的 F 恒为字母。
    default:
      return DIGITS;
  }
}

/** 按 ' 切分后最后一段的长度 = 下一个字符将落在的段内位置 */
function segOffset(code: string): number {
  if (code === "") return 0;
  const parts = splitSequence(code).split("'");
  return parts[parts.length - 1].length;
}

/** 该前缀下是否真能产出内容（走引擎实跑，与 query 行为一致，不猜） */
function hasOutput(ds: Dataset, code: string): boolean {
  const { display, allParts, literalIndices } = getPhraseSegments(ds, splitSequence(code));
  if (allParts.length === 0) return Boolean(display);
  // 全部部件都只是字面回显编码原文 = 无候选
  if (literalIndices.length >= allParts.length) return false;
  return true;
}

/**
 * 给定已输入前缀，返回下一键每个字符的分档。覆盖 CODE_CHARS 全集。
 *
 * 返回值只有 content / empty 两种 —— 没有任何字符会被判为「不可点」。
 *
 * @param ds     数据集
 * @param prefix 已输入的编码串
 */
export function nextCharClass(ds: Dataset, prefix: string): Map<string, CharClass> {
  const result = new Map<string, CharClass>();

  for (const ch of CODE_CHARS) {
    const next = prefix + ch;
    result.set(ch, hasOutput(ds, next) ? "content" : "empty");
  }

  return result;
}

/** 便捷：按档位分组，供 UI 直接套样式 */
export function groupByClass(ds: Dataset, prefix: string): Record<CharClass, string[]> {
  const map = nextCharClass(ds, prefix);
  const out: Record<CharClass, string[]> = { content: [], empty: [] };
  for (const [ch, cls] of map) out[cls].push(ch);
  return out;
}

/**
 * note · 三个容易搞混的口径（2026-08-30 修正，依据 Amatiri 反馈）
 *
 * 1. 副码 a 是「占空码」，既不是空码区也不是禁用。
 *    规则 §四「副码省略原则」：最常用字没有副码；为统一码长需要占位时使用 a，
 *    **在码表中省略不写**。所以第 5 位 a 实测 0 条，但用户输入 a 完全合法 ——
 *    引擎 queryByPrefix 的 prefix[4]==='a' 分支正是这条规则（命中 6184 次）。
 *
 * 2. 出现在第 5 位的 '.' 不是副码，是补码**引导符**。
 *    副码与补码都可省略，所以主码后一旦出现编码，无法区分它是副码还是补码。
 *    解决办法是用 '.' 作引导符：引导符之前（或没有引导符）为副码，之后为补码。
 *    因此「第 5 位出现 '.'」的字 = 没有副码（a 占位且省略）+ 有补码引导，
 *    在统计上必须归到第 6 位引导，不能记进副码。码表实测 234 条
 *    （131 条止于引导符 + 103 条引导符后带 F）。
 *
 * 3. 第 6 位出现的字母，逻辑上是第 7 位补码 F。
 *    因为第 5 位副码省略造成整串左移一位。码表实测 103 条（形式 ABCD.F）。
 *
 * 位序对照（逻辑位 → 物理位置）：
 *    ABCD        → 4 位（5935 条）
 *    ABCDE       → 5 位（1908 条）
 *    ABCD.       → 5 位（131 条，无副码，F 省略）
 *    ABCD.F      → 6 位（103 条，无副码；F 落在物理第 6 位）
 *    ABCDE.      → 6 位（31 条，有副码，F 省略）
 *    ABCDE.F     → 7 位（44 条）
 */
