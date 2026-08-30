/**
 * 从输入流中提取连续的合法编码字符。
 *
 * 与 Python dictionary_frontend.py:91-100 process_input 逐行等价。
 */

import { isCodeChar } from "./constants.ts";

/**
 * 规则：必须先遇到一个 ASCII 小写字母才开始采集；采集开始后，非编码字符会被跳过
 * （不终止采集）。
 *
 * 注意 L96 的 'a' <= char <= 'z' 只认 ASCII 小写 —— 大写 B 不会启动采集。
 * 一旦启动，大写也不是 CODE_CHARS，同样被跳过。
 */
export function processInput(inputText: string): string {
  let result = "";
  let startCollecting = false;
  for (const char of inputText) {
    if (!startCollecting && char >= "a" && char <= "z") {
      startCollecting = true;
    }
    if (startCollecting && isCodeChar(char)) {
      result += char;
    }
  }
  return result;
}
