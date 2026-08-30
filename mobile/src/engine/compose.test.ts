/**
 * 组合层 Golden 比对 + 结构化契约。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { loadDataset } from "./dataset.ts";
import { getPhraseSegments, queryMultiChars, querySingleChar } from "./compose.ts";
import { queryByPrefix } from "./query.ts";
import { toLegacy } from "./types.ts";
import { casesOf, runCases, assertRun } from "./golden.util.ts";

const ds = loadDataset();

test("L1 get_phrase_segments 与 Python 引擎逐条一致", () => {
  const cases = casesOf("get_phrase_segments");
  assert.ok(cases.length > 3000, `用例数异常：${cases.length}`);
  const r = runCases(cases, (args) => {
    const s = getPhraseSegments(ds, args[0] as string);
    // 与 Python 的 (display, all_parts, sorted(literal_indices)) 三元组对齐
    return [s.display, s.allParts, s.literalIndices];
  });
  assertRun("get_phrase_segments", r);
});

test("L1 query_multi_chars 与 Python 引擎逐条一致", () => {
  const cases = casesOf("query_multi_chars");
  assert.ok(cases.length > 5000, `用例数异常：${cases.length}`);
  const r = runCases(cases, (args) =>
    queryMultiChars(ds, args[0] as string),
  );
  assertRun("query_multi_chars", r);
});

test("query_single_char：'/' 连接，与 queryByPrefix 一致", () => {
  // 夹具里没有单独跑 query_single_char（它就是 query_by_prefix 的拼串封装），
  // 这里验证封装形态，数据正确性由 queryByPrefix 的 2 万条用例保证。
  for (const p of ["ba", "ba1", "ba13", "b;1", "zzzz"]) {
    const viaSingle = querySingleChar(ds, p, 0, 5);
    const viaPrefix = queryByPrefix(ds, p, 0, 5);
    assert.equal(
      viaSingle,
      viaPrefix.length > 0 ? viaPrefix.map(toLegacy).join("/") : "",
      `prefix=${p}`,
    );
  }
  // 分页偏移
  assert.equal(
    querySingleChar(ds, "ba", 2, 3),
    queryByPrefix(ds, "ba", 2, 3).map(toLegacy).join("/"),
  );
});

test("L1-b 单字模式只出单字候选（预览串不混入）", () => {
  // 计划 §3.3：单字模式显示单字候选，判定式 ime.py:628
  // 这里验证引擎侧的基础保证：每个候选的 text 都是单码点汉字
  for (const p of ["ba", "ba1", "ba13", "d", "b;"]) {
    for (const c of queryByPrefix(ds, p, 0, 10)) {
      assert.equal([...c.text].length, 1, `候选非单字: ${JSON.stringify(c.text)}`);
    }
  }
});

test("L4-b get_phrase_segments 三类路径全部命中", () => {
  // 词语命中 / 单字预览 / 字面输出，三条路径都要覆盖到
  let phrase = 0;
  let chars = 0;
  let literal = 0;
  for (const c of casesOf("get_phrase_segments")) {
    const s = getPhraseSegments(ds, c.args[0] as string);
    if (s.literalIndices.length > 0) literal++;
    else if (s.display.length > 0) {
      // 预览非空：可能是词语命中或单字拼接
      if (s.allParts.length >= 1) {
        // 词语命中时 display 长度通常 >= 2 且不等于部件数
        if (s.display.length >= 2) phrase++;
        else chars++;
      }
    }
  }
  assert.ok(phrase > 0, "词语路径未命中");
  assert.ok(chars > 0, "单字路径未命中");
  assert.ok(literal > 0, "字面输出路径未命中");
  console.log(`    路径命中 词语=${phrase} 单字=${chars} 字面=${literal}`);
});

test("L6-b 非 BMP 字在多字预览中不被拆成半个代理项", () => {
  const nonBmp = ds.entries.filter((e) => e.word.codePointAt(0)! > 0xffff);
  assert.equal(nonBmp.length, 152);
  for (const e of nonBmp.slice(0, 50)) {
    // 用完整编码查，取首字应得到完整汉字
    const out = queryMultiChars(ds, e.code);
    assert.equal(out, e.word, `预览首字被拆坏: ${e.code}`);
    assert.ok(!/\p{Surrogate}/u.test(out), `含孤立代理项: ${JSON.stringify(out)}`);
  }
});

test("契约：literalIndices 升序且不越界", () => {
  for (const c of casesOf("get_phrase_segments")) {
    const s = getPhraseSegments(ds, c.args[0] as string);
    for (let i = 1; i < s.literalIndices.length; i++) {
      assert.ok(
        s.literalIndices[i]! > s.literalIndices[i - 1]!,
        `literalIndices 未升序: ${c.args[0]}`,
      );
    }
    for (const idx of s.literalIndices) {
      assert.ok(idx < s.allParts.length, `下标越界: ${idx} >= ${s.allParts.length}`);
    }
  }
});
