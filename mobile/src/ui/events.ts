/**
 * 指针交互：点按与四向上滑。
 *
 * 用 Pointer Events 统一鼠标 / 触屏 / 触控笔。上滑阈值 15px 沿用设计稿。
 * 判定在 pointerup 时一次性结算 —— 途中只做视觉预告，避免 move 阶段反复触发。
 *
 * 水平阈值按键宽动态取（约 2 列），不写死像素：键宽随屏幕宽度变化，
 * 写死会让窄屏上「想上滑却判成横滑」。
 */

import type { KeyDef } from "./types.ts";

/** 上滑判定阈值（px），与设计稿一致 */
export const SWIPE_THRESHOLD = 15;

/** 水平滑动阈值 = 键宽 × 该系数 */
const HORIZONTAL_KEY_RATIO = 2;

export type SwipeDir = "none" | "up" | "left" | "right";

export interface GestureHandlers {
  onTap(def: KeyDef): void;
  onSwipeUp(def: KeyDef): void;
  onSwipeLeft(def: KeyDef): void;
  onSwipeRight(def: KeyDef): void;
}

interface Active {
  def: KeyDef;
  node: HTMLElement;
  x: number;
  y: number;
  dir: SwipeDir;
}

function resolveDir(dx: number, dy: number, keyWidth: number): SwipeDir {
  const hThreshold = keyWidth * HORIZONTAL_KEY_RATIO;
  // 纵向优先：上滑是高频操作，横向需要明显更大的位移才成立
  if (dy <= -SWIPE_THRESHOLD) return "up";
  if (Math.abs(dx) >= hThreshold && Math.abs(dx) > Math.abs(dy)) {
    return dx < 0 ? "left" : "right";
  }
  return "none";
}

export function attachGestures(
  root: HTMLElement,
  lookup: ReadonlyMap<string, KeyDef>,
  h: GestureHandlers,
): void {
  let active: Active | null = null;

  const clear = (): void => {
    if (active !== null) {
      active.node.classList.remove("is-pressed", "is-swipe-up", "is-swipe-left", "is-swipe-right");
      active = null;
    }
  };

  root.addEventListener("pointerdown", (e) => {
    const node = (e.target as HTMLElement | null)?.closest<HTMLElement>(".kb-key");
    if (node === null || node === undefined) return;
    const main = node.dataset["main"];
    if (main === undefined) return;
    const def = lookup.get(main);
    if (def === undefined) return;

    e.preventDefault();
    // 捕获失败不应中断手势：某些指针类型 / 合成事件下 setPointerCapture 会抛
    try {
      node.setPointerCapture(e.pointerId);
    } catch {
      /* 退化：仍按普通冒泡处理，pointerup 落在键盘容器内即可结算 */
    }
    node.classList.add("is-pressed");
    active = { def, node, x: e.clientX, y: e.clientY, dir: "none" };
  });

  root.addEventListener("pointermove", (e) => {
    if (active === null) return;
    const dir = resolveDir(
      e.clientX - active.x,
      e.clientY - active.y,
      active.node.offsetWidth || SWIPE_THRESHOLD * 3,
    );
    if (dir === active.dir) return;
    active.dir = dir;
    active.node.classList.remove("is-swipe-up", "is-swipe-left", "is-swipe-right");
    if (dir !== "none") active.node.classList.add(`is-swipe-${dir}`);
  });

  root.addEventListener("pointerup", (e) => {
    if (active === null) return;
    const { def, dir } = active;
    const node = active.node;
    clear();
    if (node.hasPointerCapture(e.pointerId)) node.releasePointerCapture(e.pointerId);

    switch (dir) {
      case "up":
        h.onSwipeUp(def);
        return;
      case "left":
        h.onSwipeLeft(def);
        return;
      case "right":
        h.onSwipeRight(def);
        return;
      case "none":
        h.onTap(def);
        return;
    }
  });

  root.addEventListener("pointercancel", clear);
  root.addEventListener("lostpointercapture", clear);
}
