/**
 * 设置持久化。使用 localStorage，读写失败时静默回退到默认值 ——
 * 隐私模式下 localStorage 可能抛异常，不应因此让键盘起不来。
 */

import type { Settings, SymbolSwipeMode } from "./types.ts";

// 键名带版本：默认值变更时必须升版本，否则老用户读到的仍是 localStorage 里的旧值。
// v3：上滑输入符号默认从「禁用」改为「放弃输入」（对齐 ime.py:777-780）
const KEY = "jieshu-demo-settings-v3";

export const DEFAULT_SETTINGS: Settings = {
  rows: 5,
  // 默认「放弃输入」：对齐 ime.py:777-780 —— 编码态输入非法字符一律放弃输入，
  // 原编码留在编辑区。桌面端没有「禁用」这一档。
  symbolSwipe: "abandon",
  // 默认开启，与 ime.py 的默认状态一致
  autoCommit: true,
  // 开启后，手动输入单引号的多字串走「词语增强预览」（ime.py L527-530）
  phrasePriority: true,
  // 默认开启，与 ime.py:752-758 一致
  backspaceDeletesChar: true,
};

function isMode(v: unknown): v is SymbolSwipeMode {
  return v === "disabled" || v === "abandon";
}

function bool(v: unknown, fallback: boolean): boolean {
  return typeof v === "boolean" ? v : fallback;
}

export function loadSettings(): Settings {
  try {
    const raw = localStorage.getItem(KEY);
    if (raw === null) return { ...DEFAULT_SETTINGS };
    const parsed: unknown = JSON.parse(raw);
    if (typeof parsed !== "object" || parsed === null) return { ...DEFAULT_SETTINGS };
    const o = parsed as Record<string, unknown>;
    return {
      rows: o["rows"] === 6 ? 6 : 5,
      symbolSwipe: isMode(o["symbolSwipe"]) ? o["symbolSwipe"] : DEFAULT_SETTINGS.symbolSwipe,
      autoCommit: bool(o["autoCommit"], DEFAULT_SETTINGS.autoCommit),
      phrasePriority: bool(o["phrasePriority"], DEFAULT_SETTINGS.phrasePriority),
      backspaceDeletesChar: bool(
        o["backspaceDeletesChar"],
        DEFAULT_SETTINGS.backspaceDeletesChar,
      ),
    };
  } catch {
    return { ...DEFAULT_SETTINGS };
  }
}

export function saveSettings(s: Settings): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(s));
  } catch {
    /* 隐私模式：放弃持久化，不影响当前会话 */
  }
}
