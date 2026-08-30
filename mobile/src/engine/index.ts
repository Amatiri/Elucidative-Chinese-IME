/**
 * 引擎门面。UI 层只依赖这里，不直接碰内部模块。
 *
 * 全部为纯函数：零 DOM、零 I/O、零全局可变状态。这是将来对齐 Kotlin 的前提 ——
 * 同样的输入输出契约，可以直接照着写 Kotlin data class + object。
 */

import { loadDataset } from "./dataset.ts";
import { queryByPrefix, queryPhrase } from "./query.ts";
import { splitSequence } from "./split.ts";
import { getPhraseSegments, queryMultiChars, querySingleChar } from "./compose.ts";
import { processInput } from "./process.ts";
import { groupByClass, nextCharClass } from "./charclass.ts";
import type { CharClass } from "./charclass.ts";
import type { Candidate, Dataset, PhraseSegments } from "./types.ts";

export interface Engine {
  readonly dataset: Dataset;
  /** 结构化候选。UI 层用这个，不要用 legacy 拼串 */
  queryByPrefix(prefix: string, startIdx?: number, count?: number): Candidate[];
  /** '/'-连接的拼串形态，兼容桌面端显示格式 */
  querySingleChar(splitText: string, startIdx?: number, count?: number): string;
  /** 多字预览串 */
  queryMultiChars(splitText: string): string;
  /** 编码 → 词语，带括号 */
  queryPhrase(code: string): string;
  /** 自动分词 */
  splitSequence(original: string): string;
  /** 段解析 → (预览, 部件列表, 字面下标) */
  getPhraseSegments(processed: string): PhraseSegments;
  /** 从输入流提取合法编码串 */
  processInput(text: string): string;
  /**
   * 下一键分档：content（有内容）/ empty（无候选）。**运行时只有这两档**。
   *
   * 没有「禁用」档：无候选时按 ime.py 语义直出原编码（不拒绝输入），
   * 所以 UI 不得把 empty 画成不可点 —— 空码区是规则 §六 的可用扩展面
   * （预留区 / 音区疏散 / 用户自定义），被误判成禁用会砍掉这个特性。
   * 键帽一律可点，只做灰显提示。
   */
  nextCharClass(prefix: string): Map<string, CharClass>;
  /** 同上，按档位分组，方便直接套样式 */
  groupByClass(prefix: string): Record<CharClass, string[]>;
}

export function createEngine(ds: Dataset = loadDataset()): Engine {
  return {
    dataset: ds,
    queryByPrefix: (p, s = 0, c = 5) => queryByPrefix(ds, p, s, c),
    querySingleChar: (t, s = 0, c = 5) => querySingleChar(ds, t, s, c),
    queryMultiChars: (t) => queryMultiChars(ds, t),
    queryPhrase: (code) => queryPhrase(ds, code),
    splitSequence,
    getPhraseSegments: (p) => getPhraseSegments(ds, p),
    processInput,
    nextCharClass: (p) => nextCharClass(ds, p),
    groupByClass: (p) => groupByClass(ds, p),
  };
}

// ── 类型与工具再导出，方便 UI 层 ──
export type {
  Candidate,
  CandidateKind,
  Dataset,
  Entry,
  PhraseSegments,
} from "./types.ts";
// RawDataset 由构建脚本生成，定义在 data/dataset.ts
export type { RawDataset } from "../data/dataset.ts";
export { toLegacy } from "./types.ts";
export { CODE_CHARS, SELECTION_SYMBOLS, isAsciiDigit, isCodeChar } from "./constants.ts";
export { loadDataset, datasetFromEntries } from "./dataset.ts";
export { MAX_SPLIT_ITERATIONS } from "./split.ts";
export type { CharClass } from "./charclass.ts";
export { nextCharClass, groupByClass } from "./charclass.ts";
