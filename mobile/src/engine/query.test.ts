/**
 * L1 Golden 比对 + L4 分支覆盖 + L5 顺序/分页不变量 + L6 非 BMP 专项。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { loadDataset } from "./dataset.ts";
import { queryByPrefix, queryPhrase } from "./query.ts";
import { toLegacy, type Candidate, type CandidateKind } from "./types.ts";
import { casesOf, runCases, assertRun } from "./golden.util.ts";

const ds = loadDataset();

test("L1 query_by_prefix 与 Python 引擎逐条一致", () => {
  const cases = casesOf("query_by_prefix");
  assert.ok(cases.length > 20000, `用例数异常：${cases.length}`);
  const r = runCases(cases, (args) =>
    queryByPrefix(
      ds,
      args[0] as string,
      args[1] as number,
      args[2] as number,
    ).map(toLegacy),
  );
  assertRun("query_by_prefix", r);
});

test("L4 分支覆盖：kind 四类全部命中", () => {
  // supaA 曾被误判为「死代码」（查的是 code[4]=='a' 而非 prefix[4]=='a'），
  // 这条断言确保它确实被覆盖到了。
  const counts = new Map<CandidateKind, number>();
  for (const c of casesOf("query_by_prefix")) {
    for (const cand of queryByPrefix(
      ds,
      c.args[0] as string,
      c.args[1] as number,
      c.args[2] as number,
    )) {
      counts.set(cand.kind, (counts.get(cand.kind) ?? 0) + 1);
    }
  }
  const kinds: CandidateKind[] = ["plain", "bumaDot", "bumaCode5", "supaA"];
  const missing = kinds.filter((k) => !counts.has(k));
  const summary = kinds.map((k) => `${k}=${counts.get(k) ?? 0}`).join(" ");
  assert.equal(
    missing.length,
    0,
    `未覆盖的分支: ${missing.join(", ")}（${summary}）`,
  );
  console.log(`    分支命中 ${summary}`);
});

test("L5-a 候选顺序 = 码表行序（lineNo 严格递增）", () => {
  // 防止有人顺手 sort()。候选顺序由 file_processor 排好（24 高频字首字置顶 +
  // sort_key 码值序），引擎任何地方都不得重排。
  for (const c of casesOf("query_by_prefix")) {
    const rs = queryByPrefix(
      ds,
      c.args[0] as string,
      c.args[1] as number,
      c.args[2] as number,
    );
    for (let i = 1; i < rs.length; i++) {
      assert.ok(
        rs[i]!.lineNo > rs[i - 1]!.lineNo,
        `行序错乱: prefix=${c.args[0]} 下标 ${i}`,
      );
    }
  }
});

test("L5-b 分页一致性：切片与整段取法结果相同", () => {
  const cases = casesOf("query_by_prefix").filter(
    (c) => (c.args[1] as number) === 0 && (c.args[2] as number) === 10,
  );
  for (const c of cases) {
    const p = c.args[0] as string;
    const all = queryByPrefix(ds, p, 0, 10);
    if (all.length < 3) continue;
    const head = queryByPrefix(ds, p, 0, 5);
    const mid = queryByPrefix(ds, p, 3, 5);
    assert.deepEqual(
      head.map(toLegacy),
      all.slice(0, 5).map(toLegacy),
      `首页不一致: prefix=${p}`,
    );
    assert.deepEqual(
      mid.map(toLegacy),
      all.slice(3, 8).map(toLegacy),
      `翻页不一致: prefix=${p}`,
    );
  }
});

test("L6 非 BMP 专项：152 条代理对字不被拆坏", () => {
  const nonBmp = ds.entries.filter((e) => e.word.codePointAt(0)! > 0xffff);
  assert.equal(nonBmp.length, 152);
  for (const e of nonBmp) {
    const hit = queryByPrefix(ds, e.code, 0, 10).find(
      (r) => r.lineNo === e.lineNo,
    );
    assert.ok(hit, `非 BMP 字未查到: ${e.word} (${e.code})`);
    assert.equal([...hit.text].length, 1, `text 非单码点: ${hit.text}`);
    assert.ok(
      !/\p{Surrogate}/u.test(hit.text),
      `text 含孤立代理项: ${JSON.stringify(hit.text)}`,
    );
    // legacy 拼串同样不能被拆坏
    assert.equal(toLegacy(hit), e.word + hit.rest);
  }
});

test("边界：空前缀 / 不存在的首字母 / count=0", () => {
  assert.deepEqual(queryByPrefix(ds, "", 0, 5), []);
  assert.deepEqual(queryByPrefix(ds, "0", 0, 5), []); // 首字母是数字，桶不存在
  assert.deepEqual(queryByPrefix(ds, ".", 0, 5), []);
  assert.deepEqual(queryByPrefix(ds, "ba1", 0, 0), []);
  // 起始下标超出结果数 → 空
  assert.deepEqual(queryByPrefix(ds, "ba1", 9999, 5), []);
});

test("queryPhrase：O(1) 查词，括号是协议的一部分", () => {
  // 取一个真实词条验证形态
  const [code, phrase] = [...ds.phraseIndex.entries()][0]!;
  assert.equal(queryPhrase(ds, code), "(" + phrase + ")");
  // 带空格输入应先去空格再查
  assert.equal(queryPhrase(ds, " " + code + " "), "(" + phrase + ")");
  // 不存在返回空串
  assert.equal(queryPhrase(ds, "zzzzzz"), "");
});

test("queryPhrase 覆盖全部 2003 个编码（与夹具一致）", () => {
  assert.equal(ds.phraseIndex.size, 2003);
  let n = 0;
  for (const code of ds.phraseIndex.keys()) {
    const out = queryPhrase(ds, code);
    assert.ok(out.startsWith("(") && out.endsWith(")"), `形态异常: ${out}`);
    n++;
  }
  assert.equal(n, 2003);
});
