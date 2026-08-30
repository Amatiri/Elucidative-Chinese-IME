/**
 * Demo 入口：装配引擎 → 状态 → 渲染 → 手势。
 *
 * 单次数据流：输入事件 → reducer 出新 state → buildView 算视图 → renderer.update 重绘。
 * 没有双向绑定，也没有脏检查，state 永远是唯一事实源。
 */

import { createEngine, type Candidate } from "../engine/index.ts";
import { attachGestures } from "./events.ts";
import { KEY_BY_MAIN } from "./keymap.ts";
import { mount, type Handlers } from "./render.ts";
import { loadSettings, saveSettings } from "./settings.ts";
import * as S from "./state.ts";
import type { KeyDef, KeyboardState, Settings } from "./types.ts";
import { buildView, type ViewModel } from "./view.ts";

const engine = createEngine();

let st: KeyboardState = S.initialState(loadSettings());
let view: ViewModel = buildView(engine, st);
let renderer: ReturnType<typeof mount>;

function mustGet(id: string): HTMLElement {
  const node = document.getElementById(id);
  if (node === null) throw new Error(`缺少容器 #${id}`);
  return node;
}

const root = {
  keyboard: mustGet("keyboard"),
  output: mustGet("output"),
  sheet: mustGet("sheet"),
};

const toastEl = mustGet("toast");
let toastTimer = 0;

function toast(msg: string): void {
  toastEl.textContent = msg;
  toastEl.classList.add("is-on");
  window.clearTimeout(toastTimer);
  toastTimer = window.setTimeout(() => toastEl.classList.remove("is-on"), 1400);
}

function redraw(): void {
  view = buildView(engine, st);
  renderer.update(st, view);
}

/**
 * 直出文本到编辑区（非编码字符：符号 / 空格 / 回车 / 空闲态外输）。
 * 大小写档位只作用于这里 —— 编码一律小写，与引擎 CODE_CHARS 一致。
 */
function emit(text: string): void {
  // 顺序要紧：applyCaps 可能把 once 回落成 lower 并改写 st，
  // 若把 applyCaps 写在实参里，insertAtCursor 读到的仍是回落前的旧 st，
  // 随后的赋值又把回落覆盖掉 —— 单次大写会退化成连续大写。
  const out = applyCaps(text);
  st = S.insertAtCursor(st, out);
  redraw();
}

function applyCaps(text: string): string {
  if (st.caps === "lower" || !/^[A-Za-z]$/.test(text)) return text;
  if (st.caps === "once") st = { ...st, caps: "lower" }; // 单次大借用完即回落
  return text.toUpperCase();
}

/**
 * 受设置项约束的符号。
 *
 * 设计稿模块 6：两种模式下键帽都只灰显，不做抖动拒绝 —— 抖动是「禁用」的
 * 视觉暗示，与「无候选 → 直出原编码」的运行时语义冲突（ime.py:329）。
 */
function swipeSymbol(char: string): void {
  if (!view.coding) {
    emit(char);
    return;
  }
  if (st.settings.symbolSwipe === "disabled") return; // 维持候选状态，不吞键
  st = S.abandonInput(st, st.buffer); // 原编码留在编辑区
  st = S.insertAtCursor(st, char);
  redraw();
}

/** 自动上字：编码打满（rest 为空）且唯一命中时自动上屏 */
function maybeAutoCommit(): void {
  if (!st.settings.autoCommit || view.mode !== "single") return;
  const only = view.candidates[0];
  if (only !== undefined && view.candidates.length === 1 && only.rest === "") {
    st = S.commitText(st, only.text);
    redraw();
  }
}

function commitDisplay(): void {
  const text = view.display.length > 0 ? view.display : view.preview;
  if (text.length === 0) return;
  st = S.commitText(st, text);
  redraw();
}

/** 选中候选：逐字选择态下先落到当前部件，全部选完再整串上屏 */
function pickCandidate(index: number): void {
  const c: Candidate | undefined = view.candidates[index];
  if (c === undefined) return;

  if (view.selecting && view.currentPart !== null) {
    st = S.resolvePart(st, view.currentPart, c.text);
    redraw();

    if (Object.keys(st.resolved).length >= view.partCount) {
      // 全部部件选完 → 整串上屏
      st = S.commitText(st, view.preview);
      redraw();
      return;
    }
    // 推进到下一个尚未选择的部件（ime.py 的逐字推进），字面段同样跳过
    const literal = new Set(view.literalIndices);
    const total = view.parts.length;
    let next = (view.currentPart + 1) % total;
    for (let i = 0; i < total && (st.resolved[next] !== undefined || literal.has(next)); i++) {
      next = (next + 1) % total;
    }
    st = S.setPartIndex(st, next);
    redraw();
    return;
  }

  st = S.commitText(st, c.text);
  redraw();
}

/** 逐字选择导航（ime.py navigate_parts） */
function movePart(delta: number): void {
  const total = view.parts.length;
  if (total === 0) return;

  // 字面段（无候选、按编码原样输出）没有候选可选 ——
  // ime.py 的 _apply_phrase_result 已把它们预填进 resolved_chars，导航时跳过
  const literal = new Set(view.literalIndices);
  if (literal.size >= total) return;

  const cur = st.partIndex;
  let next = cur === null ? 0 : (((cur + delta) % total) + total) % total;
  for (let i = 0; i < total && literal.has(next); i++) {
    next = (((next + delta) % total) + total) % total;
  }
  st = S.setPartIndex(st, next);
  redraw();
}

/**
 * G / H 光标移动。
 *
 * 有编码时移动**编码串内部**的光标（ime.py 的 code_char_before_cursor，
 * 外输模式支持在编码中间插入字符），空闲时才移动已上屏文本的光标。
 */
function moveCaret(delta: number): void {
  st = view.coding ? S.moveCodeCursor(st, delta) : S.moveCursor(st, delta);
  redraw();
}

const handlers: Handlers = {
  onKeyTap(def) {
    if (def.main === "∨") {
      st = S.setPage(st, st.page + 1);
      redraw();
      return;
    }
    if (def.main === "⌫") {
      st = S.backspace(st);
      redraw();
      return;
    }
    // '=' 不是编码字符。单击 = 下一个字
    if (def.main === "=") {
      if (view.mode === "multi") movePart(1);
      else if (!view.coding) emit("=");
      // 编码态但非多字：没有部件可导航，吞掉。
      // ime.py 只在 has_code_chars 时导航，单字态下 navigate_parts 无部件可用；
      // 此时若直出 '=' 会污染编码。
      return;
    }
    if (def.code !== undefined) {
      // 大 / 连：字母直接上屏大写，不进编码缓冲。
      // 这是「大」与「连」唯一的行为差异来源 —— 大用完一次自动回落小，连保持不变。
      if (st.caps !== "lower" && /^[A-Za-z]$/.test(def.code)) {
        emit(def.code);
        return;
      }
      /**
       * 空闲态直出判定 —— 但**26 个字母一律进编码缓冲**，不看 nextCharClass。
       *
       * 真值表第 0 位：simple = b-z 的 24 个字母，a / e 归入 multiOnly。
       * multiOnly 的含义是「不能作**单字**编码的开头」，不等于不能输入 ——
       * 它们仍可能是**词语编码的类型符**。若按 empty 直出，a、e 就被挡在
       * 输入流之外，相关词语永远打不出来。
       *
       * 非字母（数字 / ; / ' / .）在第 0 位是 dead，空闲态照旧直出。
       */
      if (!view.coding) {
        const isLetter = /^[a-z]$/.test(def.code);
        if (!isLetter && view.keyClass.get(def.code) !== "content") {
          emit(def.code);
          return;
        }
      }
      st = S.pushCode(st, def.code);
      redraw();
      maybeAutoCommit();
      return;
    }
  },

  onKeySwipe(def) {
    const a = def.swipe;
    switch (a.kind) {
      case "none":
        return;

      case "symbol":
        swipeSymbol(a.char);
        return;

      case "select": {
        // ime.py handle_selection_keys：有词语时「!」直接上屏词语，优先于选 1 号候选
        if (a.index === 1 && view.phraseContent.length > 0) {
          st = S.commitText(st, view.phraseContent);
          redraw();
          return;
        }
        // 空闲态上滑 1-5 → 直出 !@#$%（编码态下该位无候选则不响应，不吞键也不直出）
        if (!view.coding) {
          emit(def.idleSub ?? "");
          return;
        }
        pickCandidate(a.index - 1);
        return;
      }

      // 空闲态直出英文句点；编码态作补码引导符 —— 同一个字符，语义由状态决定
      case "dotOrBuma":
        if (view.coding) {
          st = S.pushCode(st, ".");
          redraw();
        } else {
          emit(".");
        }
        return;

      case "commitOrSpace":
        if (view.coding) commitDisplay();
        else emit(" ");
        return;

      case "abandonOrEnter":
        if (view.coding) {
          st = S.abandonInput(st, st.buffer);
          redraw();
        } else {
          emit("\n");
        }
        return;

      // 设置菜单仅在空闲态可打开；编码态按设置项处理以保持操作连续性
      case "settings":
        if (!view.coding) {
          st = S.setSettingsOpen(st, true);
          redraw();
          return;
        }
        if (st.settings.symbolSwipe === "abandon") {
          st = S.abandonInput(st, st.buffer);
          redraw();
        }
        return;

      case "caps":
        st = S.cycleCaps(st);
        redraw();
        return;

      case "page":
        st = S.setPage(st, st.page + a.delta);
        redraw();
        return;

      // '=' 上滑出 '-' = 上一个字；非多字态在空闲时才直出原字符
      case "partNav":
        if (view.mode === "multi") movePart(a.delta);
        else if (!view.coding) emit(a.delta > 0 ? "=" : "-");
        return;

      // A / S：上滑切换「自动上字」「优先上词」，不是 P2 占位
      case "toggle": {
        const next = !st.settings[a.key];
        st = S.updateSettings(st, { [a.key]: next });
        saveSettings(st.settings);
        redraw();
        toast(`${a.name}：${next ? "开" : "关"}`);
        return;
      }

      case "stub":
        toast(`${a.name} · P2 待实现`);
        return;
    }
  },

  onCandidateTap(index) {
    pickCandidate(index);
  },

  onPage(delta) {
    st = S.setPage(st, st.page + delta);
    redraw();
  },

  onPreviewTap() {
    if (view.preview.length === 0) return;
    st = S.commitText(st, view.preview);
    redraw();
  },

  onPhraseTap() {
    if (view.phraseContent.length === 0) return;
    st = S.commitText(st, view.phraseContent);
    redraw();
  },

  onSettingsChange(patch: Partial<Settings>) {
    st = S.updateSettings(st, patch);
    saveSettings(st.settings);
    redraw();
  },

  onCloseSettings() {
    st = S.setSettingsOpen(st, false);
    redraw();
  },
};

renderer = mount(root, handlers);

// 手势层只产出「方向 + 键」，语义全交给 handlers 分派
attachGestures(root.keyboard, KEY_BY_MAIN, {
  onTap: handlers.onKeyTap,
  onSwipeUp: handlers.onKeySwipe,
  onSwipeLeft: (def: KeyDef) => {
    if (def.swipeLeft?.kind === "cursor") moveCaret(def.swipeLeft.delta);
  },
  onSwipeRight: (def: KeyDef) => {
    if (def.swipeRight?.kind === "cursor") moveCaret(def.swipeRight.delta);
  },
});

redraw();
