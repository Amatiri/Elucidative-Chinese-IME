/**
 * process_input 的 Golden 比对与语义边界。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { processInput } from "./process.ts";
import { casesOf, runCases, assertRun } from "./golden.util.ts";
import { CODE_CHARS } from "./constants.ts";

test("L1 process_input 与 Python 引擎逐条一致", () => {
  const cases = casesOf("process_input");
  assert.ok(cases.length > 1000, `用例数异常：${cases.length}`);
  const r = runCases(cases, (args) => processInput(args[0] as string));
  assertRun("process_input", r);
});

test("语义：必须先遇到小写字母才开始采集", () => {
  // ⚠ 反直觉：大写/数字在开头只是**延后**启动，不是整串作废。
  // 一旦后面出现小写字母，采集从那里开始 —— 前面的字符被丢弃。
  assert.equal(processInput("ABCabc"), "abc");
  assert.equal(processInput("123abc"), "abc");
  assert.equal(processInput("abc"), "abc");
  assert.equal(processInput("中文abc123"), "abc123");
  // 全程没有小写字母 → 空
  assert.equal(processInput("ABC123中文"), "");
});

test("语义：采集开始后，非编码字符被跳过而非终止", () => {
  assert.equal(processInput("ab中文cd"), "abcd");
  assert.equal(processInput("a1b2c3"), "a1b2c3");
  // ' 和 . 是合法编码字符
  assert.equal(processInput("a'b.c"), "a'b.c");
});

test("语义：编码字符集整体通过（但开头的数字会被丢掉）", () => {
  // CODE_CHARS 以 "1234567890" 开头，而启动条件是小写字母 ——
  // 所以前 10 个数字在遇到 'q' 之前都未被采集，结果少一截。
  // 这是 Python 端的既有行为（已用真引擎核对），不是缺陷。
  const expected = CODE_CHARS.slice(10); // 去掉 "1234567890"
  assert.equal(expected, "qwertyuiopasdfghjklzxcvbnm;'.");
  assert.equal(processInput(CODE_CHARS), expected);
  // 前面垫一个小写字母就能全收
  assert.equal(processInput("a" + CODE_CHARS), "a" + CODE_CHARS);
});

test("语义：空串与纯空白", () => {
  assert.equal(processInput(""), "");
  assert.equal(processInput("   "), "");
});
