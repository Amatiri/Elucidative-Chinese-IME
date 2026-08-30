/**
 * 视图模型：把引擎输出整理成渲染层直接可用的形状。
 *
 * 【显示分区口径 · 对齐 ime.py 外输模式 update_display()】
 *   - 目标输入框（上方大区）：已上屏文本 + 正在输入的编码（下划线）。
 *   - 左上角小显示区：**只显示最后输入的那一个字符**；空闲态让位给大小写档位（小/大/连）。
 *   - 中间候选区：单字态显示单字候选；**进入多字态后不再显示单字候选**，
 *     改为显示多字预览串 + 词语（ime.py 的 first_chars_label）。
 *
 * 单字 / 多字的判定依据是 splitSequence 自动分词后的段数，不是原始串长度。
 */

import type { Candidate, CharClass, Engine } from "../engine/index.ts";
import type { KeyboardState } from "./types.ts";

export type QueryMode = "idle" | "single" | "multi";

export interface ViewModel {
  /** processInput 之后的合法编码串 */
  code: string;
  /** 自动分词后的部件列表 */
  parts: string[];
  mode: QueryMode;
  /** 最后输入的字符，供左上角小显示区 */
  lastChar: string;
  /** 当前应显示的候选。多字态且未进入逐字选择时为空 */
  candidates: Candidate[];
  /** 多字预览串（已含逐字选择的结果） */
  preview: string;
  /** 词语原文（含括号）。与预览重复时或走增强预览时为空串 */
  phrase: string;
  /** 词语内容（不含括号），供「!」直接上屏词语 */
  phraseContent: string;
  /** 字面部件（无候选、按编码原样输出）的下标，逐字选择时应跳过 */
  literalIndices: readonly number[];
  /** 上屏目标文本 */
  display: string;
  /** 下一键分档，覆盖 CODE_CHARS 全集 */
  keyClass: Map<string, CharClass>;
  hasNextPage: boolean;
  /** 是否处于编码态 */
  coding: boolean;
  /** 是否处于逐字选择态 */
  selecting: boolean;
  /** 逐字选择的当前部件下标 */
  currentPart: number | null;
  /** 部件总数（排除字面部件） */
  partCount: number;
  /** 页码文案，如「页 2」「字 1/2 页 1」 */
  pageLabel: string;
}

const PAGE_SIZE = 5;

/**
 * 按部件重建预览串。
 *
 * 字面部件（无候选，按编码原样回显）在预览串里占 len(part) 个字符，
 * 其余部件恰好占 1 个字符 —— 这是 ime.py update_display L288-295 的对齐关系，
 * 直接按 parts.length 下标取字会在存在字面部件时错位。
 */
function rebuildPreview(
  base: string,
  allParts: readonly string[],
  literalIndices: readonly number[],
  resolved: Readonly<Record<number, string>>,
): string {
  const literal = new Set(literalIndices);
  let out = "";
  let pos = 0;
  for (let i = 0; i < allParts.length; i++) {
    const part = allParts[i]!;
    const width = literal.has(i) ? part.length : 1;
    const picked = resolved[i];
    if (picked !== undefined) {
      out += picked;
    } else {
      out += base.slice(pos, pos + width);
    }
    pos += width;
  }
  return out || base;
}

export function buildView(engine: Engine, st: KeyboardState): ViewModel {
  const code = engine.processInput(st.buffer);
  const split = engine.splitSequence(code);
  const parts = split.split("'").filter((p) => p.length > 0);

  const seg = engine.getPhraseSegments(code);
  /**
   * ime.py L527-534 有两条分支，不能合并：
   *
   *   手动单引号 + 优先上词 → **词语增强预览**：预览串直接取 getPhraseSegments().display
   *     （词语优先，无候选的字面段按编码原文参与），此时**不再单列词语**。
   *   其余情况 → 预览串 = 各段首选字拼串（queryMultiChars），词语单独成项，
   *     并排显示为「厕是   (测试)」。
   *
   * 混用会丢信息：只用 display 会让非手动分段的输入丢掉逐字预览「厕是」；
   * 只用 queryMultiChars 则手动分段时拿不到词语增强。
   */
  const enhanced = code.includes("'") && st.settings.phrasePriority;
  const firstCharsRaw = parts.length > 1 && !enhanced ? engine.queryMultiChars(split) : "";
  const basePreview = enhanced ? seg.display : firstCharsRaw;

  const preview =
    parts.length > 1
      ? rebuildPreview(basePreview, seg.allParts, seg.literalIndices, st.resolved)
      : seg.display;

  const rawPhrase = enhanced ? "" : engine.queryPhrase(code);
  const phraseContent = rawPhrase.slice(1, -1);
  // ime.py L301-306：词语与预览内容相同时只显示一个，避免重复
  const phrase = phraseContent === preview ? "" : rawPhrase;

  const keyClass = engine.nextCharClass(code);
  const coding = code.length > 0;
  const mode: QueryMode = !coding ? "idle" : parts.length > 1 ? "multi" : "single";

  const literalCount = seg.literalIndices.length;
  const partCount = Math.max(0, seg.allParts.length - literalCount);

  // ── 逐字选择：仅在多字态下有意义 ──
  const selecting = mode === "multi" && st.partIndex !== null;
  const currentPart =
    selecting && st.partIndex !== null && st.partIndex < parts.length ? st.partIndex : null;

  // 单字态查首段；多字态进入逐字选择后查当前部件；否则不显示单字候选
  const queryTarget = mode === "single" ? parts[0] ?? "" : currentPart !== null ? parts[currentPart]! : "";
  const showCandidates = mode === "single" || currentPart !== null;

  const start = st.page * PAGE_SIZE;
  const candidates = showCandidates ? engine.queryByPrefix(queryTarget, start, PAGE_SIZE) : [];
  const hasNextPage =
    showCandidates && queryTarget.length > 0 && engine.queryByPrefix(queryTarget, start + PAGE_SIZE, PAGE_SIZE).length > 0;

  // 上屏目标：优先上词开启且有词语时用词语内容，否则用逐字预览串
  const display =
    mode === "multi"
      ? st.settings.phrasePriority && phraseContent.length > 0
        ? phraseContent
        : preview
      : (candidates[0]?.text ?? "");

  const pageLabel = buildPageLabel(st, mode, selecting, currentPart, partCount, hasNextPage, start);

  return {
    code,
    parts,
    mode,
    // 取最后按下的键，不是编码末字符 —— 中间插入时两者不同（见 types.ts lastTap）
    lastChar: st.lastTap,
    candidates,
    preview,
    phrase,
    phraseContent,
    literalIndices: seg.literalIndices,
    display,
    keyClass,
    hasNextPage,
    coding,
    selecting,
    currentPart,
    partCount,
    pageLabel,
  };
}

function buildPageLabel(
  st: KeyboardState,
  mode: QueryMode,
  selecting: boolean,
  currentPart: number | null,
  partCount: number,
  hasNextPage: boolean,
  start: number,
): string {
  if (mode === "idle") return "";
  const page = start / PAGE_SIZE + 1;
  // 首页且无下一页时不显示页码，避免常态下的视觉噪音
  const showPage = page > 1 || hasNextPage;
  if (selecting && currentPart !== null) {
    const done = Object.keys(st.resolved).length;
    return `字 ${currentPart + 1}/${partCount}${showPage ? ` 页 ${page}` : ""}`;
  }
  if (mode === "multi") return "";
  return showPage ? `页 ${page}` : "";
}
