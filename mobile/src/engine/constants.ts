/**
 * 引擎常量。与 config.py 保持一致，但不 import config —— 它带 tkinter 依赖。
 */

/** config.py:17 —— 合法编码字符集（39 个） */
export const CODE_CHARS = "1234567890qwertyuiopasdfghjklzxcvbnm;'.";

const CODE_CHAR_SET: ReadonlySet<string> = new Set(CODE_CHARS);

/** config.py:19 —— 桌面端选候选符号 */
export const SELECTION_SYMBOLS: readonly string[] = ["!", "@", "#", "$", "%"];

/**
 * 只认 ASCII 0-9。
 *
 * 刻意区别于 JS 的 /\d/ 和 Python 的 str.isdigit()：后两者对 '²' '٣' '１'
 * 之类也返回 true，而码表里不存在这些字符。用 ASCII 比较属于**收紧**语义：
 * 遇到非 ASCII 数字时本引擎与 Python 端行为不同，但那种输入不可能来自键盘
 * （输入串只会含 CODE_CHARS），故无实际影响。
 *
 * 已知偏差，Golden 夹具不涉及。
 */
export function isAsciiDigit(c: string): boolean {
  return c >= "0" && c <= "9";
}

/** 是否为合法编码字符 */
export function isCodeChar(c: string): boolean {
  return CODE_CHAR_SET.has(c);
}
