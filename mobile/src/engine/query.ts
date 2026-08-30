/**
 * 前缀查询 —— 整个引擎的核心，也是最容易译错的一处。
 *
 * 与 Python dictionary_frontend.py:53-88 query_by_prefix 逐行等价。
 * 每处硬编码下标都标注了 Python 原行号。改任何一处前请先跑 Golden 夹具。
 */

import { isAsciiDigit } from "./constants.ts";
import type { Candidate, CandidateKind, Dataset, Entry } from "./types.ts";

function mk(
  entry: Entry,
  typed: string,
  rest: string,
  kind: CandidateKind,
): Candidate {
  return {
    text: entry.word, // 完整 word —— 152 条非 BMP 字是代理对，不可按下标截取
    code: entry.code,
    rest,
    typed,
    kind,
    lineNo: entry.lineNo,
  };
}

/**
 * 按编码前缀查候选。返回顺序 = dictionary.txt 行序（首字置顶 + sort_key 已排好），
 * 引擎内**任何地方都不得排序**。
 */
export function queryByPrefix(
  ds: Dataset,
  prefix: string,
  startIdx = 0,
  count = 5,
): Candidate[] {
  // L54-55：空前缀直接返回空
  if (prefix.length === 0) return [];

  // L57-59：取首字母桶；桶不存在返回空
  const bucket = ds.buckets.get(prefix[0]!);
  if (bucket === undefined) return [];

  // L60：收满 startIdx + count 个即可提前终止
  const need = startIdx + count;
  const results: Candidate[] = [];

  for (const e of bucket) {
    const code = e.code;

    // L64：副码 a 特殊规则。判的是 **prefix 第 5 位**，不是 code 的第 5 位。
    // 真实码表里 code[4]=='a' 命中 0 条，但那与这个分支无关 —— 用户只要输入
    // 第 5 位是 'a' 的串就会进来，故这不是死代码。
    if (prefix.length >= 5 && prefix[4] === "a") {
      // L65-66：prefix 正好 5 位且 code 等于其前 4 位 → 唯一不带 rest 的分支
      if (prefix.length === 5 && code === prefix.slice(0, 4)) {
        results.push(mk(e, prefix, "", "supaA"));
      } else if (code.length >= 5 && code.startsWith(prefix.slice(0, 4))) {
        // L68：code[4:] 以 prefix[5:] 开头（len(prefix)==5 时后者为空串，恒真）
        if (code.slice(4).startsWith(prefix.slice(5)) && code[4] === ".") {
          // L69：全函数唯一的 -1 —— 语义是「把 '.' 本身留在 rest 里」，
          // 抄成 slice(prefix.length) 会静默少一个字符。
          results.push(mk(e, prefix, code.slice(prefix.length - 1), "supaA"));
        }
      }
    } else if (code.startsWith(prefix)) {
      // L73：code 前 6 位内是否含 '.'
      if (code.slice(0, 6).indexOf(".") !== -1) {
        if (prefix.indexOf(".") !== -1) {
          // L74-76：prefix 自己就带 '.' → 直接切剩余
          results.push(mk(e, prefix, code.slice(prefix.length), "bumaDot"));
        } else if (
          // L77：复合条件，两项顺序与短路不可互换
          (code.length > 5 && code[5] === ".") ||
          (prefix.length === 4 && isAsciiDigit(prefix[3]!))
        ) {
          // L78：取第一个 '.' 之前的全部
          const codeBeforeDot = code.split(".")[0]!;
          // L79-81：prefix 必须正好等于 '.' 前的部分
          if (prefix === codeBeforeDot) {
            results.push(mk(e, prefix, code.slice(prefix.length), "bumaCode5"));
          }
        }
      } else {
        // L82-84：普通命中
        results.push(mk(e, prefix, code.slice(prefix.length), "plain"));
      }
    }

    // L86：提前终止。**在 if/elif 之外**，每轮循环都要检查 ——
    // 移进 elif 会改变 startIdx > 0 时的截断行为。
    if (results.length >= need) break;
  }

  // L88
  return results.slice(startIdx, startIdx + count);
}

/**
 * 词语查询：编码 → 词语。O(1)。
 *
 * 替代 Python L7-18 的「每次调用重新打开 ciyu.txt 全扫 1939 行」。
 * 2003 个编码全唯一（已验证），故正向索引与「顺序扫描取首个匹配」等价。
 *
 * 返回值保留括号 —— 这是与上层 getPhraseSegments 的协议的一部分。
 *
 * 已知偏差：Python 原版对 code="" 会因 split 产生空字段而命中首行；
 * 本实现返回 ""。夹具不含该用例（见 golden meta.deviations）。
 */
export function queryPhrase(ds: Dataset, code: string): string {
  const c = code.split(" ").join(""); // 对应 Python L9 去掉所有空格
  const p = ds.phraseIndex.get(c);
  return p === undefined ? "" : "(" + p + ")";
}
