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

/** 长按判定阈值（ms）。按住不动到时即成立，用于 ⌫ 的加速连删 */
export const LONG_PRESS_MS = 600;

export type SwipeDir = "none" | "up" | "left" | "right";

export interface GestureHandlers {
  onTap(def: KeyDef): void;
  onSwipeUp(def: KeyDef): void;
  onSwipeLeft(def: KeyDef): void;
  onSwipeRight(def: KeyDef): void;
  /**
   * 长按成立（按住 LONG_PRESS_MS 且期间未滑动）。
   * 返回 true = **消费**了这次长按：松手时不再派发 onTap，
   * 保证「长按连删」结束的松手不会多吃一次单点退格。
   * 返回 false / 未实现 = 不消费，松手照常当单点处理 —— 其余键长按不吞键。
   */
  onLongPressStart?(def: KeyDef): boolean;
  /** 松手 / 取消：停止长按连发（interval 必须成对清理） */
  onLongPressEnd?(): void;
}

interface Active {
  def: KeyDef;
  node: HTMLElement;
  x: number;
  y: number;
  dir: SwipeDir;
  /** 长按计时已到点并回调过 onLongPressStart */
  longPressFired: boolean;
  /** 回调返回 true（该键吃下了长按），松手时抑制 onTap */
  longPressConsumed: boolean;
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
  let longPressTimer = 0;

  const clear = (): void => {
    window.clearTimeout(longPressTimer);
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
    const self: Active = {
      def,
      node,
      x: e.clientX,
      y: e.clientY,
      dir: "none",
      longPressFired: false,
      longPressConsumed: false,
    };
    active = self;

    longPressTimer = window.setTimeout(() => {
      // 期间已换键 / 已松手则作废（self 与当前 active 不一致）
      if (active !== self) return;
      self.longPressFired = true;
      self.longPressConsumed = h.onLongPressStart?.(self.def) === true;
      // 触感反馈。部分浏览器不支持 vibrate，静默失败即可
      try {
        navigator.vibrate?.(10);
      } catch {
        /* 桌面浏览器无振动，忽略 */
      }
    }, LONG_PRESS_MS);
  });

  root.addEventListener("pointermove", (e) => {
    if (active === null) return;
    const dx = e.clientX - active.x;
    const dy = e.clientY - active.y;

    // 长按成立**前**出现位移 = 用户在滑动，取消长按计时
    if (!active.longPressFired && (Math.abs(dx) >= SWIPE_THRESHOLD || Math.abs(dy) >= SWIPE_THRESHOLD)) {
      window.clearTimeout(longPressTimer);
    }

    // 长按连删中不做滑动预告，也不改变判定（手指微动不应打断连删）
    if (active.longPressConsumed) return;

    const dir = resolveDir(dx, dy, active.node.offsetWidth || SWIPE_THRESHOLD * 3);
    if (dir === active.dir) return;
    active.dir = dir;
    active.node.classList.remove("is-swipe-up", "is-swipe-left", "is-swipe-right");
    if (dir !== "none") active.node.classList.add(`is-swipe-${dir}`);
  });

  root.addEventListener("pointerup", (e) => {
    if (active === null) return;
    const { def, dir, longPressFired, longPressConsumed } = active;
    const node = active.node;
    clear();
    if (node.hasPointerCapture(e.pointerId)) node.releasePointerCapture(e.pointerId);

    // 长按：无论是否消费都要停止连发；只有消费了的才吞掉随后的单点，
    // 否则「长按连删 → 松手」会额外多删一个字符。
    if (longPressFired) {
      h.onLongPressEnd?.();
      if (longPressConsumed) return;
    }

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

  const abort = (): void => {
    const fired = active?.longPressFired === true;
    clear();
    if (fired) h.onLongPressEnd?.();
  };

  root.addEventListener("pointercancel", abort);
  root.addEventListener("lostpointercapture", abort);
}
