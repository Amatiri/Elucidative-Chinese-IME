/**
 * Golden 夹具读取与比对工具。
 *
 * 夹具由 tools/gen_golden.py 用 Python 真引擎 dump 生成，是「TS 与 Python 行为一致」
 * 的唯一裁决依据。任何一条不符都是移植 bug，不是夹具问题 —— 除非码表变了，
 * 那种情况由 source 字段的断言拦下。
 */

import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

export interface GoldenCase {
  id: string;
  fn: string;
  args: unknown[];
  out: unknown;
}

export interface GoldenFile {
  schema: string;
  source: {
    dictionary: number;
    ciyuLines: number;
    ciyuCodes: number;
    sourceSha: string;
    seed: number;
  };
  meta: { deviations: string[]; notes: string[] };
  cases: GoldenCase[];
}

const GOLDEN_PATH = fileURLToPath(
  new URL("../../tests/golden_v1.json", import.meta.url),
);

let cached: GoldenFile | null = null;

export function loadGolden(): GoldenFile {
  if (cached === null) {
    cached = JSON.parse(readFileSync(GOLDEN_PATH, "utf-8")) as GoldenFile;
  }
  return cached;
}

/** 按函数名取用例 */
export function casesOf(fn: string): GoldenCase[] {
  return loadGolden().cases.filter((c) => c.fn === fn);
}

export interface RunResult {
  total: number;
  failed: number;
  /** 最多 20 条，避免几万条失败把日志淹没 */
  samples: string[];
}

/** 结构化比较。字符串与数组都适用，不依赖引用相等。 */
export function deepEq(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/**
 * 逐条比对，收集失败样例。
 * 不逐条 assert —— 几万条用例下 assert 的开销和日志都不可接受。
 */
export function runCases(
  cases: GoldenCase[],
  invoke: (args: unknown[]) => unknown,
  maxSamples = 20,
): RunResult {
  const samples: string[] = [];
  let failed = 0;
  for (const c of cases) {
    let actual: unknown;
    try {
      actual = invoke(c.args);
    } catch (e) {
      failed++;
      if (samples.length < maxSamples) {
        samples.push(`${c.id}\n    抛异常: ${(e as Error).message}`);
      }
      continue;
    }
    if (!deepEq(actual, c.out)) {
      failed++;
      if (samples.length < maxSamples) {
        samples.push(
          `${c.id}\n    期望 ${JSON.stringify(c.out)}\n    实际 ${JSON.stringify(actual)}`,
        );
      }
    }
  }
  return { total: cases.length, failed, samples };
}

/** 把 RunResult 转成断言。有失败就抛出并附上样例。 */
export function assertRun(label: string, r: RunResult): void {
  if (r.failed > 0) {
    throw new Error(
      `${label}: ${r.failed}/${r.total} 条不符\n  ` + r.samples.join("\n  "),
    );
  }
}
