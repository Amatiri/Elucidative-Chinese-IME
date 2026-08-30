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
    page: 0,
    caps: "lower",
    settings,
    settingsOpen: false,
    partIndex: null,
    resolved: {},
  };
}

/** 按码点切分，避免切坏代理对 */
function chars(s: string): string[] {
  return [...s];
}

/** 编码变化后逐字选择必须重置：部件下标与已选字都依赖旧的分段结果 */
function resetParts(st: KeyboardState): Partial<KeyboardState> {
  return { partIndex: null, resolved: {}, page: 0, codeCursor: 0, lastTap: "" };
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
 * 逐字选择态下优先退出选择，而不是删编码 —— 与 ime.py 的部件导航一致。
 */
export function backspace(st: KeyboardState): KeyboardState {
  if (st.partIndex !== null) {
    return { ...st, partIndex: null, resolved: {} };
  }
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

/** 放弃输入：当前编码原样留在编辑区，结束编码态（对齐 ime.py:777-780） */
export function abandonInput(st: KeyboardState, code: string): KeyboardState {
  const next = insertAtCursor(st, code);
  return { ...next, ...resetParts(next), buffer: "" };
}

/** 清空编码，保留已上屏内容 */
export function clearBuffer(st: KeyboardState): KeyboardState {
  return { ...st, ...resetParts(st), buffer: "" };
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
