/**
 * Demo 入口：装配引擎 → 状态 → 渲染 → 手势。
 *
 * 单次数据流：输入事件 → reducer 出新 state → buildView 算视图 → renderer.update 重绘。
 * 没有双向绑定，也没有脏检查，state 永远是唯一事实源。
 */

import { createEngine, type Candidate } from "../engine/index.ts";
import { attachGestures } from "./events.ts";
import { KEY_BY_MAIN, subTextOf } from "./keymap.ts";
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

/** 长按连删间隔（ms）。⌫ 按住不放时的连续删除速度 ≈ 20 字/秒 */
const REPEAT_DELETE_MS = 50;

/** 上滑 ⌫ 的二次确认窗口（ms）。清空整段文本是破坏性操作，必须二次确认 */
const CLEAR_CONFIRM_MS = 3000;

let repeatDeleteTimer = 0;
let clearPendingUntil = 0;

/**
 * 长按 ⌫：加速连删（业界惯例的 repeat delete）。
 *
 * 立即删一次再起 interval，避免第一个字符要等 REPEAT_DELETE_MS 才动 ——
 * 那会让长按看起来"迟钝"。删到文本与编码都空时自动停表，不做无意义轮询。
 * 返回 true 表示消费了长按，松手不再派发单点（events.ts 据此抑制 onTap）。
 */
function startRepeatDelete(): boolean {
  stopRepeatDelete();
  st = S.backspace(st);
  redraw();
  repeatDeleteTimer = window.setInterval(() => {
    st = S.backspace(st);
    redraw();
    if (st.committed.length === 0 && st.buffer.length === 0) stopRepeatDelete();
  }, REPEAT_DELETE_MS);
  return true;
}

function stopRepeatDelete(): void {
  if (repeatDeleteTimer !== 0) {
    window.clearInterval(repeatDeleteTimer);
    repeatDeleteTimer = 0;
  }
}

/**
 * 受设置项约束的符号。
 *
 * 设计稿模块 6：两种模式下键帽都只灰显，不做抖动拒绝 —— 抖动是「禁用」的
 * 视觉暗示，与「无候选 → 直出原编码」的运行时语义冲突（ime.py:329）。
 */
function swipeSymbol(char: string, gated: boolean): void {
  // 6 行布局下，中文逗号已提升为 Row6 主键，V 上滑（门控键）的逗号功能摘除；
  // Row6 逗号键自身（gated=false）不受影响（计划 §1.2）
  if (st.settings.rows === 6 && char === "，" && gated) return;
  if (!view.coding) {
    emit(char);
    return;
  }
  if (st.settings.symbolSwipe === "disabled") return; // 维持候选状态，不吞键
  st = S.abandonInput(st, st.buffer); // 原编码留在编辑区
  st = S.insertAtCursor(st, char);
  redraw();
}

/**
 * 自动上字。对齐 ime.py:505-518，四条缺一不可：
 *
 *   1. 必须单字态 —— 多字分支（ime.py:525 起）根本没有自动上字。
 *      含人工单引号的输入必定是多字态，因此自动上字对其永不生效。
 *   2. len(split_text) > 3 —— 至少 4 码才上字。单字态下 split === code，
 *      故用 view.code.length 判定（da4 只有 3 码，即使唯一命中也不上字）。
 *   3. 当前页候选里 rest 不含 '.' 的**恰好 1 条**。rest 含 '.' 表示还在补码
 *      引导中，不算命中 —— 这一条把「总候选多条但只有一条已打全」的情况放行。
 *   4. 上屏该候选的首个**码点**，不是首个 UTF-16 码元：152 条非 BMP 字是代理对。
 *
 * 注意条件 3 不要求 rest 为空：ime.py:513 直接取该候选的首字上屏，
 * 所以补码已唯一确定、但仍带 rest 的输入（如 bo2c. → 簿，rest="z"）也会自动上字。
 */
function maybeAutoCommit(): void {
  if (!st.settings.autoCommit || view.mode !== "single") return;
  if (view.candidates.length === 0 || view.code.length <= 3) return;

  const nonDot = view.candidates.filter((c) => !c.rest.includes("."));
  if (nonDot.length !== 1) return;

  const picked = [...nonDot[0]!.text][0];
  if (picked === undefined) return;
  st = S.commitText(st, picked);
  redraw();
}

/**
 * 翻页。对齐 ime.py:229-237：下一页只有**下一页真有候选**才前进，
 * 上一页要求 page > 0。否则页码会一路涨下去，而候选区始终是空的。
 */
function changePage(delta: number): void {
  if (delta > 0 && !view.hasNextPage) return;
  if (delta < 0 && st.page <= 0) return;
  st = S.setPage(st, st.page + delta);
  redraw();
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
    const i = view.currentPart;
    st = S.resolvePart(st, i, c.text);
    redraw();

    if (Object.keys(st.resolved).length >= view.partCount) {
      // 全部部件选完 → 整串上屏
      st = S.commitText(st, view.preview);
      redraw();
      return;
    }

    // 推进到下一个尚未选择的部件（ime.py 的逐字推进），字面段同样跳过。
    // 必须在回写前算：回写会改 buffer，parts 的内容随之改变。
    const literal = new Set(view.literalIndices);
    const total = view.parts.length;
    let next = (i + 1) % total;
    for (let k = 0; k < total && (st.resolved[next] !== undefined || literal.has(next)); k++) {
      next = (next + 1) % total;
    }

    /**
     * ime.py:424-441 非末字分支：把「前缀 + 剩余编码」回写进编码串，
     * 于是上方下划线的编码实时补全 —— ceu 选「测」后从 ceu 变成 ce4u'u，
     * 左上角小显示区同时显示刚选的「测」。
     * 回写必须走 commitPartCode 而不是 pushCode：后者会清掉 resolved。
     */
    const parts = [...view.parts];
    parts[i] = parts[i]! + c.rest;
    st = S.commitPartCode(st, parts.join("'"), next, c.text);
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
    // 清空确认窗口只覆盖「紧接着的第二次上滑 ⌫」：期间做了别的按键操作即作废
    clearPendingUntil = 0;
    if (def.main === "∨") {
      changePage(1);
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
    // Row6 直接输出键（6 行布局）。这些键无 code，点按即直出，不进编码缓冲。
    // 逗号键键面为半角「,」（用户定稿），输出**英文**逗号；
    // 编码态下走 swipeSymbol（放弃输入再出符号，对齐桌面端「符号等编码上屏后才输」）
    if (def.main === ",") {
      swipeSymbol(",", false);
      return;
    }
    // 句点键双身份（对齐 N 上滑的 dotOrBuma）：编码态作补码引导符进编码流，
    // 空闲态直出英文句点 —— 6 行下这是补码引导符的唯一入口
    if (def.main === ".") {
      if (view.coding) {
        st = S.pushCode(st, ".");
        redraw();
      } else {
        emit(".");
      }
      return;
    }
    if (def.main === "🌐") {
      toast("语言切换 · P2 待实现");
      return;
    }
    if (def.main === "空格") {
      // 与 B 上滑同源：编码态上屏首选，空闲态输出空格
      if (view.coding) commitDisplay();
      else emit(" ");
      return;
    }
    if (def.main === "↵") {
      // 与 M 上滑同源：编码态放弃输入，空闲态回车
      if (view.coding) {
        st = S.abandonInput(st, st.buffer);
        redraw();
      } else {
        emit("\n");
      }
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
    /**
     * 上滑门控（2026-08-31 定稿）：当前状态下键面无可见副字符 → 上滑视作单点。
     * 判定与渲染共用 subTextOf，保证「看不见的提示不生效、看得见的提示必生效」。
     *
     * 覆盖两类键：
     *   - 本无副字符的键（⌫、Row6 五键）—— 上滑不再吞键，等同单点；
     *   - hideSubIn6Row 的键（X/V/B/N/M）—— 6 行下副字符隐藏，上滑回落到
     *     主字符（如 6 行下上滑 B 输出 b 进编码流，不再出空格）；
     *     5 行下副字符可见，原有上滑行为完整保留。
     */
    if (subTextOf(def, view.coding, st.settings.rows).length === 0) {
      handlers.onKeyTap(def);
      return;
    }

    const a = def.swipe;
    switch (a.kind) {
      case "none":
        return;

      case "symbol":
        swipeSymbol(a.char, a.gated);
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
        } else if (st.settings.rows !== 6) {
          // 6 行布局下句点功能下沉到 Row6 主键，此处不再直出（计划 §1.2）
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
        changePage(a.delta);
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

      case "radical":
        // 上滑 Z：切换部件表浮层。不触碰编码 / 候选状态，关闭后原样保留
        st = S.setRadicalOpen(st, !st.radicalOpen);
        redraw();
        return;

      // 上滑 ⌫：清空已上屏文本。二次确认 —— 窗口内再滑一次才真执行，
      // 超时或期间做了别的操作（onKeyTap 会重置）则作废
      case "clearAll": {
        const now = Date.now();
        if (clearPendingUntil > now) {
          clearPendingUntil = 0;
          st = S.clearCommitted(st);
          redraw();
          toast("已清空文本（编码保留）");
          return;
        }
        clearPendingUntil = now + CLEAR_CONFIRM_MS;
        toast("再滑一次 ⌫ 清空全部");
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
    changePage(delta);
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

  onRadicalClose() {
    st = S.setRadicalOpen(st, false);
    redraw();
  },
};

renderer = mount(root, handlers);

// 手势层只产出「方向 + 键」，语义全交给 handlers 分派。
// 左右滑门控（2026-08-31 定稿）：仅 G/H 的光标滑动保留，
// 其余键的左右滑一律视作单点，不让手势吞键。
attachGestures(root.keyboard, KEY_BY_MAIN, {
  onTap: handlers.onKeyTap,
  onSwipeUp: handlers.onKeySwipe,
  onSwipeLeft: (def: KeyDef) => {
    if (def.swipeLeft?.kind === "cursor") {
      moveCaret(def.swipeLeft.delta);
      return;
    }
    handlers.onKeyTap(def);
  },
  onSwipeRight: (def: KeyDef) => {
    if (def.swipeRight?.kind === "cursor") {
      moveCaret(def.swipeRight.delta);
      return;
    }
    handlers.onKeyTap(def);
  },
  // 长按：只有 ⌫ 消费（加速连删）。其余键返回 false，长按不吞键
  onLongPressStart: (def: KeyDef) => (def.main === "⌫" ? startRepeatDelete() : false),
  onLongPressEnd: stopRepeatDelete,
});

redraw();
