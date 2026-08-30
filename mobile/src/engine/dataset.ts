/**
 * 数据集加载。零 I/O —— 数据已由 tools/build_dataset.py 内联进 TS 常量。
 * 移动端 assets 只读，mtime 缓存必然失效，所以构造时一次性建索引，永不碰文件系统。
 */

import { DATASET, type RawDataset } from "../data/dataset.ts";
import { isCodeChar } from "./constants.ts";
import type { Dataset, Entry } from "./types.ts";

/**
 * 解析 flat 串 "字码,字码,..."。
 *
 * 每项**从尾部向前扫描**：连续属于 CODE_CHARS 的部分是 code，剩余前缀是 word。
 * 这样即使 word 是非 BMP 字符（152 条，UTF-16 代理对）也不会错位 ——
 * 代理对的任一码元都不在 CODE_CHARS 里，扫描会正确停在它之后。
 *
 * 与 Python tools/build_dataset.py#decode_flat 逐行等价。
 */
export function parseEntries(flat: string): Entry[] {
  const out: Entry[] = [];
  let lineNo = 0;
  for (const item of flat.split(",")) {
    if (item.length === 0) continue;
    let i = item.length;
    while (i > 0 && isCodeChar(item[i - 1]!)) i--;
    out.push({ word: item.slice(0, i), code: item.slice(i), lineNo: lineNo++ });
  }
  return out;
}

/**
 * 建首字母桶。与 Python _get_index（dictionary_frontend.py:36-44）等价：
 * setdefault(code[0], []).append(...)，桶内保持文件原顺序 —— 这是候选顺序的关键。
 */
export function buildBuckets(entries: readonly Entry[]): Map<string, Entry[]> {
  const buckets = new Map<string, Entry[]>();
  for (const e of entries) {
    const key = e.code[0]!;
    let arr = buckets.get(key);
    if (arr === undefined) {
      arr = [];
      buckets.set(key, arr);
    }
    arr.push(e);
  }
  return buckets;
}

/** 从 RawDataset 构造引擎可用的 Dataset。默认用内联的 DATASET。 */
export function loadDataset(raw: RawDataset = DATASET): Dataset {
  const entries = parseEntries(raw.entries);
  if (entries.length !== raw.entryCount) {
    throw new Error(
      `flat 解析条目数不符：解析得 ${entries.length}，声明 ${raw.entryCount}`,
    );
  }
  const phraseIndex = new Map<string, string>(Object.entries(raw.phraseIndex));
  if (phraseIndex.size !== raw.codeCount) {
    throw new Error(
      `phraseIndex 条目数不符：解析得 ${phraseIndex.size}，声明 ${raw.codeCount}`,
    );
  }
  return {
    version: raw.version,
    entryCount: raw.entryCount,
    phraseCount: raw.phraseCount,
    codeCount: raw.codeCount,
    nonBmpCount: raw.nonBmpCount,
    sourceSha: raw.sourceSha,
    entries,
    buckets: buildBuckets(entries),
    phraseIndex,
  };
}

/**
 * 用自定义条目构造 Dataset —— 供副码 a 合成用例使用。
 *
 * 该分支在真实码表上命中 0 条（prefix 第 5 位为 'a'），不造虚拟条目就永远无法覆盖。
 */
export function datasetFromEntries(
  entries: readonly Entry[],
  phraseIndex: ReadonlyMap<string, string> = new Map(),
): Dataset {
  return {
    version: 0,
    entryCount: entries.length,
    phraseCount: 0,
    codeCount: phraseIndex.size,
    nonBmpCount: entries.filter((e) => e.word.codePointAt(0)! > 0xffff).length,
    sourceSha: "synthetic",
    entries,
    buckets: buildBuckets(entries),
    phraseIndex,
  };
}
