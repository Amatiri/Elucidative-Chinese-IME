/**
 * L8 键位分档测试。
 *
 * 这一层保护的是**产品语义**而非算法正确性：
 *  ① 没有任何键会被判为「不可点」（运行时只有 content / empty 两档）。
 *     把空码区画成禁用，会让 ba5o=𠀧 这类已在码表里的字永远输不出来，
 *     并砍掉规则 §六 的「可自定义」卖点。
 *  ② 副码 / 补码引导符 / 补码的位序口径不能混淆（见 charclass.ts 文件末 note）。
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { loadDataset } from "./dataset.ts";
import { groupByClass, nextCharClass, ruleForbiddenAt } from "./charclass.ts";
import { CODE_CHARS } from "./constants.ts";

const ds = loadDataset();

/** 去掉 ' —— 它是手动分段符，不属于任一码位的字符集 */
const noQuote = (s: string[]) => s.filter((c) => c !== "'");

test("L8-a 第 1 位声母：24 个（无 a/e，含 o），无空码区", () => {
  const g = groupByClass(ds, "");
  const content = noQuote(g.content).sort().join("");
  assert.equal(content, "bcdfghijklmnopqrstuvwxyz", "声母集合不符");
  assert.equal(content.length, 24);
  assert.ok(content.includes("o"), "「哦」以 o 开头，o 必须可用");
  assert.ok(!content.includes("a") && !content.includes("e"), "§二 零声母归 o，a/e 不作声母");
  // 段首无意义的字符落 empty：可点、直出原编码，但不会被判为不可点
  for (const ch of "ae0123456789;.") {
    assert.ok(g.empty.includes(ch), `段首 ${ch} 应为 empty（无候选 → 直出原编码）`);
  }
  // 规则知识层面仍然记录它们不被允许（供真值表使用）
  assert.equal(ruleForbiddenAt(0), "ae0123456789;'.");
});

test("L8-b 第 2 位空码区是上下文相关的（拼音缺失区）", () => {
  const gb = groupByClass(ds, "b");
  const gf = groupByClass(ds, "f");
  assert.equal(noQuote(gb.content).length, 17, "b 声母应有 17 个韵母有内容");
  assert.equal(noQuote(gf.content).length, 9, "f 声母应有 9 个韵母有内容");
  // 只看字母部分：数字与 . 在韵母位恒为 empty（规则上也不接受）
  const lettersOf = (g: ReturnType<typeof groupByClass>) =>
    g.empty.filter((c) => /[a-z;]/.test(c)).sort().join("");
  assert.equal(lettersOf(gb), "bepqrstvwy", "b 的空码韵母集合不符");
  // 两者空码集合必须不同 —— 这就是「不能用静态样式表」的证据
  assert.notEqual(
    lettersOf(gb),
    lettersOf(gf),
    "不同声母的空码区必须不同，否则说明退化成了静态判定",
  );
  assert.equal(ruleForbiddenAt(1), "0123456789.", "韵母位规则上不接受数字与 .");
});

test("L8-c 【核心】任何前缀下都不存在「不可点」的键", () => {
  // 运行时只有 content / empty 两档。这条断言把「不吞键」固化成契约：
  // 无候选时按 ime.py 语义直出原编码，UI 不得抖动拒绝。
  const prefixes = new Set<string>();
  for (const entry of ds.entries) {
    if (entry.code.length >= 2) prefixes.add(entry.code.slice(0, 2));
  }
  for (const p of prefixes) {
    const map = nextCharClass(ds, p);
    for (const ch of CODE_CHARS) {
      const cls = map.get(ch);
      assert.ok(
        cls === "content" || cls === "empty",
        `prefix=${p} ch=${ch} 分档为 ${cls}，运行时不允许出现第三档`,
      );
    }
  }
  // 规则知识层面：调码位不禁用 5-9（§六 声调缺失区）
  assert.ok(!ruleForbiddenAt(2).includes("5"), "§六 调码 5-9 是空码区，规则上不禁用");
  console.log(`    已验证 ${prefixes.size} 个音节前缀 × ${CODE_CHARS.length} 键，无不可点键`);
});

test("L8-d 疏散区实证：yi+8 = content，ba+5 = content", () => {
  assert.equal(nextCharClass(ds, "yi").get("8"), "content", "yi8 是 yi4 的疏散区，12 条");
  assert.equal(nextCharClass(ds, "ba").get("5"), "content", "ba5 有 1 条（ba5o=𠀧）");
  // 同一个 8，在 ba 下却是空码区 —— 上下文相关的直接证据
  assert.equal(nextCharClass(ds, "ba").get("8"), "empty", "ba8 无字，应为空码区而非 content");
});

test("L8-e 第 4 位主码：a / e / ; 规则上禁用，运行时仍不可拒绝输入", () => {
  const g = groupByClass(ds, "ba1");
  for (const ch of "ae;") {
    assert.ok(g.empty.includes(ch), `主码 ${ch} 无候选 → empty，但仍可点`);
  }
  assert.equal(ruleForbiddenAt(3), "ae;.", "§三.4 明文禁用主码 a/e/;");
  // 交叉验证：码表第 4 位实测 0 条
  let hits = 0;
  for (const entry of ds.entries) {
    if (entry.code.length >= 4 && "ae;".includes(entry.code[3]!)) hits++;
  }
  assert.equal(hits, 0, "码表第 4 位不应出现 a/e/;");
});

test("L8-f 第 5 位副码：a = 占空码，必须是 content", () => {
  // 规则 §四：需要占位时用 a 作占空码，在码表中省略不写。
  // 故码表 0 条，但输入 a 合法 —— 引擎 prefix[4]==='a' 分支即此规则。
  assert.equal(nextCharClass(ds, "ba13").get("a"), "content", "a 是占空码，输入合法");
  let hits = 0;
  for (const entry of ds.entries) {
    if (entry.code.length >= 5 && entry.code[4] === "a") hits++;
  }
  assert.equal(hits, 0, "占空码 a 在码表中省略不写，应 0 条");
});

test("L8-g 不变量：两档互斥，并集恰为 CODE_CHARS", () => {
  for (const p of ["", "b", "ba", "ba1", "ba13", "ba13.", "yi4", "d.", "ba'"]) {
    const g = groupByClass(ds, p);
    const total = g.content.length + g.empty.length;
    assert.equal(total, CODE_CHARS.length, `prefix=${JSON.stringify(p)} 分档总数不等于字符集`);
    const all = new Set([...g.content, ...g.empty]);
    assert.equal(all.size, CODE_CHARS.length, `prefix=${JSON.stringify(p)} 存在重复分档`);
  }
});

test("L8-h 交叉验证：拼音缺失区总量 = 235 组合（36.3%）", () => {
  // 与 Python 侧独立统计对齐：24 声母 × 27 韵母位字符 = 648，有内容 413。
  const shengmu = "bcdfghijklmnopqrstuvwxyz";
  const yunmuChars = new Set<string>();
  for (const entry of ds.entries) {
    if (entry.code.length >= 2) yunmuChars.add(entry.code[1]!);
  }
  let contentCnt = 0;
  let emptyCnt = 0;
  for (const s of shengmu) {
    const map = nextCharClass(ds, s);
    for (const y of yunmuChars) {
      const cls = map.get(y);
      if (cls === "content") contentCnt++;
      else if (cls === "empty") emptyCnt++;
    }
  }
  const total = shengmu.length * yunmuChars.size;
  console.log(
    `    ${shengmu.length}×${yunmuChars.size}=${total}：有内容 ${contentCnt}，空码区 ${emptyCnt}（${((emptyCnt / total) * 100).toFixed(1)}%）`,
  );
  assert.equal(total, 648, "理论组合数应为 648");
  assert.equal(contentCnt, 413, "有内容组合应为 413");
  assert.equal(emptyCnt, 235, "拼音缺失区应为 235");
});

test("L8-i 每档都非空且规模合理（防止逻辑退化成全 content）", () => {
  const g = groupByClass(ds, "ba1");
  assert.ok(g.content.length > 0, "content 不应为空");
  assert.ok(g.empty.length > 0, "empty 不应为空");
  // 主码位：a / e / ; / . 恒无候选（§三.4 明文禁用），落 empty。
  // 注意数字**不能**这样断言 —— 0-9 是合法的独体构形码（如 ba13 = 八）。
  for (const ch of "ae;.") {
    assert.ok(g.empty.includes(ch), `主码位 ${ch} 应无候选`);
  }
  // 有候选的主码（部首码字母）不得落 empty
  for (const ch of noQuote(g.content)) {
    assert.ok(!g.empty.includes(ch), `${ch} 同时出现在两档`);
  }
  assert.equal(ruleForbiddenAt(3), "ae;.", "§三.4 明文禁用主码 a/e/;");
});

test("L8-j 【口径】副码 / 引导符 / 补码的位序与计数", () => {
  // 副码与补码都可省略，靠 '.' 引导符区分：引导符前为副码，后为补码。
  // 因此「第 5 位是 '.'」= 无副码（a 占位省略）+ 补码引导提前，
  // 统计上必须归到第 6 位引导，绝不能记进副码。
  // 位序：ABCD / ABCDE / ABCD. / ABCD.F / ABCDE. / ABCDE.F
  const shape = new Map<string, number>();
  let fuma = 0; // 逻辑第 5 位副码（真出现）
  let daoyin = 0; // 逻辑第 6 位引导符
  let buma = 0; // 逻辑第 7 位补码 F

  for (const entry of ds.entries) {
    const c = entry.code;
    const dot = c.indexOf(".");
    const key =
      dot === -1
        ? c.length === 4
          ? "ABCD"
          : "ABCDE"
        : dot === 4
          ? c.length === 5
            ? "ABCD."
            : "ABCD.F"
          : c.length === 6
            ? "ABCDE."
            : "ABCDE.F";
    shape.set(key, (shape.get(key) ?? 0) + 1);

    // 副码存在 ⟺ 物理第 5 位是字母（不是引导符）。4 位码 ABCD 无副码。
    if (c.length >= 5 && c[4] !== ".") fuma++;
    if (dot !== -1) daoyin++;
    if (dot !== -1 && c.length > dot + 1) buma++;
  }

  assert.equal(shape.get("ABCD"), 5935, "ABCD 条数不符");
  assert.equal(shape.get("ABCDE"), 1908, "ABCDE 条数不符");
  assert.equal(shape.get("ABCD."), 131, "ABCD. 条数不符");
  assert.equal(shape.get("ABCD.F"), 103, "ABCD.F 条数不符");
  assert.equal(shape.get("ABCDE."), 31, "ABCDE. 条数不符");
  assert.equal(shape.get("ABCDE.F"), 44, "ABCDE.F 条数不符");

  // 副码 = 1908 + 31 + 44；而非「第 5 位字符数 2039」（那把 131 条引导符算进去了）
  assert.equal(fuma, 1983, "副码应只统计逻辑第 5 位为字母者");
  assert.equal(daoyin, 309, "引导符总数应为 234 + 75");
  assert.equal(buma, 147, "补码 F 应为 103 + 44");

  // 反例固化：把第 5 位的 '.' 计进副码 = 234 条，是错误口径
  let dotAt5 = 0;
  for (const entry of ds.entries) {
    if (entry.code[4] === ".") dotAt5++;
  }
  assert.equal(dotAt5, 234, "物理第 5 位为 '.' 的条数（该数不得计入副码）");
  assert.notEqual(fuma, 2039, "2039 是把 131 条引导符误并入副码的旧口径");

  // 规则层面：副码位不接受数字，但 '.' 是合法的（它是引导符，不是副码）
  assert.equal(ruleForbiddenAt(4), "0123456789");
  assert.ok(!ruleForbiddenAt(4).includes("."), "引导符在第 5 位合法，不得列为禁用");
});
