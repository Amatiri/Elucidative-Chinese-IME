/**
 * 键盘状态与纯函数 reducer。
 *
 * 所有函数返回新对象，不原地修改 —— 渲染层据此做整树重绘，
 * 键位只有 50 个，重绘成本可忽略，换来的是状态可预测。
 *
 * 涉及 committed 的增删一律按「码点」操作：152 条非 BMP 字是 UTF-16 代理对，
 * 用 slice(i-1) 会切出孤立代理项。
 */

import type { CapsMode, KeyboardState, Settings } from "./types.ts";

const CAPS_ORDER: readonly CapsMode[] = ["lower", "once", "upper"];

export function initialState(settings: Settings): KeyboardState {
  return {
    buffer: "",
    committed: "",
    cursor: 0,
    codeCursor: 0,
    lastTap: "",
    lastPicked: "",
    page: 0,
    caps: "lower",
    settings,
    settingsOpen: false,
    partIndex: null,
    resolved: {},
    radicalOpen: false,
  };
}

/** 按码点切分，避免切坏代理对 */
function chars(s: string): string[] {
  return [...s];
}

/** 编码变化后逐字选择必须重置：部件下标与已选字都依赖旧的分段结果 */
function resetParts(st: KeyboardState): Partial<KeyboardState> {
  return {
    partIndex: null,
    resolved: {},
    page: 0,
    codeCursor: 0,
    lastTap: "",
    lastPicked: "",
  };
}

/**
 * 在编码光标处插入字符（ime.py 是在 entry_box 的 INSERT 位置插入，不只是追加）。
 * 插入后光标随之后移一位。
 */
export function pushCode(st: KeyboardState, code: string): KeyboardState {
  const caps = st.caps === "once" ? "lower" : st.caps;
  const at = clamp(st.codeCursor, 0, st.buffer.length);
  const buffer = st.buffer.slice(0, at) + code + st.buffer.slice(at);
  return {
    ...st,
    ...resetParts(st),
    buffer,
    codeCursor: at + code.length,
    lastTap: code,
    caps,
    settingsOpen: false,
  };
}

/** 编码光标移动，边界钳制在 [0, buffer.length] */
export function moveCodeCursor(st: KeyboardState, delta: number): KeyboardState {
  const next = clamp(st.codeCursor + delta, 0, st.buffer.length);
  return next === st.codeCursor ? st : { ...st, codeCursor: next };
}

function clamp(v: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, v));
}

/**
 * 退格：先删编码；编码为空才删光标前的已上屏字符。
 *
 * 逐字选择态下的行为由设置项 backspaceDeletesChar 决定（默认开）：
 *   - 开：删一位编码字符，**同时**退出逐字选择 —— 与 ime.py:752-758 一致。
 *     桌面端退格无条件删字符，退出选择只是输入变化后 main_function
 *     （ime.py:464-476）重置状态的连带效果，两者一起发生。
 *   - 关：只退出逐字选择，编码原样保留。
 */
export function backspace(st: KeyboardState): KeyboardState {
  if (st.partIndex !== null && !st.settings.backspaceDeletesChar) {
    return { ...st, partIndex: null, resolved: {}, page: 0, lastPicked: "" };
  }
  // 逐字选择态也会落到这里：下面的 resetParts 顺带清掉选择态
  // 删的是光标前那一个字符，不是末字符 —— 光标可以停在编码中间
  if (st.buffer.length > 0 && st.codeCursor > 0) {
    const at = st.codeCursor;
    return {
      ...st,
      ...resetParts(st),
      buffer: st.buffer.slice(0, at - 1) + st.buffer.slice(at),
      codeCursor: at - 1,
    };
  }
  if (st.cursor > 0) {
    const arr = chars(st.committed);
    arr.splice(st.cursor - 1, 1);
    return { ...st, committed: arr.join(""), cursor: st.cursor - 1 };
  }
  return st;
}

/** 在光标处插入文本（上屏 / 直出符号） */
export function insertAtCursor(st: KeyboardState, text: string): KeyboardState {
  const arr = chars(st.committed);
  arr.splice(st.cursor, 0, ...chars(text));
  return {
    ...st,
    committed: arr.join(""),
    cursor: st.cursor + chars(text).length,
  };
}

/** 候选上屏：清空编码与逐字选择 */
export function commitText(st: KeyboardState, text: string): KeyboardState {
  const next = insertAtCursor(st, text);
  return { ...next, ...resetParts(next), buffer: "" };
}

/** 放弃输入：当前编码原样留在编辑区，结束编码态（对齐 ime.py:797-802） */
export function abandonInput(st: KeyboardState, code: string): KeyboardState {
  const next = insertAtCursor(st, code);
  return { ...next, ...resetParts(next), buffer: "" };
}

/**
 * 编码态输入符号（放弃输入）：编码按**编码光标**切开，符号插在切口处。
 *
 * 对齐 ime.py 外输模式 initial() L797-802：非法字符一律视作放弃输入
 * （entry_box 清空、计数归零）。桌面端编码字符是随按键流逐字进入目标文本的，
 * 光标可以停在编码中间（left / right 只动 entry_box 光标，目标光标随之移动），
 * 随后的符号按键落在**目标光标处** —— 编码因此被切成两段，而不是追加到末尾。
 *
 * 例：已上屏「模|型」，编码 ce，编码光标在 c 后 → 上滑 ` 得「模c`e型」。
 *
 * 光标停在符号之后，即用户抬手前眼睛看的那个位置。
 */
export function abandonInputWithSymbol(st: KeyboardState, char: string): KeyboardState {
  const at = clamp(st.codeCursor, 0, st.buffer.length);
  const head = st.buffer.slice(0, at);
  const tail = st.buffer.slice(at);
  const next = insertAtCursor(st, head + char + tail);
  return {
    ...next,
    ...resetParts(next),
    buffer: "",
    // head 是 ASCII 编码字符，码元数 = 码点数；char 可能是全角符号，要按码点算
    cursor: st.cursor + head.length + [...char].length,
  };
}

/** 清空编码，保留已上屏内容 */
export function clearBuffer(st: KeyboardState): KeyboardState {
  return { ...st, ...resetParts(st), buffer: "" };
}

/**
 * 清空已上屏文本（上滑 ⌫ 二次确认后的落点）。
 *
 * 只动 committed 与 cursor，编码 buffer 原样保留 —— 清空的是「已提交的内容」，
 * 正在输入的编码属于另一个状态域；一起清掉会让用户打了一半的编码无声消失。
 */
export function clearCommitted(st: KeyboardState): KeyboardState {
  if (st.committed.length === 0) return st;
  return { ...st, committed: "", cursor: 0 };
}

export function setPage(st: KeyboardState, page: number): KeyboardState {
  return { ...st, page: Math.max(0, page) };
}

export function cycleCaps(st: KeyboardState): KeyboardState {
  const i = CAPS_ORDER.indexOf(st.caps);
  return { ...st, caps: CAPS_ORDER[(i + 1) % CAPS_ORDER.length]! };
}

export function setSettingsOpen(st: KeyboardState, open: boolean): KeyboardState {
  return { ...st, settingsOpen: open };
}

/**
 * 部件表浮层开 / 关。
 *
 * 只切一个布尔位，不进 resetParts、不改 buffer / resolved / 候选——
 * 浮层是覆盖在键盘上的参考视图，关闭后键盘状态原样保留。
 */
export function setRadicalOpen(st: KeyboardState, open: boolean): KeyboardState {
  return { ...st, radicalOpen: open };
}

export function updateSettings(st: KeyboardState, patch: Partial<Settings>): KeyboardState {
  return { ...st, settings: { ...st.settings, ...patch } };
}

/** 光标移动，边界钳制在 [0, committed 码点数] */
export function moveCursor(st: KeyboardState, delta: number): KeyboardState {
  const max = chars(st.committed).length;
  const next = Math.min(max, Math.max(0, st.cursor + delta));
  return next === st.cursor ? st : { ...st, cursor: next };
}

/** 逐字选择：进入 / 切换当前部件 */
export function setPartIndex(st: KeyboardState, index: number | null): KeyboardState {
  if (index === null) return { ...st, partIndex: null, page: 0 };
  return { ...st, partIndex: index, page: 0 };
}

/** 逐字选择：手选某个部件的字 */
export function resolvePart(st: KeyboardState, index: number, text: string): KeyboardState {
  return { ...st, resolved: { ...st.resolved, [index]: text }, page: 0 };
}

/**
 * 逐字选择中手选一个部件后，把「前缀 + 剩余编码」回写进编码串。
 *
 * 对齐 ime.py:424-441 handle_selection_keys 的非末字分支：
 *   parts[i] = prefix + remaining，再 "'".join(parts) 写回输入框。
 * 于是上方下划线的编码串实时补全（ceu → 选「测」→ ce4u'u），
 * 后续翻页 / 再选字都基于补全后的完整编码。
 *
 * 不能用 pushCode：它调 resetParts 会把 resolved 冲掉，而逐字选择必须跨这次回写保留。
 */
export function commitPartCode(
  st: KeyboardState,
  buffer: string,
  nextPart: number | null,
  picked: string,
): KeyboardState {
  return {
    ...st,
    buffer,
    codeCursor: buffer.length,
    partIndex: nextPart,
    page: 0,
    lastPicked: picked,
  };
}
