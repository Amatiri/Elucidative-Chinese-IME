/**
 * L0 层：数据契约验证。
 *
 * 目的不是测引擎，是防数据文件过期 —— 码表一变而数据没重新生成，这里立刻红。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { DATASET } from "../data/dataset.ts";
import { parseEntries, buildBuckets, loadDataset } from "./dataset.ts";
import { isCodeChar } from "./constants.ts";

const ds = loadDataset();

test("L0-1 条目数与声明一致", () => {
  assert.equal(ds.entries.length, 8152);
  assert.equal(ds.entries.length, ds.entryCount);
});

test("L0-2 词语数与 ciyu 编码数", () => {
  assert.equal(ds.phraseCount, 1939);
  assert.equal(ds.codeCount, 2003);
  assert.equal(ds.phraseIndex.size, 2003);
});

test("L0-3 非 BMP 条目数（152 条，UTF-16 代理对）", () => {
  assert.equal(ds.nonBmpCount, 152);
  const actual = ds.entries.filter(
    (e) => [...e.word].length !== 1 || e.word.codePointAt(0)! > 0xffff,
  );
  assert.equal(actual.length, 152);
});

test("L0-4 每个 word 都是单码点且不含编码字符", () => {
  for (const e of ds.entries) {
    assert.equal([...e.word].length, 1, `word 非单码点: ${JSON.stringify(e.word)}`);
    assert.ok(!isCodeChar(e.word), `word 含编码字符: ${e.word}`);
  }
});

test("L0-5 每个 code 只含编码字符，且全表唯一", () => {
  const seen = new Set<string>();
  for (const e of ds.entries) {
    for (const ch of e.code) {
      assert.ok(isCodeChar(ch), `code 含非法字符: ${e.code}`);
    }
    assert.ok(!seen.has(e.code), `编码重复: ${e.code}`);
    seen.add(e.code);
  }
  assert.equal(seen.size, 8152);
});

test("L0-6 桶内保持行序（候选顺序的唯一依据）", () => {
  for (const [key, arr] of ds.buckets) {
    for (let i = 1; i < arr.length; i++) {
      assert.ok(
        arr[i]!.lineNo > arr[i - 1]!.lineNo,
        `桶 "${key}" 行序错乱于下标 ${i}`,
      );
    }
  }
});

test("L0-7 桶集合 = 去重首字母集合", () => {
  const firsts = new Set(ds.entries.map((e) => e.code[0]!));
  assert.equal(ds.buckets.size, firsts.size);
  // 第 1 位是声母，24 个字母（无 a/e/o）—— 数值由实测固定，变了说明码表结构变了
  assert.equal(ds.buckets.size, 24);
});

test("L0-8 sourceSha 格式", () => {
  assert.match(ds.sourceSha, /^[0-9a-f]{16}$/);
});

test("L0-9 flat 解析 round-trip：拼回原串应逐字节一致", () => {
  const rebuilt = ds.entries.map((e) => e.word + e.code).join(",");
  assert.equal(rebuilt, DATASET.entries);
});

test("L0-10 parseEntries 与 buildBuckets 可独立使用（合成用例需要）", () => {
  const es = parseEntries("甲ab1c,乙de2f");
  assert.equal(es.length, 2);
  assert.deepEqual(es[0], { word: "甲", code: "ab1c", lineNo: 0 });
  assert.deepEqual(es[1], { word: "乙", code: "de2f", lineNo: 1 });
  const b = buildBuckets(es);
  assert.equal(b.size, 2);
  assert.equal(b.get("a")!.length, 1);
  assert.equal(b.get("d")!.length, 1);
});

test("L0-11 非 BMP 解析不产生孤立代理项", () => {
  // 𠀧 是 U+20027，UTF-16 下 length === 2
  const es = parseEntries("𠀧ba5o");
  assert.equal(es.length, 1);
  assert.equal(es[0]!.word, "𠀧");
  assert.equal(es[0]!.code, "ba5o");
  assert.equal(es[0]!.word.length, 2); // UTF-16 码元数
  assert.equal([...es[0]!.word].length, 1); // 码点数
});
