/**
 * 组合层：在 queryByPrefix / queryPhrase / splitSequence 之上组装出
 * 上屏需要的各种视图。
 *
 * 与 Python dictionary_frontend.py 的
 *   query_single_char(L174) / query_multi_chars(L186) / get_phrase_segments(L204)
 * 逐行等价。
 */

import { queryByPrefix, queryPhrase } from "./query.ts";
import { splitSequence } from "./split.ts";
import { toLegacy, type Dataset, type PhraseSegments } from "./types.ts";

/**
 * 取字符串的首个**码点**。
 *
 * 对应 Python 的 s[0]。JS 的 s[0] 取的是首个 UTF-16 码元 —— 对 152 条非 BMP 字
 * （代理对）会拿到孤立的高位代理项。所有"取首字"的地方都必须走这里。
 */
function firstCodePoint(s: string): string {
  return [...s][0] ?? "";
}

/**
 * 单字候选，返回 '/'-连接的拼串（与 Python 完全一致的 legacy 形态）。
 *
 * 保留这个形态是为了与 Python 逐字节比对；UI 层请用 queryByPrefix 拿结构化结果。
 */
export function querySingleChar(
  ds: Dataset,
  splitText: string,
  startIdx = 0,
  count = 5,
): string {
  const candidates = queryByPrefix(ds, splitText, startIdx, count);
  return candidates.length > 0 ? candidates.map(toLegacy).join("/") : "";
}

/**
 * 多字预览：把各部件的首选字拼成串。任一部件无候选则返回空串。
 */
export function queryMultiChars(ds: Dataset, splitText: string): string {
  const charCodes = splitText.split("'");
  let firstChars = "";
  for (const code of charCodes) {
    if (code.length === 0) continue;
    const candidates = queryByPrefix(ds, code, 0, 1);
    if (candidates.length > 0) {
      // 对应 Python L198 candidates[0][0] —— 取首个候选的首个码点
      firstChars += firstCodePoint(candidates[0]!.text);
    } else {
      return "";
    }
  }
  return firstChars;
}

/**
 * 解析手动 ' 分隔的各段，产出 (预览文本, 展平部件列表, 字面输出下标集合)。
 *
 * 优先级：词语命中 > 单字预览 > 字面输出编码原文。
 */
export function getPhraseSegments(
  ds: Dataset,
  processed: string,
): PhraseSegments {
  const segments = processed.split("'");
  const partsList: string[][] = [];
  const displayParts: string[] = [];
  const literalIndices = new Set<number>();
  let flatIdx = 0; // 当前段在展平部件列表中的起始下标

  for (const seg of segments) {
    if (seg.length === 0) continue; // L217-218：空段跳过，且不递增 flatIdx

    if (seg.length < 3) {
      // L219：阈值是 3，与 split_sequence 的 condition1 阈值 2 不同
      const char = queryByPrefix(ds, seg, 0, 1);
      if (char.length > 0) {
        displayParts.push(firstCodePoint(char[0]!.text)); // L222
        partsList.push([seg]);
      } else {
        displayParts.push(seg);
        partsList.push([seg]);
        literalIndices.add(flatIdx);
      }
    } else {
      // L230：词语路径优先于单字
      const phrase = queryPhrase(ds, seg);
      if (phrase !== "") {
        displayParts.push(phrase.slice(1, -1)); // L232：剥掉括号
        // L234：词语命中时仍需自动拆分，供逐字选择
        const splitSeg = splitSequence(seg);
        partsList.push(splitSeg.split("'"));
      } else {
        const splitSeg = splitSequence(seg);
        const chars = queryMultiChars(ds, splitSeg);
        if (chars !== "") {
          displayParts.push(chars);
          partsList.push(splitSeg.split("'"));
        } else {
          displayParts.push(seg);
          partsList.push([seg]);
          literalIndices.add(flatIdx);
        }
      }
    }
    // L247：累加的是**该段展平后的部件数**，不是 1
    flatIdx += partsList[partsList.length - 1]!.length;
  }

  const allParts: string[] = [];
  for (const group of partsList) {
    allParts.push(...group);
  }

  return {
    display: displayParts.join(""),
    allParts,
    // Python 侧是 set，JSON 化统一为升序数组
    literalIndices: [...literalIndices].sort((a, b) => a - b),
  };
}
