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
  /**
   * 逐字选择的**部件空间**。下标与 literalIndices / partCount / st.resolved 同源。
   *
   * ⚠ 不等于 parts：手动分段且优先上词时，部件来自 getPhraseSegments 的展平结果
   * （词语段会被再拆分、无候选段整段作字面段），与「对整串做自动分词」的 parts
   * 是两套下标空间。混用会让序号与候选整体错位（deepseek'mox; 曾显示「字 3/2」）。
   */
  partSpace: string[];
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
  /**
   * 是否允许进入逐字选择。
   *
   * 对齐 ime.py:313 的 `if first_chars and ...` 守卫：逐字首选串为空（= 编码里有
   * 至少一段不对应任何候选，如 deepseek → de'ep'se'ek，ep/ek 无候选）时，
   * 桌面端根本不会进逐字选择，也不会显示「字 N/M」。手机上若放行，就会出现
   * 「字 2/0」—— 分母算自字面段、分子算自另一套下标。
   */
  canSelect: boolean;
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
 * 字面部件（无候选，按编码原样回显）在预览串里占 len(part) 个**码点**，
 * 其余部件恰好占 1 个**码点** —— 这是 ime.py update_display L288-296 的对齐关系，
 * 直接按 parts.length 下标取字会在存在字面部件时错位。
 *
 * ⚠ 必须按码点切，不能按 UTF-16 码元切。152 条非 BMP 字（如 𬇕 U+2C7D5）是代理对，
 * `base.slice(pos, pos + 1)` 只会切到半个字，且每出现一个非 BMP 字，后面所有部件
 * 就整体错位一格 —— 多字预览会丢字，或拼出孤立代理项。
 * Python 的 `first_chars[pos]` 天然按码点，这是 TS 移植特有的偏差。
 */
function rebuildPreview(
  base: string,
  allParts: readonly string[],
  literalIndices: readonly number[],
  resolved: Readonly<Record<number, string>>,
): string {
  const literal = new Set(literalIndices);
  const cps = [...base];
  let out = "";
  let pos = 0;
  for (let i = 0; i < allParts.length; i++) {
    const part = allParts[i]!;
    // 字面部件按编码原文占 len(part) 个码点（编码是 ASCII，码元数 = 码点数）
    const width = literal.has(i) ? part.length : 1;
    const picked = resolved[i];
    if (picked !== undefined) {
      out += picked;
    } else {
      out += cps.slice(pos, pos + width).join("");
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
   * ime.py L544-556 的两条分支决定**两套不同的部件空间**，不能合并：
   *
   *   手动单引号 + 优先上词 → _apply_phrase_result(get_phrase_segments(processed))：
   *     split_parts = seg.allParts（词语段再拆分、无候选段整段作字面段），
   *     literal_indices 记载字面段，首选项 = seg.display（词语增强预览）。
   *   其余 → split_parts = 自动分词结果，first_chars = query_multi_chars(split)，
   *     literal_indices 为空（这一支里每一段都必定有候选，否则 first_chars 为空）。
   *
   * 2026-09-01 修复：原先逐字选择在 `parts`（整串自动分词）上导航，而 partCount /
   * literalIndices 取自 seg —— deepseek'mox; 因此出现「字 2/2 / 字 3/2 / 字 4/2」，
   * 且候选查的是 ep / se 而不是 mo / x;。
   */
  const enhanced = code.includes("'") && st.settings.phrasePriority;
  const partSpace: string[] = enhanced ? [...seg.allParts] : parts;
  const literalIndices: readonly number[] = enhanced ? seg.literalIndices : [];
  const literalSet = new Set(literalIndices);

  /**
   * 所有**非字面**部件是否都有候选。
   *
   * 这是能否进入逐字选择的判据：任一可选的部件无候选，逐字选择就无从选起，
   * 桌面端禁止进入（用户拍板，2026-09-01）。字面段（无候选、按编码原文输出）
   * 本就不参与选择，不计入此判断。
   *
   * 例：
   *   deepseek（部件 de/ep/se/ek，ep/ek 无候选）→ false，禁止进入；
   *   deepseek'mox;（部件 deepseek(字面)/mo/x;，mo/x; 都有候选）→ true，允许进入；
   *   ceu'jihw（ce/u/ji/hw 都有候选）→ true。
   */
  const allPartsSelectable: boolean = (() => {
    for (let i = 0; i < partSpace.length; i++) {
      if (literalSet.has(i)) continue;
      if (engine.queryByPrefix(partSpace[i]!, 0, 1).length === 0) return false;
    }
    return true;
  })();

  /**
   * 逐字首选串：对部件空间逐段取「首候选的首个码点」，无候选段保留编码原文。
   *
   * 对齐 ime.py navigate_parts entered_selection 分支（L211-217）的逐段重建口径，
   * 进入逐字选择后把每个可选的部件换成它自己的首候选字。
   * 能进入选择（allPartsSelectable）时，非字面段必有候选，回退只发生在字面段
   * （本就按编码原文输出）。
   *
   * 例：ceu'jihw → 「厕是几花」（而非词语「测试计划」）；
   *     deepseek'mox; → [deepseek(字面),mo,x;] → 「deepseek摸兴」（而非「deepseek模型」）。
   */
  const perPartFirst: string = (() => {
    let out = "";
    for (const part of partSpace) {
      const c = engine.queryByPrefix(part, 0, 1)[0];
      out += c !== undefined ? ([...c.text][0] ?? "") : part;
    }
    return out;
  })();

  const coding = code.length > 0;
  /**
   * 单字 / 多字判据对齐 ime.py:501 —— 看**分词结果里有没有单引号**，
   * 不是看过滤空段后的段数。
   *
   * 差别出在尾随的人工单引号：splitSequence("wj4u'") === "wj4u'"，按 "'" 切再滤掉
   * 空段只剩 1 段，按段数判就误判成单字 → maybeAutoCommit 把 𬇕 直接顶上屏。
   * 而人工单引号意味着用户在做多字输入，ime.py 走多字分支，不会自动上字。
   */
  const mode: QueryMode = !coding ? "idle" : split.includes("'") ? "multi" : "single";

  /** 可选字总数 = 部件总数 - 字面段数（字面段不可选） */
  const partCount = Math.max(0, partSpace.length - literalIndices.length);

  /**
   * 逐字选择：多字态 + 所有可选部件都有候选 + 至少一个可选字。
   *
   * allPartsSelectable 排除 deepseek（ep/ek 无候选）这类不该进选择的多字；
   * partCount > 0 排除「全部是字面段」（如 deepseek'）的空转。
   *
   * selecting 的状态语义对齐 ime.py navigate_parts 的 entered_selection：
   * st.partIndex !== null 等价于「已进入选择且输入未变」—— resetParts 在 buffer
   * 变化时会把 partIndex 清回 null。所以进入选择后只要不再改动编码，
   * selecting 就一直为真（ime.py 的 current_phrase="" 在 navigation 时同样一直保持）。
   */
  const canSelect = mode === "multi" && allPartsSelectable && partCount > 0;
  const selecting = canSelect && st.partIndex !== null;
  const currentPart =
    selecting && st.partIndex !== null && st.partIndex < partSpace.length ? st.partIndex : null;

  /**
   * 预览基准串。
   *
   * 未进入逐字选择（selecting=false）时，对齐 ime.py main_function L544-556 两条分支：
   *   - 手动单引号 + 优先上词（enhanced）→ 词语增强预览（seg.display，词语优先、
   *     字面段按原文）—— 如 ceu'jihw → 「测试计划」。
   *   - 其余 → queryMultiChars(split)（各段首选拼串）—— 如 ceu → 「厕是」；
   *     各段无候选时整体为空（deepseek），兜底回 seg.display（字面整段回显原始编码）。
   *   这里的差别正是「非优先上词时直接空格上首选字组合」的关键。
   *
   * 进入逐字选择后（selecting=true）：
   *   切回 perPartFirst（逐段首候选组合）—— 对齐 ime.py navigate_parts
   *   entered_selection 把 last_output_text 换成首选字组合、空格上屏该串。
   */
  const multiCharsFirst = parts.length > 1 ? engine.queryMultiChars(split) : "";
  const previewBase = selecting
    ? perPartFirst
    : enhanced
      ? seg.display
      : multiCharsFirst !== ""
        ? multiCharsFirst
        : seg.display;

  /**
   * 逐字选择中按 resolved 覆盖（ime.py:283-297）。
   *
   * 只在**已有手选结果**时重建，空手选直接用 previewBase —— 这是 2026-09-01
   * 修的截断 bug：juyx 只对应词语「解书音形」，逐字首选为空、基准串是 4 字词语，
   * 而部件只有 ju / yx 两段，按「每段取 1 字」重建就把预览切成「解书」。
   */
  const preview =
    Object.keys(st.resolved).length > 0
      ? rebuildPreview(previewBase, partSpace, literalIndices, st.resolved)
      : previewBase;

  const rawPhrase = enhanced ? "" : engine.queryPhrase(code);
  const phraseContent = rawPhrase.slice(1, -1);
  // ime.py L301-306：词语与预览内容相同时只显示一个，避免重复
  const phrase = phraseContent === preview ? "" : rawPhrase;

  const keyClass = engine.nextCharClass(code);

  // 单字态查首段；多字态进入逐字选择后查当前部件；否则不显示单字候选
  const queryTarget =
    mode === "single"
      ? (parts[0] ?? "")
      : currentPart !== null
        ? (partSpace[currentPart] ?? "")
        : "";
  const showCandidates = mode === "single" || currentPart !== null;

  const start = st.page * PAGE_SIZE;
  const candidates = showCandidates ? engine.queryByPrefix(queryTarget, start, PAGE_SIZE) : [];
  const hasNextPage =
    showCandidates && queryTarget.length > 0 && engine.queryByPrefix(queryTarget, start + PAGE_SIZE, PAGE_SIZE).length > 0;

  /**
   * 上屏目标。
   *
   * 多字态：进入逐字选择后（selecting）用逐字预览串（回归首选字组合）——
   * 对齐 ime.py navigate_parts entered_selection 把 last_output_text 换成
   * 首选字组合、以及空格路径 L530 仅在 current_phrase 非空时用词语（进入选择时
   * 已被清空）。未进入选择时优先用词语（phrasePriority 开着且有词语）。
   */
  const display =
    mode === "multi"
      ? selecting
        ? preview
        : st.settings.phrasePriority && phraseContent.length > 0
          ? phraseContent
          : preview
      : (candidates[0]?.text ?? "");

  const pageLabel = buildPageLabel(
    mode,
    selecting,
    currentPart,
    partSpace,
    literalIndices,
    partCount,
    hasNextPage,
    start,
  );

  return {
    code,
    parts,
    partSpace,
    mode,
    // 取最后按下的键，不是编码末字符 —— 中间插入时两者不同（见 types.ts lastTap）。
    // 逐字选择中手选了一个字后让位给该字（lastPicked），确认「刚选了什么」。
    lastChar: st.lastPicked !== "" ? st.lastPicked : st.lastTap,
    candidates,
    preview,
    phrase,
    phraseContent,
    literalIndices,
    display,
    keyClass,
    hasNextPage,
    coding,
    selecting,
    canSelect,
    currentPart,
    partCount,
    pageLabel,
  };
}

/**
 * 逐字选择的当前部件在「非字面部件」中的序数（1 起）。
 *
 * 字面部件（无候选、按编码原样输出）不可选，既不计入分母也不该占用分子的序号 ——
 * 否则 deepseek'mox;（deepseek 是字面段）会显示「字 2/2」而不是「字 1/2」。
 */
function partOrdinal(
  partSpace: readonly string[],
  literalIndices: readonly number[],
  index: number,
): number {
  const literal = new Set(literalIndices);
  let n = 1;
  for (let i = 0; i < index && i < partSpace.length; i++) {
    if (!literal.has(i)) n++;
  }
  return n;
}

function buildPageLabel(
  mode: QueryMode,
  selecting: boolean,
  currentPart: number | null,
  partSpace: readonly string[],
  literalIndices: readonly number[],
  partCount: number,
  hasNextPage: boolean,
  start: number,
): string {
  if (mode === "idle") return "";
  const page = start / PAGE_SIZE + 1;
  // 首页且无下一页时不显示页码，避免常态下的视觉噪音
  const showPage = page > 1 || hasNextPage;
  if (selecting && currentPart !== null) {
    // 序号语义（2026-09-01 定稿）：分子 = 当前正在选第几个**可选**字，
    // 分母 = 可选字总数。桌面端 ime.py:323-326 已同步改为同一口径。
    const ordinal = partOrdinal(partSpace, literalIndices, currentPart);
    return `字 ${ordinal}/${partCount}${showPage ? ` 页 ${page}` : ""}`;
  }
  if (mode === "multi") return "";
  return showPage ? `页 ${page}` : "";
}
