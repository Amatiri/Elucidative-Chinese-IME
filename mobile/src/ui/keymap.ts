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
  // Z 上滑打开部件表浮层（对齐 ime.py:983 的 radical_table_data）；点按仍是编码键 z
  { main: "Z", code: "z", idleSub: "部", swipe: { kind: "radical" }, name: "部件表查询" },
  // X/V/B/N/M 五键的功能在 6 行布局下提升为 Row6 主键，副字符仅 6 行下隐藏；
  // 5 行布局完整保留副字符与上滑行为（计划 §1.2「Row5 其余上滑保留不删」）
  { ...funcKey("X", "🌐", "语言切换"), hideSubIn6Row: true },
  { main: "C", code: "c", idleSub: "设", dimWhenCoding: true, swipe: { kind: "settings" }, name: "设置" },
  // swipe.char 与 idleSub 同源但创建时已定值，隐藏副字符不影响 5 行下上滑出「,」
  { ...ch("V", ",", { dim: true, gated: true }), hideSubIn6Row: true },
  { main: "B", code: "b", idleSub: "空", hideSubIn6Row: true, swipe: { kind: "commitOrSpace" }, name: "上屏首选/空格" },
  { main: "N", code: "n", idleSub: ".", hideSubIn6Row: true, swipe: { kind: "dotOrBuma" }, name: "句点/补码引导" },
  { main: "M", code: "m", idleSub: "↵", hideSubIn6Row: true, swipe: { kind: "abandonOrEnter" }, name: "放弃输入/回车" },
  /**
   * '=' / '-' **不是编码字符**（不在 CODE_CHARS 里）。
   * 有编码时作逐字选择导航（ime.py L727-734），空闲态直出原字符。
   *
   * 单击 = 下一个字（进入逐字选择的第一步，用得最多，放主位）；
   * 上滑 = 上一个字。原先反过来，最常用的操作反而要上滑。
   */
  { main: "=", idleSub: "-", swipe: { kind: "partNav", delta: -1 }, name: "逐字选择" },
  /**
   * ⌫：单点退格、长按加速连删、**上滑清空已上屏文本**（副字符「清」）。
   * 有了副字符，上滑就走 clearAll 而不会退化成单点退格（见 subTextOf 门控）。
   */
  { main: "⌫", idleSub: "清", swipe: { kind: "clearAll" }, name: "退格 / 上滑清空" },
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

/**
 * Row6（6 行变体）：在 Row5 下方追加一行，把几个高频功能键提升为主键。
 * 列宽比对齐计划 §1.2：语 1U / ， 1U / 空格 5U≈170dp / 句点 1U / 回车 2U（共 10U）。
 *
 * - 🌐：语言切换（与 X 上滑同源，P2 待实现），单点即提示
 * - ,：键面与输出都是英文逗号（用户定稿）；编码态走 swipeSymbol 的放弃语义
 *   （6 行下这是英文逗号的唯一入口；中文逗号走 d.b 或 5 行 V 上滑）
 * - 空格 5U：编码态上屏首选、空闲态输出空格（与 B 上滑同源）
 * - 句点 . 1U：键面显示英文句点，永远输出英文句点；中文句号仍走 d.. / N 上滑空闲态
 * - 回车 2U：编码态放弃输入、空闲态回车（与 M 上滑同源）
 *
 * Row5 其余上滑保留不删（上滑 B 仍出空格）。见计划 §1.2。
 */
const ROW6_DEFS: KeyDef[] = [
  { main: "🌐", swipe: { kind: "stub", name: "语言切换" }, name: "语言切换" },
  { main: ",", swipe: { kind: "symbol", char: ",", gated: false }, name: "英文逗号" },
  { main: "空格", swipe: { kind: "commitOrSpace" }, name: "空格" },
  { main: ".", swipe: { kind: "symbol", char: ".", gated: false }, name: "英文句点" },
  { main: "↵", swipe: { kind: "abandonOrEnter" }, name: "回车" },
];

const ROW6: Cell[] = [
  { kind: "key", span: 1, def: ROW6_DEFS[0]! },
  { kind: "key", span: 1, def: ROW6_DEFS[1]! },
  { kind: "key", span: 5, def: ROW6_DEFS[2]! },
  { kind: "key", span: 1, def: ROW6_DEFS[3]! },
  { kind: "key", span: 2, def: ROW6_DEFS[4]! },
];

/** 5 行方案 H */
export const KEYMAP_5ROW: readonly Cell[][] = [ROW1, ROW2, ROW3, ROW4, ROW5];

/** 全量布局（5 行 + Row6）。DOM 始终按全量构建，Row6 在 5 行模式下隐藏 */
export const KEYMAP_ALL: readonly Cell[][] = [...KEYMAP_5ROW, ROW6];

/** 总列数 —— 每行 span 之和必须等于它 */
export const COLS = 10;

/** 取出一行里的所有键（跳过显示区与候选条） */
export function keysOf(row: readonly Cell[]): KeyDef[] {
  return row.flatMap((c) => (c.kind === "key" ? [c.def] : []));
}

/** 主字符 → 键定义。主字符在整个键位表中唯一，可安全用作反查键。
 *  基于 KEYMAP_ALL 构建，使 Row6 的键也能被手势层反查到 */
export const KEY_BY_MAIN: ReadonlyMap<string, KeyDef> = new Map(
  KEYMAP_ALL.flatMap((row) =>
    row.flatMap((cell) => (cell.kind === "key" ? [[cell.def.main, cell.def] as const] : [])),
  ),
);

/**
 * 当前状态下键面副字符的**实际显示内容**（2026-08-31 定稿规则）。
 *
 * 渲染（render.ts 的 .kb-sub）与手势门控（main.ts 的上滑转单点）必须共用
 * 这一个函数 —— 两处各写一份迟早漂移（Row6 单点失配就是前车之鉴）。
 *
 * 返回空串意味着键面上没有可提示的上滑动作 → 上滑视作单点
 * （「若某按键没有副字符，则不允许上滑」），不让手势吞键。
 */
export function subTextOf(def: KeyDef, coding: boolean, rows: 5 | 6): string {
  // 6 行下，功能已提升为 Row6 主键的键位（X/V/B/N/M）副字符隐藏
  if (rows === 6 && def.hideSubIn6Row === true) return "";
  return coding && def.codingSub !== undefined ? def.codingSub : (def.idleSub ?? "");
}
