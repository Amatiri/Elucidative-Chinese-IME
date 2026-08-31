// 布局 / 部首表 / 状态切换 的逻辑级校验（直接吃构建产物，不依赖浏览器）
import { KEYMAP_ALL, COLS, KEY_BY_MAIN } from "../web/assets/ui/keymap.js";
import { RADICAL_TABLE } from "../web/assets/ui/radical.js";
import {
  initialState,
  setRadicalOpen,
  updateSettings,
  setSettingsOpen,
} from "../web/assets/ui/state.js";

let ok = true;
const fail = (m) => {
  console.log("FAIL:", m);
  ok = false;
};

// 1) 每行 span 之和必须等于 COLS(10)
KEYMAP_ALL.forEach((row, i) => {
  const sum = row.reduce((a, c) => a + c.span, 0);
  if (sum !== COLS) fail(`ROW ${i} span sum=${sum} != ${COLS}`);
});

// 2) Row6 必须是最后一行，且列宽比 = 🌐1/,1/空格5/.1/↵2
//    （语言切换键面 🌐、逗号键面半角「,」为用户 2026-08-31 定稿）
const row6 = KEYMAP_ALL[KEYMAP_ALL.length - 1];
const spans = row6.map((c) => c.span);
if (JSON.stringify(spans) !== JSON.stringify([1, 1, 5, 1, 2]))
  fail(`Row6 spans ${JSON.stringify(spans)} != [1,1,5,1,2]`);
const mains6 = row6.filter((c) => c.kind === "key").map((c) => c.def.main);
if (JSON.stringify(mains6) !== JSON.stringify(["🌐", ",", "空格", ".", "↵"]))
  fail(`Row6 mains ${JSON.stringify(mains6)}`);

// 3) KEY_BY_MAIN 无主字符冲突（size == 全部键数）
const totalKeys = KEYMAP_ALL.reduce(
  (n, row) => n + row.filter((c) => c.kind === "key").length,
  0,
);
if (KEY_BY_MAIN.size !== totalKeys)
  fail(`KEY_BY_MAIN size ${KEY_BY_MAIN.size} != totalKeys ${totalKeys}（存在主字符冲突）`);

// 3.5) ⌫ 必须带副字符「清」：上滑门控靠副字符存在才走 clearAll，
//      副字符一旦丢失，上滑会退化成单点退格 —— 清空功能静默失配（2026-08-31 教训）
const backspaceKey = KEY_BY_MAIN.get("⌫");
if (backspaceKey === undefined) fail("缺 ⌫ 键");
else {
  if (backspaceKey.idleSub !== "清") fail(`⌫ 副字符应为「清」，实际 ${JSON.stringify(backspaceKey.idleSub)}`);
  if (backspaceKey.swipe.kind !== "clearAll") fail(`⌫ 上滑应为 clearAll，实际 ${backspaceKey.swipe.kind}`);
}

// 4) 部首表：对齐 ime.py 实际为 26 组（25 声母字母 a–z 去 e + 0-9）；
//    计划正文误写 25，以 ime.py 为准
if (RADICAL_TABLE.length !== 26) fail(`RADICAL_TABLE len=${RADICAL_TABLE.length} != 26`);
const labels = RADICAL_TABLE.map((g) => g.label);
// 首组标签移动端为「笔画」（桌面端 ime.py 为 a(副)，仅标签差异），以用户定稿为准
if (!labels.includes("笔画")) fail("RADICAL_TABLE 缺 笔画");
if (!labels.includes("0-9")) fail("RADICAL_TABLE 缺 0-9");
// 每组的部首串非空
for (const g of RADICAL_TABLE)
  if (g.chars.length === 0) fail(`RADICAL_TABLE ${g.label} 空串`);

// 5) 状态切换：radicalOpen 只切布尔位，不碰 buffer / resolved / 候选
let st = initialState({ rows: 5, symbolSwipe: "abandon", autoCommit: true, phrasePriority: true, backspaceDeletesChar: true });
st = { ...st, buffer: "ba0", resolved: { 0: "八" }, page: 2 };
const before = JSON.stringify({ buffer: st.buffer, resolved: st.resolved, page: st.page });
st = setRadicalOpen(st, true);
if (!st.radicalOpen) fail("setRadicalOpen(true) 未置位");
const after = JSON.stringify({ buffer: st.buffer, resolved: st.resolved, page: st.page });
if (before !== after) fail(`radicalOpen 改动了编码/候选状态: ${before} -> ${after}`);
st = setRadicalOpen(st, false);
if (st.radicalOpen) fail("setRadicalOpen(false) 未清除");

// 6) 6 行切换：rows 改变，编码状态不变
st = updateSettings(st, { rows: 6 });
if (st.settings.rows !== 6) fail("rows 未切到 6");
if (st.buffer !== "ba0") fail("切 6 行时误改 buffer");
st = setSettingsOpen(st, true);
if (!st.settingsOpen) fail("设置面板未打开");

console.log(ok ? "VALIDATION_OK" : "VALIDATION_FAIL");
console.log(`rows=${KEYMAP_ALL.length}, totalKeys=${totalKeys}, radicalGroups=${RADICAL_TABLE.length}`);
