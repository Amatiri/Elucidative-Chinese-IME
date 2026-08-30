/**
 * 设置持久化。使用 localStorage，读写失败时静默回退到默认值 ——
 * 隐私模式下 localStorage 可能抛异常，不应因此让键盘起不来。
 */

import type { Settings, SymbolSwipeMode } from "./types.ts";

// 键名带版本：默认值变更时（如本轮把自动上字改为默认开启）
// 必须让旧的 localStorage 记录失效，否则老用户仍拿到旧默认
const KEY = "jieshu-demo-settings-v2";

export const DEFAULT_SETTINGS: Settings = {
  rows: 5,
  // 默认禁用：避免误触打断输入流（设计稿模块 6 · 选项 B）
  symbolSwipe: "disabled",
  // 默认开启，与 ime.py 的默认状态一致
  autoCommit: true,
  // 开启后，手动输入单引号的多字串走「词语增强预览」（ime.py L527-530）
  phrasePriority: true,
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
