/**
 * 自动分词：把连续编码切成部件，用单引号分隔。
 *
 * 与 Python dictionary_frontend.py:103-171 split_sequence 逐行等价。
 * 这是整个引擎里分支最多、最易译错的函数，每处索引边界都标注了对应行号。
 */

import { isAsciiDigit } from "./constants.ts";

/**
 * 死循环保护。
 *
 * condition1/2/3 每命中一次就置 canSplitMore=true，而 condition2 的插入点
 * `pos-2` 可能产生空前缀段，理论上存在振荡风险。加硬上限并抛错，
 * 而不是静默截断 —— 截断会产出与 Python 不同的结果且难以察觉。
 */
export const MAX_SPLIT_ITERATIONS = 64;

let lastIterationCount = 0;

/** 最近一次 splitSequence 的迭代次数，供测试统计最大值（验证死循环保护不误触发） */
export function getLastIterationCount(): number {
  return lastIterationCount;
}

export function splitSequence(original: string): string {
  let parts = original.split("'");
  let canSplitMore = true;
  let iterations = 0;

  while (canSplitMore) {
    if (++iterations > MAX_SPLIT_ITERATIONS) {
      throw new Error(
        `splitSequence 迭代超过 ${MAX_SPLIT_ITERATIONS} 次，疑似死循环：${JSON.stringify(original)}`,
      );
    }
    canSplitMore = false;
    const newParts: string[] = [];

    for (const part of parts) {
      let condition1 = false; // 连续双拼
      let condition2 = false; // 调码定位
      let condition3 = false; // 独体字四码打全
      let condition4 = false; // 合体字五码打全
      let condition5 = false; // 补码打全
      const positions: number[] = []; // condition2 插入位置
      const positions3: number[] = []; // condition3 插入位置

      // L123-124：片段内无数字且长度 > 2 → 按每 2 字符切分
      if (!hasDigit(part) && part.length > 2) {
        condition1 = true;
      }

      for (let index = 0; index < part.length; index++) {
        const ch = part[index]!;
        // L126：index > 2 且前一位不是数字
        if (isAsciiDigit(ch) && index > 2 && !isAsciiDigit(part[index - 1]!)) {
          condition2 = true;
          positions.push(index);
        }
        // L129-133：index > 0 且前一位是数字，且后一位既不是 '.' 也不是数字
        if (
          isAsciiDigit(ch) &&
          index > 0 &&
          isAsciiDigit(part[index - 1]!) &&
          index + 1 < part.length
        ) {
          const next = part[index + 1]!;
          if (next !== "." && !isAsciiDigit(next)) {
            condition3 = true;
            positions3.push(index);
          }
        }
      }

      // L134：长度 > 5 且不含 '.'
      if (part.length > 5 && part.indexOf(".") === -1) {
        condition4 = true;
      }
      // L136：含 '.' 且 len(part.split(".")[1]) > 1
      //
      // ⚠ 必须是「第 1 个与第 2 个 '.' **之间**的子串」，不是「第 1 个 '.' 之后
      // 的全部字符」。两者只在只有一个 '.' 时等价 —— 对 "..8"：
      //   split(".") === ["", "", "8"] → [1] === ""       → 长度 0，不触发
      //   length - indexOf - 1        === 2（即 ".8"）     → 会误触发
      // 这个差异曾被误判为等价，是 Golden 夹具跑出来的 6 条不符定位到的。
      const dotIdx = part.indexOf(".");
      if (dotIdx !== -1) {
        const secondDot = part.indexOf(".", dotIdx + 1);
        const between =
          secondDot === -1
            ? part.slice(dotIdx + 1)
            : part.slice(dotIdx + 1, secondDot);
        if (between.length > 1) {
          condition5 = true;
        }
      }

      if (condition1) {
        // L140：每 2 字符切一段；奇数长度时末段为 1 个字符
        for (let i = 0; i < part.length; i += 2) {
          newParts.push(part.slice(i, i + 2));
        }
        canSplitMore = true;
      } else if (condition2) {
        // L143-147：在 pos-2 处插入，从后往前插以免位移。pos-2 可能为 0（产生空前缀段）
        let newPart = part;
        for (const pos of [...positions].sort((a, b) => b - a)) {
          newPart = newPart.slice(0, pos - 2) + "'" + newPart.slice(pos - 2);
        }
        newParts.push(...newPart.split("'"));
        canSplitMore = true;
      } else if (condition3) {
        // L149-153：在 pos+1 处插入（方向与前一条相反）
        let newPart = part;
        for (const pos of [...positions3].sort((a, b) => b - a)) {
          newPart = newPart.slice(0, pos + 1) + "'" + newPart.slice(pos + 1);
        }
        newParts.push(...newPart.split("'"));
        canSplitMore = true;
      } else if (condition4) {
        // L155-157：第 5 位后断开
        const newPart = part.slice(0, 5) + "'" + part.slice(5);
        newParts.push(...newPart.split("'"));
        canSplitMore = true;
      } else if (condition5) {
        // L159-162：ff = 第一个 '.' 的下标 + 2
        const ff = part.indexOf(".") + 2;
        const newPart = part.slice(0, ff) + "'" + part.slice(ff);
        newParts.push(...newPart.split("'"));
        canSplitMore = true;
      } else {
        newParts.push(part);
      }
    }

    parts = newParts;
  }

  lastIterationCount = iterations;

  // L167：过滤空串（只在这里过滤，中途的空串要参与后续条件判断）
  parts = parts.filter((p) => p !== "");
  let result = parts.join("'");

  // L169-170：原始串以 ' 结尾但结果不以 ' 结尾时补回。
  // 判据是 **原始 original**，不是 parts。
  if (original.endsWith("'") && !result.endsWith("'")) {
    result += "'";
  }
  return result;
}

function hasDigit(part: string): boolean {
  for (const ch of part) {
    if (isAsciiDigit(ch)) return true;
  }
  return false;
}
