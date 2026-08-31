/**
 * DOM 渲染。首次 mount 建结构，之后只改文本与 class，不重建节点。
 *
 * 【三区职责】对齐 ime.py 外输模式的 update_display()：
 *   目标输入框 = 已上屏文本 + 正在输入的编码（下划线）
 *   左上小显示区 = 最后输入的一个字符；空闲态显示大小写档位「小 / 大 / 连」
 *   中间候选区 = 单字态出单字候选；多字态**不出单字候选**，改出多字预览串 + 词语
 */

import { KEYMAP_ALL, subTextOf } from "./keymap.ts";
import { RADICAL_TABLE } from "./radical.ts";
import { CAPS_LABEL, type KeyClass, type KeyDef, type KeyboardState, type Settings } from "./types.ts";
import type { ViewModel } from "./view.ts";

export interface Handlers {
  onKeyTap(def: KeyDef): void;
  onKeySwipe(def: KeyDef): void;
  onCandidateTap(index: number): void;
  onPage(delta: number): void;
  /** 点击多字预览串（首选字组合）→ 上屏该串 */
  onPreviewTap(): void;
  /** 点击括号内的词语 → 上屏词语 */
  onPhraseTap(): void;
  onSettingsChange(patch: Partial<Settings>): void;
  onCloseSettings(): void;
  /** 关闭部件表浮层（状态保留） */
  onRadicalClose(): void;
}

export interface Renderer {
  update(st: KeyboardState, view: ViewModel): void;
}

const PAGE_SIZE = 5;

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  cls?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (cls !== undefined) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}

export function mount(
  root: { keyboard: HTMLElement; output: HTMLElement; sheet: HTMLElement },
  h: Handlers,
): Renderer {
  const keyEls = new Map<string, HTMLElement>();

  const lastRowIdx = KEYMAP_ALL.length - 1;
  let row6El: HTMLElement | null = null;

  // 始终按全量布局（5 行 + Row6）构建 DOM；Row6 在 5 行模式下隐藏
  for (let ri = 0; ri < KEYMAP_ALL.length; ri++) {
    const row = KEYMAP_ALL[ri]!;
    const rowEl = el("div", "kb-row");
    if (ri === lastRowIdx) {
      rowEl.classList.add("kb-row-6");
      row6El = rowEl;
    }

    for (const cell of row) {
      if (cell.kind === "display") {
        rowEl.append(el("div", "kb-display"));
        continue;
      }

      if (cell.kind === "candidate") {
        const bar = el("div", "kb-candidates");
        const list = el("div", "kb-cand-list");
        for (let i = 0; i < PAGE_SIZE; i++) {
          const item = el("button", "kb-cand");
          item.type = "button";
          item.append(el("span", "kb-cand-text"), el("span", "kb-cand-rest"));
          item.addEventListener("click", () => h.onCandidateTap(i));
          list.append(item);
        }
        bar.append(list, el("div", "kb-preview-strip"));
        rowEl.append(bar);
        continue;
      }

      const def = cell.def;
      const key = el("div", "kb-key");
      // span 交给 grid：Row6 空格 5U / 回车 2U 靠它生效；span 1 走默认，不写多余样式
      if (cell.span !== 1) key.style.gridColumn = `span ${cell.span}`;
      key.dataset["main"] = def.main;
      if (def.code !== undefined) key.dataset["code"] = def.code;
      key.append(el("span", "kb-main", def.main), el("span", "kb-sub"));
      // 页码挂在翻页键底部（设计建议位之一）
      if (def.main === "∨") key.append(el("span", "kb-page"));
      rowEl.append(key);
      keyEls.set(def.main, key);
    }

    root.keyboard.append(rowEl);
  }

  const displayEl = root.keyboard.querySelector<HTMLElement>(".kb-display");
  const candEls = [...root.keyboard.querySelectorAll<HTMLElement>(".kb-cand")];
  const listEl = root.keyboard.querySelector<HTMLElement>(".kb-cand-list");
  const stripEl = root.keyboard.querySelector<HTMLElement>(".kb-preview-strip");
  const pageEl = root.keyboard.querySelector<HTMLElement>(".kb-page");

  const sheet = buildSheet(h);
  root.sheet.append(sheet.frag);

  // 部件表浮层：覆盖在键盘之上，等比高，状态开关不触碰编码 / 候选
  const radical = buildRadical(h);
  root.keyboard.append(radical.el);

  return {
    update(st, view) {
      renderOutput(root.output, st, view);
      renderDisplay(displayEl, st, view);
      renderCandidates(listEl, stripEl, candEls, view, h);
      if (pageEl !== null) pageEl.textContent = view.pageLabel;

      // 6 行布局：Row6 按设置显隐（高度随之变化）
      if (row6El !== null) row6El.hidden = st.settings.rows !== 6;
      // 部件表浮层：覆盖键盘但不改动任何键盘状态
      radical.el.hidden = !st.radicalOpen;

      for (const [main, node] of keyEls) {
        const def = findDef(main);
        if (def === undefined) continue;
        // 开关类键按当前值高亮，让「字 / 词」的开与关一眼可见
        const on = def.swipe.kind === "toggle" && st.settings[def.swipe.key] ? " is-on" : "";
        node.className = "kb-key " + classify(def, view) + on;
        const sub = node.querySelector<HTMLElement>(".kb-sub");
        if (sub !== null) {
          // 显示规则与上滑门控共用 subTextOf（keymap.ts），两处不允许各自漂移
          sub.textContent = subTextOf(def, view.coding, st.settings.rows);
        }
        const mainEl = node.querySelector<HTMLElement>(".kb-main");
        if (mainEl !== null) mainEl.textContent = displayMain(def, st);
      }

      // 面板是 mount 时建好的，update 只改 class —— 不回写的话
      // radio / checkbox 会一直停在「全部未选中」的初始状态
      syncSheet(sheet.ctl, st.settings);
      root.sheet.classList.toggle("is-open", st.settingsOpen);
    },
  };
}

/**
 * 目标输入框：已上屏文本 + 正在输入的编码（下划线）+ 光标。
 *
 * 有编码时光标落在**编码串内部**（ime.py 的外输模式支持在编码中间插入字符），
 * 没有编码时才落在已上屏文本里。
 */
function renderOutput(out: HTMLElement, st: KeyboardState, view: ViewModel): void {
  const chars = [...st.committed];
  const before = chars.slice(0, st.cursor).join("");
  const after = chars.slice(st.cursor).join("");

  out.classList.toggle("is-empty", st.committed.length === 0 && view.code.length === 0);
  out.replaceChildren();

  if (before.length > 0) out.append(el("span", "out-text", before));

  if (view.code.length > 0) {
    const at = Math.min(Math.max(st.codeCursor, 0), view.code.length);
    const head = view.code.slice(0, at);
    const tail = view.code.slice(at);
    if (head.length > 0) out.append(el("span", "out-code", head));
    out.append(el("span", "out-caret"));
    if (tail.length > 0) out.append(el("span", "out-code", tail));
  } else {
    out.append(el("span", "out-caret"));
  }

  if (after.length > 0) out.append(el("span", "out-text", after));
}

/** 左上小显示区：编码态显示最后输入的字符，空闲态显示大小写档位 */
function renderDisplay(node: HTMLElement | null, st: KeyboardState, view: ViewModel): void {
  if (node === null) return;
  node.className = "kb-display";
  if (view.coding) {
    node.append();
    node.textContent = view.lastChar;
    node.classList.add("has-char");
  } else {
    node.textContent = CAPS_LABEL[st.caps];
    node.classList.add(`mode-${st.caps}`);
  }
}

/** 中间候选区：单字态出 5 条候选，多字态出预览串 + 词语 */
function renderCandidates(
  list: HTMLElement | null,
  strip: HTMLElement | null,
  candEls: HTMLElement[],
  view: ViewModel,
  h: Handlers,
): void {
  const multiNoSelect = view.mode === "multi" && !view.selecting;

  if (list !== null) list.hidden = multiNoSelect;
  if (strip !== null) strip.hidden = !multiNoSelect;

  // 多字态下始终刷新预览条：逐字选择期间它虽被隐藏，重新显示时不能留旧值。
  // 预览串与词语都是按钮 —— 点哪个上屏哪个（ime.py 里「!」上屏词语，这里补上直接点选）
  if (strip !== null && view.mode === "multi") {
    strip.replaceChildren();
    if (view.preview.length > 0) {
      const btn = el("button", "pv-text", view.preview);
      btn.type = "button";
      btn.addEventListener("click", h.onPreviewTap);
      strip.append(btn);
    }
    if (view.phrase.length > 0) {
      const btn = el("button", "pv-phrase", view.phrase);
      btn.type = "button";
      btn.addEventListener("click", h.onPhraseTap);
      strip.append(btn);
    }
  }

  if (multiNoSelect) return;

  candEls.forEach((node, i) => {
    const c = view.candidates[i];
    const textNode = node.querySelector<HTMLElement>(".kb-cand-text");
    const restNode = node.querySelector<HTMLElement>(".kb-cand-rest");
    if (textNode === null || restNode === null) return;
    if (c === undefined) {
      node.classList.add("is-empty");
      textNode.textContent = "";
      restNode.textContent = "";
      return;
    }
    node.classList.remove("is-empty");
    textNode.textContent = c.text;
    restNode.textContent = c.rest;
  });
}

function findDef(main: string): KeyDef | undefined {
  for (const row of KEYMAP_ALL) {
    for (const cell of row) {
      if (cell.kind === "key" && cell.def.main === main) return cell.def;
    }
  }
  return undefined;
}

function displayMain(def: KeyDef, st: KeyboardState): string {
  if (!/^[A-Za-z]$/.test(def.main)) return def.main;
  return st.caps === "lower" ? def.main.toLowerCase() : def.main.toUpperCase();
}

function classify(def: KeyDef, view: ViewModel): KeyClass {
  if (def.code === undefined) return "func";
  if (view.keyClass.get(def.code) === "empty") return "dim";
  if (view.coding && def.dimWhenCoding === true) return "subDim";
  return "normal";
}

// ── 设置面板 ──

/** 面板控件的引用，供 update() 按 settings 回写选中态 */
interface SheetControls {
  symbolSwipe: HTMLInputElement[];
  backspaceDeletesChar: HTMLInputElement;
  rows: HTMLInputElement[];
}

function buildSheet(h: Handlers): { frag: DocumentFragment; ctl: SheetControls } {
  const frag = document.createDocumentFragment();
  const panel = el("div", "sheet-panel");

  panel.append(el("h2", "sheet-title", "设置"));
  const symbol = buildRadioGroup(h);
  panel.append(symbol.group);
  const backspace = buildBackspaceGroup(h);
  panel.append(backspace.group);
  const rows = buildRowsGroup(h);
  panel.append(rows.group);

  const close = el("button", "sheet-btn", "关闭");
  close.type = "button";
  close.addEventListener("click", h.onCloseSettings);
  panel.append(close);

  frag.append(panel);
  return {
    frag,
    ctl: {
      symbolSwipe: symbol.inputs,
      backspaceDeletesChar: backspace.input,
      rows: rows.inputs,
    },
  };
}

/** 把 settings 回写到面板控件。面板不随 update 重建，这步不做控件就会停在初始态 */
function syncSheet(ctl: SheetControls, s: Settings): void {
  for (const input of ctl.symbolSwipe) {
    input.checked = input.value === s.symbolSwipe;
  }
  ctl.backspaceDeletesChar.checked = s.backspaceDeletesChar;
  for (const input of ctl.rows) {
    input.checked = input.value === String(s.rows);
  }
}

function buildRadioGroup(h: Handlers): { group: HTMLElement; inputs: HTMLInputElement[] } {
  const group = el("div", "sheet-group");
  group.append(el("div", "sheet-label", "上滑输入符号"));

  const options: Array<{ value: Settings["symbolSwipe"]; title: string; desc: string }> = [
    {
      value: "abandon",
      title: "① 放弃输入，保留原编码（默认）",
      desc: "结束编码态：当前编码原样留在编辑区，随后输入该符号（ime.py:777-780）",
    },
    {
      value: "disabled",
      title: "② 禁用，维持候选状态",
      desc: "上滑符号不响应，编码与候选保持不变。桌面端没有这一档",
    },
  ];

  const inputs: HTMLInputElement[] = [];
  for (const o of options) {
    const row = el("label", "sheet-option");
    const input = el("input");
    input.type = "radio";
    input.name = "symbol-swipe";
    input.value = o.value;
    input.addEventListener("change", () => {
      if (input.checked) h.onSettingsChange({ symbolSwipe: o.value });
    });
    row.append(input, optionBody(o.title, o.desc));
    group.append(row);
    inputs.push(input);
  }
  return { group, inputs };
}

/**
 * 逐字选择下的退格行为。
 *
 * 桌面端 ime.py:752-758 无条件删字符，「退出逐字选择」只是输入变化后
 * main_function（ime.py:464-476）重置状态的连带效果 —— 两者一起发生。
 * 这里把它做成开关，默认开。
 */
function buildBackspaceGroup(h: Handlers): { group: HTMLElement; input: HTMLInputElement } {
  const group = el("div", "sheet-group");
  group.append(el("div", "sheet-label", "退格"));

  const row = el("label", "sheet-option");
  const input = el("input");
  input.type = "checkbox";
  input.addEventListener("change", () =>
    h.onSettingsChange({ backspaceDeletesChar: input.checked }),
  );
  row.append(
    input,
    optionBody(
      "逐字选择下按退格删除一位字符",
      "开启＝删一位编码并退出逐字选择（与桌面端一致）；关闭＝只退出逐字选择，编码保留",
    ),
  );
  group.append(row);
  return { group, input };
}

function buildRowsGroup(h: Handlers): { group: HTMLElement; inputs: HTMLInputElement[] } {
  const group = el("div", "sheet-group");
  group.append(el("div", "sheet-label", "键盘布局"));

  const inputs: HTMLInputElement[] = [];

  const row5 = el("label", "sheet-option");
  const i5 = el("input");
  i5.type = "radio";
  i5.name = "kb-rows";
  // value 必须与 settings.rows 的字符串一致 —— syncSheet 靠它回写选中态，
  // 缺了 value 两个 radio 会永远停在「全部未选中」
  i5.value = "5";
  i5.addEventListener("change", () => {
    if (i5.checked) h.onSettingsChange({ rows: 5 });
  });
  row5.append(i5, optionBody("5 行（方案 H）"));
  group.append(row5);
  inputs.push(i5);

  const row6 = el("label", "sheet-option");
  const i6 = el("input");
  i6.type = "radio";
  i6.name = "kb-rows";
  i6.value = "6";
  i6.addEventListener("change", () => {
    if (i6.checked) h.onSettingsChange({ rows: 6 });
  });
  row6.append(i6, optionBody("6 行变体", "Row5 下追加语 / ，/ 空格 / 句点 / 回车，键盘高 +47dp"));
  group.append(row6);
  inputs.push(i6);

  return { group, inputs };
}

function optionBody(title: string, desc?: string): HTMLElement {
  const box = el("div", "sheet-option-body");
  box.append(el("div", "sheet-option-title", title));
  if (desc !== undefined) box.append(el("div", "sheet-option-desc", desc));
  return box;
}

// ── 部件表浮层 ──

/**
 * 部件表浮层：覆盖原键盘、等高、右上角 × 关闭。
 *
 * 浮层是键盘的子节点，绝对定位填满键盘（.keyboard 设为 relative），
 * 故天然与键盘同高、同宽，覆盖 Row1 候选区到 Row5/Row6 全部键。
 * 打开 / 关闭只切一个布尔状态位（st.radicalOpen），不触碰编码 / 候选 / 逐字选择，
 * 关闭后原键盘状态原样保留。
 */
function buildRadical(h: Handlers): { el: HTMLElement } {
  const wrap = el("div", "kb-radical");
  wrap.hidden = true;

  const close = el("button", "kb-radical-close", "×");
  close.type = "button";
  close.setAttribute("aria-label", "关闭形部表");
  close.addEventListener("click", h.onRadicalClose);

  const title = el("div", "kb-radical-title", "形部表 · 上滑 Z 查询");

  const list = el("div", "kb-radical-list");
  for (const g of RADICAL_TABLE) {
    const row = el("div", "kb-radical-row");
    row.append(el("span", "kb-radical-key", g.label), el("span", "kb-radical-chars", g.chars));
    list.append(row);
  }

  wrap.append(close, title, list);
  return { el: wrap };
}
