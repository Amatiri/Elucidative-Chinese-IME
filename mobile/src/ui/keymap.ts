/**
 * 键位定义 —— 方案 H（10 列 × 5 行，数字整行在 Row2）。
 *
 * 副字符口径依据设计稿「四、副字符状态切换表」：
 *   - 上滑 1-5：空闲态显示 !@#$%，编码态切换为 ①②③④⑤ 并改为「选 N 号候选」。
 *     硬编码成符号会导致「想选候选却看到 ! 提示」的错误引导。
 *   - 上滑 N：空闲态直出英文句点，编码态作补码引导符，两种状态都不灰显。
 *   - 上滑 B / M：编码态分别为「上屏首选」「放弃输入」，副字符提示不变。
 *   - 上滑 6-0、Row3/Row4 其余符号、上滑 V 的「,」、上滑 C：
 *     编码态灰显，行为受设置项「上滑输入符号」约束。
 *
 * 【空闲态直出】ime.py L721：数字 / ; / . / ' 只有在「已有编码字符」时才进编码缓冲，
 * 空闲态一律直接外输。本表不逐个标注，由 main.ts 依 nextCharClass("") 统一判定 ——
 * 凡不能作为编码首字符的一律直出，避免与真值表脱节。
 */

import type { Cell, KeyDef, ToggleKey } from "./types.ts";

/**
 * 编码字符键：主字符即编码字符。
 *
 * 注意引擎 CODE_CHARS 只认小写，而键帽按设计稿显示大写，
 * 故 code 一律转小写；大小写只影响显示，不影响编码。
 */
function ch(
  main: string,
  idleSub: string,
  opts: { codingSub?: string; dim?: boolean; gated?: boolean; name?: string } = {},
): KeyDef {
  return {
    main,
    code: main.toLowerCase(),
    idleSub,
    codingSub: opts.codingSub,
    dimWhenCoding: opts.dim ?? false,
    swipe: { kind: "symbol", char: idleSub, gated: opts.gated ?? false },
    name: opts.name,
  };
}

/** 数字行 1-5：编码态变候选序号 */
function selectKey(main: string, sym: string, index: number): KeyDef {
  return {
    main,
    code: main,
    idleSub: sym,
    codingSub: "①②③④⑤"[index - 1]!,
    swipe: { kind: "select", index },
    name: `数字${main}`,
  };
}

/** 数字行 6-0：编码态灰显，受设置项约束 */
function gatedDigit(main: string, sym: string): KeyDef {
  const d = ch(main, sym, { dim: true, gated: true });
  return d;
}

/** Row3 / Row4 符号键：编码态灰显，受设置项约束 */
function symbolKey(main: string, sym: string): KeyDef {
  return ch(main, sym, { dim: true, gated: true });
}

/** 上滑切换设置项的键（A 自动上字 / S 优先上词）。键帽按开关状态高亮 */
function toggleKey(main: string, sub: string, key: ToggleKey, name: string): KeyDef {
  return {
    main,
    code: main.toLowerCase(),
    idleSub: sub,
    dimWhenCoding: true,
    swipe: { kind: "toggle", key, name },
  };
}

/** P2 功能键：上滑为 stub */
function funcKey(main: string, sub: string, name: string): KeyDef {
  return {
    main,
    code: main.toLowerCase(),
    idleSub: sub,
    dimWhenCoding: true,
    swipe: { kind: "stub", name },
  };
}

const ROW2: Cell[] = [
  selectKey("1", "!", 1),
  selectKey("2", "@", 2),
  selectKey("3", "#", 3),
  selectKey("4", "$", 4),
  selectKey("5", "%", 5),
  gatedDigit("6", "^"),
  gatedDigit("7", "&"),
  gatedDigit("8", "*"),
  gatedDigit("9", "("),
  gatedDigit("0", ")"),
].map((def) => ({ kind: "key" as const, span: 1, def }));

const ROW3: Cell[] = (
  [
    ["Q", "`"],
    ["W", "~"],
    ["E", "_"],
    ["R", "+"],
    ["T", "["],
    ["Y", "]"],
    ["U", "{"],
    ["I", "}"],
    ["O", "\\"],
    ["P", "|"],
  ] as const
).map(([m, s]) => ({ kind: "key" as const, span: 1, def: symbolKey(m, s) }));

// 同 ROW5：显式标注 KeyDef[]，否则 swipeLeft.kind 会被推断成 string
const ROW4_DEFS: KeyDef[] = [
  // 键帽只印「字」「词」，全称分别是「自动上字」「优先上词」；
  // 上滑即切换对应开关，不再提示「P2 待实现」
  toggleKey("A", "字", "autoCommit", "自动上字"),
  toggleKey("S", "词", "phrasePriority", "优先上词"),
  funcKey("D", "译", "翻译"),
  funcKey("F", "剪", "剪贴板"),
  // G / H：上滑出 < >，左右滑移动光标（手机键盘拟定.html 的「← 左移」「右移 →」）
  { ...symbolKey("G", "<"), swipeLeft: { kind: "cursor", delta: -1 }, name: "光标左移 / <" },
  { ...symbolKey("H", ">"), swipeRight: { kind: "cursor", delta: 1 }, name: "光标右移 / >" },
  symbolKey("J", "/"),
  symbolKey("K", "?"),
  symbolKey("L", '"'),
  symbolKey(";", ":"),
];

const ROW4: Cell[] = ROW4_DEFS.map((def) => ({ kind: "key" as const, span: 1, def }));

// 显式标注 KeyDef[]：否则字面量里的 swipe.kind 会被推断成 string 而非联合成员
const ROW5_DEFS: KeyDef[] = [
  { main: "'", code: "'", idleSub: "⇪", swipe: { kind: "caps" }, name: "大写锁定" },
  funcKey("Z", "部", "部首查询"),
  funcKey("X", "🌐", "语言切换"),
  { main: "C", code: "c", idleSub: "设", dimWhenCoding: true, swipe: { kind: "settings" }, name: "设置" },
  ch("V", ",", { dim: true, gated: true }),
  { main: "B", code: "b", idleSub: "空", swipe: { kind: "commitOrSpace" }, name: "上屏首选/空格" },
  { main: "N", code: "n", idleSub: ".", swipe: { kind: "dotOrBuma" }, name: "句点/补码引导" },
  { main: "M", code: "m", idleSub: "↵", swipe: { kind: "abandonOrEnter" }, name: "放弃输入/回车" },
  /**
   * '=' / '-' **不是编码字符**（不在 CODE_CHARS 里）。
   * 有编码时作逐字选择导航（ime.py L727-734），空闲态直出原字符。
   *
   * 单击 = 下一个字（进入逐字选择的第一步，用得最多，放主位）；
   * 上滑 = 上一个字。原先反过来，最常用的操作反而要上滑。
   */
  { main: "=", idleSub: "-", swipe: { kind: "partNav", delta: -1 }, name: "逐字选择" },
  { main: "⌫", swipe: { kind: "none" }, name: "退格" },
];

const ROW5: Cell[] = ROW5_DEFS.map((def) => ({ kind: "key" as const, span: 1, def }));

/** Row1：显示区（1 列）+ 候选条（8 列）+ 翻页键（1 列） */
const ROW1: Cell[] = [
  { kind: "display", span: 1 },
  { kind: "candidate", span: 8 },
  {
    kind: "key",
    span: 1,
    def: {
      main: "∨",
      idleSub: "∧",
      swipe: { kind: "page", delta: -1 },
      name: "候选翻页",
    },
  },
];

/** 5 行方案 H。6 行变体（v0.2）在 Row1 与 Row2 之间插入 QWERTY 行 */
export const KEYMAP_5ROW: readonly Cell[][] = [ROW1, ROW2, ROW3, ROW4, ROW5];

/** 总列数 —— 每行 span 之和必须等于它 */
export const COLS = 10;

/** 取出一行里的所有键（跳过显示区与候选条） */
export function keysOf(row: readonly Cell[]): KeyDef[] {
  return row.flatMap((c) => (c.kind === "key" ? [c.def] : []));
}

/** 主字符 → 键定义。主字符在整个键位表中唯一，可安全用作反查键 */
export const KEY_BY_MAIN: ReadonlyMap<string, KeyDef> = new Map(
  KEYMAP_5ROW.flatMap((row) =>
    row.flatMap((cell) => (cell.kind === "key" ? [[cell.def.main, cell.def] as const] : [])),
  ),
);
