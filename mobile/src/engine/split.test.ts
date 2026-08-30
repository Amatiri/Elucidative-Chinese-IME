/**
 * L1 层：split_sequence 的 Golden 比对 + L3 幂等不变量。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { splitSequence, getLastIterationCount, MAX_SPLIT_ITERATIONS } from "./split.ts";
import { casesOf, runCases, assertRun, loadGolden } from "./golden.util.ts";

test("L1 split_sequence 与 Python 引擎逐条一致", () => {
  const cases = casesOf("split_sequence");
  assert.ok(cases.length > 10000, `用例数异常：${cases.length}`);

  let maxIter = 0;
  const r = runCases(cases, (args) => {
    const out = splitSequence(args[0] as string);
    const it = getLastIterationCount();
    if (it > maxIter) maxIter = it;
    return out;
  });
  assertRun(`split_sequence`, r);

  // 死循环保护不应在正常数据上逼近上限
  assert.ok(
    maxIter * 4 < MAX_SPLIT_ITERATIONS,
    `最大迭代次数 ${maxIter} 已逼近上限 ${MAX_SPLIT_ITERATIONS}`,
  );
  console.log(`    最大迭代次数 ${maxIter} / 上限 ${MAX_SPLIT_ITERATIONS}`);
});

test("L3-a splitSequence 幂等：split(split(s)) === split(s)", () => {
  const cases = casesOf("split_sequence");
  const bad: string[] = [];
  for (const c of cases) {
    const s = c.args[0] as string;
    const once = splitSequence(s);
    const twice = splitSequence(once);
    if (once !== twice) {
      if (bad.length < 20) {
        bad.push(`${s} -> ${once} -> ${twice}`);
      }
    }
  }
  assert.equal(
    bad.length,
    0,
    `幂等性破坏 ${bad.length} 处：\n  ${bad.join("\n  ")}`,
  );
});

test("L3-b 字符守恒：split 只插入引号，不增删字符", () => {
  // 去掉所有引号后，输出的字符序列必须与输入完全相同。
  // 这是比形态检查强得多的不变量 —— 任何一处切分位置写错都会破坏它。
  //
  // 注意：不要断言「输出不以引号开头」。splitSequence("'") === "'" 是
  // Python 的真实行为（filter 掉空串后结果为空，再由 L169-170 的尾部引号
  // 补偿加回一个），Golden 已逐条验证通过。那是正确的，不是缺陷。
  const cases = casesOf("split_sequence");
  const bad: string[] = [];
  for (const c of cases) {
    const s = c.args[0] as string;
    const out = splitSequence(s);
    const strip = (x: string) => x.split("'").join("");
    if (strip(out) !== strip(s)) {
      if (bad.length < 20) {
        bad.push(`${JSON.stringify(s)} -> ${JSON.stringify(out)}`);
      }
    }
  }
  assert.equal(bad.length, 0, `字符不守恒 ${bad.length} 处：\n  ${bad.join("\n  ")}`);
});

test("L3-c 无连续引号（空串已在 L167 被过滤）", () => {
  const cases = casesOf("split_sequence");
  const bad: string[] = [];
  for (const c of cases) {
    const s = c.args[0] as string;
    const out = splitSequence(s);
    if (out.includes("''")) {
      if (bad.length < 20) {
        bad.push(`${JSON.stringify(s)} -> ${JSON.stringify(out)}`);
      }
    }
  }
  assert.equal(bad.length, 0, `出现连续引号 ${bad.length} 处：\n  ${bad.join("\n  ")}`);
});

test("L0-g 夹具与当前数据集同源", () => {
  const g = loadGolden();
  assert.equal(g.schema, "jieshu-golden/1");
  assert.equal(g.source.dictionary, 8152);
  assert.equal(g.source.ciyuLines, 1939);
  assert.equal(g.source.ciyuCodes, 2003);
});
