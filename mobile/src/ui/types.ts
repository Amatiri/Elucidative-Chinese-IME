/**
 * UI 层数据结构。
 *
 * 键位定义与引擎解耦：引擎只认 CODE_CHARS 里的编码字符，
 * 键帽上的主字符 / 副字符 / 上滑语义全部由本模块描述。
 */

/**
 * 上滑行为。带 Or 后缀的表示行为随状态（空闲态 / 编码态）而变，
 * 由 main.ts 依据当前 buffer 是否为空来分派。
 */
export type SwipeAction =
  /** 无上滑行为（⌫） */
  | { kind: "none" }
  /** 直出英文符号。gated=true 时编码态受设置项「上滑输入符号」约束 */
  | { kind: "symbol"; char: string; gated: boolean }
  /** 选第 index 号候选（上滑 1-5，编码态语义） */
  | { kind: "select"; index: number }
  /** 上滑 N：空闲态直出英文句点，编码态作补码引导符 */
  | { kind: "dotOrBuma" }
  /** 上滑 B：编码态上屏首选，空闲态输入空格 */
  | { kind: "commitOrSpace" }
  /** 上滑 M：编码态放弃输入，空闲态回车 */
  | { kind: "abandonOrEnter" }
  | { kind: "settings" }
  | { kind: "caps" }
  /** 候选翻页：∨ 点按下一页，上滑 ∧ 上一页 */
  | { kind: "page"; delta: number }
  /** 逐字选择导航：- 上一个部件 / = 下一个部件（对齐 ime.py navigate_parts） */
  | { kind: "partNav"; delta: number }
  /** 开关：上滑 A / S 切换对应设置项，键帽按状态高亮 */
  | { kind: "toggle"; key: ToggleKey; name: string }
  /** P2 待实现的功能键 */
  | { kind: "stub"; name: string };

/** 可由上滑直接开关的设置项 */
export type ToggleKey = "autoCommit" | "phrasePriority";

/**
 * 大小写档位。三态循环，与手机键盘拟定.html 的 capCount % 3 一致：
 *   小 = lower（小写） 大 = once（单次大写） 连 = upper（连续大写）
 */
export type CapsMode = "lower" | "once" | "upper";

/** 小显示区的档位标识。空闲态显示，打字时让位给最后输入的字符 */
export const CAPS_LABEL: Record<CapsMode, string> = {
  lower: "小",
  once: "大",
  upper: "连",
};

/** 键帽视觉档位 —— 对应设计稿组件库五态 + 运行时二档 */
export type KeyClass =
  | "normal"
  | "recommended"
  /** 下一键无候选 —— 仍可点，只做灰显，不做抖动拒绝 */
  | "dim"
  | "func"
  /** 副字符灰显（常态键在编码态下的表现） */
  | "subDim";

export interface KeyDef {
  /** 键帽主字符 */
  main: string;
  /** 点按时输入的编码字符；功能键为 undefined */
  code?: string;
  /** 空闲态副字符 */
  idleSub?: string;
  /** 编码态副字符。undefined = 沿用 idleSub */
  codingSub?: string;
  /** 编码态副字符是否灰显 */
  dimWhenCoding?: boolean;
  /** 上滑行为 */
  swipe: SwipeAction;
  /** 左滑行为（G 键：光标左移） */
  swipeLeft?: { kind: "cursor"; delta: number };
  /** 右滑行为（H 键：光标右移） */
  swipeRight?: { kind: "cursor"; delta: number };
  /** 无障碍 / 调试用名 */
  name?: string;
}

/** 一行的单元格。Row1 由显示区与候选条占据，其余行全为键 */
export type Cell =
  | { kind: "display"; span: number }
  | { kind: "candidate"; span: number }
  | { kind: "key"; span: number; def: KeyDef };

/** 上滑输入符号 · 设置项值 */
export type SymbolSwipeMode =
  /** 禁用，维持候选状态（默认） */
  | "disabled"
  /** 放弃输入，保留原编码（对齐 ime.py:777-780） */
  | "abandon";

export interface Settings {
  /** 键盘布局。6 行变体 v0.1 仅占位 */
  rows: 5 | 6;
  symbolSwipe: SymbolSwipeMode;
  /** 自动上字：编码打满且无重码时自动上屏（键帽简作「字」） */
  autoCommit: boolean;
  /** 优先上词：多字时词语优先于首选字组合（键帽简作「词」） */
  phrasePriority: boolean;
}

/** 键盘运行时状态。committed 为已上屏文本，buffer 为正在输入的编码串 */
export interface KeyboardState {
  buffer: string;
  committed: string;
  /** 光标在 committed 中的位置；空闲态下 G/H 移动它 */
  cursor: number;
  /**
   * 光标在编码串内部的位置（0..buffer.length）。
   * 候选态下 G/H 移动它，对齐 ime.py 的 code_char_before_cursor ——
   * 外输模式支持在编码中间插入字符，不只是追加到末尾。
   */
  codeCursor: number;
  /** 候选页码，0 起 */
  page: number;
  caps: CapsMode;
  settings: Settings;
  settingsOpen: boolean;
  /**
   * 最后按下的那个编码字符，供左上角小显示区。
   * 手机键盘上手指会挡住键帽，小显示区起的是「刚按了什么」的反馈作用
   * （手机键盘拟定.html L774 就是把它设成按下的字符）。
   * 与 code.slice(-1) 的区别只在编码中间插入/移动光标时显现。
   */
  lastTap: string;
  /** 逐字选择：当前部件下标。null = 未进入逐字选择 */
  partIndex: number | null;
  /** 逐字选择：已手选的字，键为部件下标 */
  resolved: Readonly<Record<number, string>>;
}
