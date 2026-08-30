/**
 * L7 人工冒烟 + 产品指标复核。
 *
 * 这里的期望值全部来自对真实码表的查证，不是推导出来的。
 * 覆盖四类最容易出问题的字：首字置顶高频字、补码字（含 '.'）、
 * 非 BMP 字（UTF-16 代理对）、通用符号标点。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { createEngine } from "./index.ts";
import { toLegacy } from "./types.ts";

const e = createEngine();

test("L7-a 首字置顶高频字：bu44 首选「不」", () => {
  // file_processor 的 first_level_map 把 24 个高频字移到各声母桶首位
  const rs = e.queryByPrefix("bu44", 0, 10);
  assert.ok(rs.length > 0);
  assert.equal(rs[0]!.text, "不");
  assert.equal(rs[0]!.rest, "");
});

test("L7-b 补码字：ba13 → ['八','捌.']，打满 ba13. 唯一命中「捌」", () => {
  const p4 = e.queryByPrefix("ba13", 0, 10);
  assert.deepEqual(p4.map(toLegacy), ["八", "捌."]);
  // '捌' 的 rest 是 '.' —— 提示用户还可以补第 5 位
  assert.equal(p4[1]!.text, "捌");
  assert.equal(p4[1]!.rest, ".");
  assert.equal(p4[1]!.kind, "bumaCode5");

  const full = e.queryByPrefix("ba13.", 0, 10);
  assert.equal(full.length, 1);
  assert.equal(full[0]!.text, "捌");
  assert.equal(full[0]!.rest, "");
});

test("L7-c 非 BMP 字：ba5o 唯一命中「𠀧」(U+20027)", () => {
  const rs = e.queryByPrefix("ba5o", 0, 10);
  assert.equal(rs.length, 1);
  assert.equal(rs[0]!.text, "𠀧");
  // UTF-16 下是 2 个码元，但码点必须是 1 个，且无孤立代理项
  assert.equal(rs[0]!.text.length, 2);
  assert.equal([...rs[0]!.text].length, 1);
  assert.ok(!/\p{Surrogate}/u.test(rs[0]!.text));
});

test("L7-d 通用符号标点：d.. → 。", () => {
  // 标点走 ciyu.txt 的 d 系列编码，没有独立符号面板
  assert.equal(e.queryPhrase("d.."), "(。)");
  const seg = e.getPhraseSegments("d..");
  assert.equal(seg.display, "。");
  // split_sequence 把 "d.." 切成 "d.'."（无数字且 len>2 → condition1 每 2 字符切）
  assert.deepEqual(seg.allParts, ["d.", "."]);
  assert.deepEqual(seg.literalIndices, []);
});

test("L7-e 多字模式：baba → 八八", () => {
  const split = e.splitSequence("baba");
  assert.equal(split, "ba'ba");
  assert.equal(e.queryMultiChars(split), "八八");
});

test("L7-f 端到端：输入流 → 编码 → 分词", () => {
  const raw = "wo3g 中文 bu44 XYZ";
  // processInput 遇第一个小写字母启动，之后非编码字符被跳过而非终止
  const code = e.processInput(raw);
  assert.equal(code, "wo3gbu44");
  // 分词结果是 "wo3g'bu44"，不是 "wo'3g'bu'44" ——
  // condition1（每 2 字符切）要求片段内**无数字**，这串有数字，故走
  // condition2：在 index 6 的数字处（前一位 'u' 非数字）于 pos-2=4 断开。
  assert.equal(e.splitSequence(code), "wo3g'bu44");
});

test("产品指标复核：4 键唯一率（计划值 77.2%）", () => {
  // 这是方案 H 的核心产品论据：鼓励打满 4 键，而不是 3 键看候选。
  // 引擎侧不排序、不干预，唯一率完全由码表决定 —— 这里复核它确实如此。
  const p4 = new Set<string>();
  for (const entry of e.dataset.entries) {
    if (entry.code.length >= 4) p4.add(entry.code.slice(0, 4));
  }
  let unique = 0;
  for (const p of p4) {
    if (e.queryByPrefix(p, 0, 500).length === 1) unique++;
  }
  const rate = unique / p4.size;
  console.log(
    `    4 键唯一率 ${(rate * 100).toFixed(1)}%（${unique}/${p4.size} 个前缀）`,
  );
  assert.ok(
    rate > 0.7 && rate < 0.85,
    `4 键唯一率 ${(rate * 100).toFixed(1)}% 偏离预期区间 70%-85%`,
  );
});

test("产品指标复核：3 键候选压力（实测 253，非计划的 316）", () => {
  // 316 同前缀 vs 8 位候选栏，是方案 H 的 🔴 级风险。
  //
  // ⚠ 计划里的 316 是**朴素 startswith 统计**，没有考虑 query_by_prefix 的补码
  // 规则。真实引擎返回 253，差的 63 条是前缀 "yi4" 下含 '.' 的编码
  // （yi44. / yi45. / yi45.b …）—— 3 位 prefix 不含 '.'，也不满足
  // `len(code)>5 and code[5]=='.'` 或 `len(prefix)==4 and prefix[3].isdigit()`，
  // 于是被补码分支挡掉，不进候选。
  //
  // 已用 Python 真引擎交叉验证：朴素统计 316、query_by_prefix 253，与 TS 一致。
  // 也就是说真实压力比计划估计的轻 20%，但 253 挤 8 位候选栏仍是硬问题。
  const p3 = new Set<string>();
  for (const entry of e.dataset.entries) {
    if (entry.code.length >= 3) p3.add(entry.code.slice(0, 3));
  }
  assert.equal(p3.size, 1296, "3 位前缀组数与计划值不符");

  let max = 0;
  let maxPrefix = "";
  for (const p of p3) {
    const n = e.queryByPrefix(p, 0, 1000).length;
    if (n > max) {
      max = n;
      maxPrefix = p;
    }
  }
  console.log(`    3 键最大候选数 ${max}（前缀 "${maxPrefix}"）`);
  assert.equal(maxPrefix, "yi4");
  assert.equal(max, 253, "3 键最大候选数应为 253（真引擎口径）");
});
