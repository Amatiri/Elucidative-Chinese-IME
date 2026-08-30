/**
 * 引擎数据结构。全部为纯数据，不含行为，便于将来直接映射到 Kotlin data class。
 */

/**
 * query_by_prefix 的命中分支。
 * 用于 L4 分支覆盖率断言 —— 尤其 supaA，现码表命中 0 条，只能靠合成用例覆盖。
 */
export type CandidateKind =
  /** 普通前缀命中（Python L71-84 的无补码路径） */
  | "plain"
  /** 补码：prefix 自身已含 '.'（Python L74-76） */
  | "bumaDot"
  /** 补码：code[5]=='.' 或 prefix 第 4 位是数字（Python L77-81） */
  | "bumaCode5"
  /** 副码 a 特殊分支（Python L64-70） */
  | "supaA";

export interface Candidate {
  /** 候选字。必须是完整 word —— 152 条非 BMP 字是 UTF-16 代理对，禁止按下标截取 */
  text: string;
  /** 该候选的完整编码 */
  code: string;
  /** 输入前缀之后的剩余编码，可能为空串 */
  rest: string;
  /** 用户已输入的前缀 */
  typed: string;
  /** 命中哪个分支，供覆盖率断言 */
  kind: CandidateKind;
  /** dictionary.txt 中的行号（0-based），候选顺序的唯一依据 */
  lineNo: number;
}

/**
 * 还原成 Python 端的拼串形态（"疤b" = word + rest）。
 * 仅用于与 Python 逐字节比对，业务代码请用结构化字段。
 */
export function toLegacy(c: Candidate): string {
  return c.text + c.rest;
}

export interface Entry {
  word: string;
  code: string;
  /** dictionary.txt 行号（0-based） */
  lineNo: number;
}

export interface Dataset {
  version: number;
  entryCount: number;
  phraseCount: number;
  codeCount: number;
  nonBmpCount: number;
  sourceSha: string;
  /**
   * 按 dictionary.txt 行序。这是候选顺序的唯一依据（首字置顶 + sort_key 码值序
   * 已由 file_processor 排好），**引擎任何地方都不得排序**。
   */
  entries: readonly Entry[];
  /** 首字母桶，桶内保持行序 */
  buckets: ReadonlyMap<string, Entry[]>;
  /** 编码 → 词语。ciyu.txt 的 2003 个编码全唯一，故 1:1 */
  phraseIndex: ReadonlyMap<string, string>;
}

/** get_phrase_segments 的返回结构 */
export interface PhraseSegments {
  /** 预览显示文本（词语、首选字组合或编码原文） */
  display: string;
  /** 展平后的部件列表，供逐字选择 */
  allParts: string[];
  /** 无候选、按编码原文字面输出的部件下标（升序） */
  literalIndices: number[];
}
