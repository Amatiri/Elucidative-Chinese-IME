/**
 * DOM 渲染。首次 mount 建结构，之后只改文本与 class，不重建节点。
 *
 * 【三区职责】对齐 ime.py 外输模式的 update_display()：
 *   目标输入框 = 已上屏文本 + 正在输入的编码（下划线）
 *   左上小显示区 = 最后输入的一个字符；空闲态显示大小写档位「小 / 大 / 连」
 *   中间候选区 = 单字态出单字候选；多字态**不出单字候选**，改出多字预览串 + 词语
 */

import { KEYMAP_5ROW } from "./keymap.ts";
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

  for (const row of KEYMAP_5ROW) {
    const rowEl = el("div", "kb-row");

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

  root.sheet.append(buildSheet(h));

  return {
    update(st, view) {
      renderOutput(root.output, st, view);
      renderDisplay(displayEl, st, view);
      renderCandidates(listEl, stripEl, candEls, view, h);
      if (pageEl !== null) pageEl.textContent = view.pageLabel;

      for (const [main, node] of keyEls) {
        const def = findDef(main);
        if (def === undefined) continue;
        // 开关类键按当前值高亮，让「字 / 词」的开与关一眼可见
        const on = def.swipe.kind === "toggle" && st.settings[def.swipe.key] ? " is-on" : "";
        node.className = "kb-key " + classify(def, view) + on;
        const sub = node.querySelector<HTMLElement>(".kb-sub");
        if (sub !== null) {
          sub.textContent =
            def.codingSub !== undefined && view.coding ? def.codingSub : (def.idleSub ?? "");
        }
        const mainEl = node.querySelector<HTMLElement>(".kb-main");
        if (mainEl !== null) mainEl.textContent = displayMain(def, st);
      }

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
  for (const row of KEYMAP_5ROW) {
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

function buildSheet(h: Handlers): DocumentFragment {
  const frag = document.createDocumentFragment();
  const panel = el("div", "sheet-panel");

  panel.append(el("h2", "sheet-title", "设置"));
  panel.append(buildRadioGroup(h));
  panel.append(buildToggleGroup(h));
  panel.append(buildRowsGroup(h));

  const close = el("button", "sheet-btn", "关闭");
  close.type = "button";
  close.addEventListener("click", h.onCloseSettings);
  panel.append(close);

  frag.append(panel);
  return frag;
}

function buildRadioGroup(h: Handlers): HTMLElement {
  const group = el("div", "sheet-group");
  group.append(el("div", "sheet-label", "上滑输入符号"));

  const options: Array<{ value: Settings["symbolSwipe"]; title: string; desc: string }> = [
    { value: "disabled", title: "② 禁用，维持候选状态（默认）", desc: "上滑符号不响应，编码与候选保持不变" },
    {
      value: "abandon",
      title: "① 放弃输入，保留原编码",
      desc: "结束编码态：当前编码原样留在编辑区，随后输入该符号",
    },
  ];

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
  }
  return group;
}

/** 自动上字 / 优先上词 —— 键帽简作「字」「词」，此处用全称 */
function buildToggleGroup(h: Handlers): HTMLElement {
  const group = el("div", "sheet-group");
  group.append(el("div", "sheet-label", "上屏策略"));

  const toggles: Array<{ key: "autoCommit" | "phrasePriority"; title: string; desc: string }> = [
    {
      key: "autoCommit",
      title: "自动上字（键帽「字」）",
      desc: "编码打满且无重码时自动上屏，无需再选候选",
    },
    {
      key: "phrasePriority",
      title: "优先上词（键帽「词」）",
      desc: "多字时词语优先于首选字组合；关闭则按逐字首选拼接",
    },
  ];

  for (const t of toggles) {
    const row = el("label", "sheet-option");
    const input = el("input");
    input.type = "checkbox";
    input.addEventListener("change", () => h.onSettingsChange({ [t.key]: input.checked }));
    row.append(input, optionBody(t.title, t.desc));
    group.append(row);
  }
  return group;
}

function buildRowsGroup(h: Handlers): HTMLElement {
  const group = el("div", "sheet-group");
  group.append(el("div", "sheet-label", "键盘布局"));

  const row5 = el("label", "sheet-option");
  const i5 = el("input");
  i5.type = "radio";
  i5.name = "kb-rows";
  i5.checked = true;
  i5.addEventListener("change", () => {
    if (i5.checked) h.onSettingsChange({ rows: 5 });
  });
  row5.append(i5, optionBody("5 行（方案 H）"));
  group.append(row5);

  const row6 = el("label", "sheet-option is-disabled");
  const i6 = el("input");
  i6.type = "radio";
  i6.name = "kb-rows";
  i6.disabled = true;
  row6.append(i6, optionBody("6 行变体", "v0.2 暂未支持"));
  group.append(row6);

  return group;
}

function optionBody(title: string, desc?: string): HTMLElement {
  const box = el("div", "sheet-option-body");
  box.append(el("div", "sheet-option-title", title));
  if (desc !== undefined) box.append(el("div", "sheet-option-desc", desc));
  return box;
}
