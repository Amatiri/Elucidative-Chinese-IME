import tkinter as tk
import os
import pyperclip
import keyboard
import threading
import time
import win32api

# ==================== 导入模块化组件 ====================
from config import (DATA_FILE, CODE_CHARS, SURROUND_CHARS, SELECTION_SYMBOLS,
                         SYMBOL_TO_INDEX, CIYU_FILE,
                         FONT_SIZE_INPUT, FONT_SIZE_COUNT, FONT_SIZE_RADICAL,
                         FONT_SIZE_SMALL, FONT_SIZE_BUTTON,
                         FONT_SMALL_NAME, FONT_BUTTON_NAME,
                         get_primary_font_name)
from manager.dictionary_frontend import (
    ensure_data_file, query_phrase, get_entry_count,
    query_by_prefix, process_input, split_sequence,
    query_single_char, query_multi_chars,get_phrase_segments
)

# ==================== 上下文对象：替代全部全局变量 ====================

class InputContext:

    def __init__(self):
        # ── 输入流程状态 ──
        self.current_page = 0                  # 当前候选页码（0起始）
        self.query_type = ""                   # "single" | "multi_part"
        self.current_phrase = ""               # 当前匹配到的短语
        self.current_part_index = -1           # 多字选择时当前部件索引
        self.split_parts = []                  # 多字输入时拆分后的部件列表
        self.in_part_selection = False         # 是否处于多字部件选择模式
        self.last_input_text = ""              # 上一次输入文本，用于检测变化
        self.last_output_text = ""             # 上次计算的首候选首字/预览串，供空格快速上屏
        self.current_candidates = []           # 缓存的候选列表（已分割），供 get_current_candidates 直达
        self.selection_updating = False        # 是否正在由选择操作更新输入框（保护 resolved_chars）
        self.resolved_chars = {}               # {part_index: "汉字"} 多字模式下已选中的部件
        self.original_split_count = 0          # 多字模式下原始拆分的部件总数

        # ── 缓存：避免 navigate / update_display 重复计算 ──
        self._cached_processed = ""
        self._cached_processed_input = ""
        self._cached_split_text = ""
        self._cached_first_chars = ""
        self._cached_first_chars_input = ""
        self._cached_phrase_result = None       # get_phrase_segments 的完整结果

        # ── 设置开关 ──
        self.auto_commit_enabled = "1"         # 自动上字开关（"1"启用）
        self.phrase_priority = "1"             # 优先上词开关（"1"启用）

        # ── 外输模式 ──
        self.external_mode = False             # 外输模式开关
        self.window_closing = False            # 窗口是否正在关闭
        self.key_press_counter = 0             # 按键计数防抖
        self.code_char_before_cursor = 0       # 光标前的编码字符数
        self.code_char_after_cursor = 0        # 光标后的编码字符数

        # ── 主窗口引用（创建后赋值） ──
        self.window = None

    # ── 集中操作 ──

    def reset(self):
        """集中重置输入相关状态（不清除外输 / 设置开关 / 窗口引用）。"""
        self.current_page = 0
        self.current_part_index = -1
        self.query_type = ""
        self.split_parts = []
        self.in_part_selection = False
        self.current_phrase = ""
        self.last_output_text = ""
        self.current_candidates = []
        self.resolved_chars = {}
        self.original_split_count = 0
        # ── 清空缓存 ──
        self._cached_processed = ""
        self._cached_processed_input = ""
        self._cached_split_text = ""
        self._cached_first_chars = ""
        self._cached_first_chars_input = ""
        self._cached_phrase_result = None

    @property
    def resolved_count(self) -> int:
        return len(self.resolved_chars)

    def is_all_resolved(self) -> bool:
        """是否所有多字部件都已解析完毕。"""
        return len(self.resolved_chars) == self.original_split_count

    # ── 外输模式便捷方法 ──

    def reset_cursor_counters(self):
        self.code_char_before_cursor = 0
        self.code_char_after_cursor = 0

    def has_code_chars(self) -> bool:
        return self.code_char_before_cursor + self.code_char_after_cursor != 0


ctx = InputContext()

# ==================== 输入处理核心函数 ====================

def replace_content(original, processed, do_paste=True, reset_entry=True):
    """
    用处理后的编码结果替换输入框中的编码部分，并处理粘贴。
    original: 原始输入文本
    processed: 要替换的编码结果（如选中的汉字）
    do_paste: 是否执行粘贴（外输模式）
    reset_entry: 粘贴后是否清空输入框
    """
    first_letter_pos = -1
    last_letter_pos = -1
    # 找到第一个字母的位置
    for i, char in enumerate(original):
        if 'a' <= char <= 'z':
            first_letter_pos = i
            break
    # 找到编码结束的位置（第一个非SURROUND_CHARS字符）
    for j, char in enumerate(original):
        if (char not in SURROUND_CHARS) and j > i:
            last_letter_pos = j
            break
    if first_letter_pos == -1:
        output = original
    elif last_letter_pos == -1:
        prefix = original[:first_letter_pos]
        output = prefix + processed
    else:
        prefix = original[:first_letter_pos]
        suffix = original[last_letter_pos:]
        output = prefix + processed + suffix
    output = output.strip()
    if do_paste and ctx.external_mode:
        paste_text(output, reset_entry)
    else:
        pyperclip.copy(output)
        entry_box.delete(0, tk.END)
        entry_box.insert(0, output)
        real_time_var.set(output)

def clear_display_if_no_code(input_text):
    """
    如果输入文本中不包含有效编码，则清空下方的显示标签。
    """
    first_letter_pos = -1
    for i, char in enumerate(input_text):
        if 'a' <= char <= 'z':
            first_letter_pos = i
            break
    if first_letter_pos == -1:
        should_clear = True
    else:
        should_clear = True
        for char in input_text[first_letter_pos:]:
            if char in CODE_CHARS:
                should_clear = False
                break
    if should_clear:
        first_chars_label.config(text='')
        current_part_label.config(text='')
        page_label.config(text='')

def navigate_parts(direction):
    """
    在多字选择模式中切换当前部件。
    跳过已解析（resolved_chars 中已有）的部件，只在未解析部件之间跳转。
    """
    if ctx.query_type != "multi_part" or not ctx.split_parts:
        return
    if not ctx.in_part_selection:
        if direction == "next":
            ctx.in_part_selection = True
            ctx.current_phrase = ""
            for idx in range(len(ctx.split_parts)):
                if idx not in ctx.resolved_chars:
                    ctx.current_part_index = idx
                    break
    else:
        ctx.current_phrase = ""
        n = len(ctx.split_parts)
        if direction == "next":
            for offset in range(1, n + 1):
                candidate = (ctx.current_part_index + offset) % n
                if candidate not in ctx.resolved_chars:
                    ctx.current_part_index = candidate
                    break
        elif direction == "prev":
            for offset in range(1, n + 1):
                candidate = (ctx.current_part_index - offset) % n
                if candidate not in ctx.resolved_chars:
                    ctx.current_part_index = candidate
                    break
    ctx.current_page = 0

    input_text = real_time_var.get()
    # 输入未变 → 复用 main_function 缓存的 processed 和 first_chars
    if input_text == ctx._cached_processed_input:
        processed = ctx._cached_processed
        cached_first_chars = ctx._cached_first_chars if ctx._cached_first_chars else None
    else:
        processed = process_input(input_text)
        cached_first_chars = None
    update_display(processed=processed, first_chars=cached_first_chars)

def navigate_pages(direction):
    """
    翻页：direction "down" 下一页， "up" 上一页。
    """
    input_text = real_time_var.get()
    # 输入未变 → 复用 main_function 缓存的 processed 和 split_text
    if input_text == ctx._cached_processed_input:
        processed = ctx._cached_processed
        split_text = ctx._cached_split_text
    else:
        processed = process_input(input_text)
        split_text = split_sequence(processed)

    candidates = None
    if direction == "down":
        if ctx.query_type == "single":
            if query_single_char(split_text, (ctx.current_page + 1) * 5):
                ctx.current_page += 1
                candidates = query_single_char(split_text, ctx.current_page * 5)
        elif ctx.query_type == "multi_part" and ctx.split_parts and ctx.current_part_index >= 0:
            part = ctx.split_parts[ctx.current_part_index]
            if query_single_char(part, (ctx.current_page + 1) * 5):
                ctx.current_page += 1
    elif direction == "up" and ctx.current_page > 0:
        ctx.current_page -= 1
        if ctx.query_type == "single":
            candidates = query_single_char(split_text, ctx.current_page * 5)

    update_display(processed=processed, candidates=candidates)

def update_display(processed=None, candidates=None, first_chars=None):
    """
    根据当前状态更新下方的三个显示标签：
      - first_chars_label: 多字预览串（已解部件显示汉字，未解部件显示首候选首字）或短语
      - current_part_label: 当前部件的候选列表
      - page_label: 页码信息（含已选/总数）

    可选参数供 main_function 传入已算数据，避免重复扫描：
      processed:  process_input() 的结果
      candidates: 单字模式下的候选字符串
      first_chars: 多字模式下的预览串
    未传入时自行计算（navigate_pages/navigate_parts 路径）。
    """
    input_text = real_time_var.get()

    # ── 补充未传入的计算结果 ──
    if processed is None:
        processed = process_input(input_text)
    if candidates is None and first_chars is None:
        split_text = split_sequence(processed)

    # 整串查询短语（仅多字模式需要，单字模式下词语不显示，直接跳过）
    if ctx.query_type == "multi_part" and "'" not in processed:
        ctx.current_phrase = query_phrase(processed)
    else:
        ctx.current_phrase = ""

    # 清空标签，准备重新显示
    first_chars_label.config(text='')
    current_part_label.config(text='')
    page_label.config(text='')

    if ctx.query_type == "multi_part":
        # 未传入 first_chars → 需要完整计算（navigate_pages / navigate_parts 路径）
        if first_chars is None:
            if "'" in processed and ctx.phrase_priority == "1":
                phrase_result = get_phrase_segments(processed)
                if phrase_result:
                    first_chars = phrase_result[0]
                    ctx.split_parts = phrase_result[1]
                else:
                    first_chars = ""
                    ctx.split_parts = []
            else:
                first_chars = query_multi_chars(split_sequence(processed))
            # 缓存 first_chars，供下次 navigate_parts 输入未变时复用
            ctx._cached_first_chars = first_chars
            ctx._cached_first_chars_input = input_text

        if first_chars:
            if ctx.current_phrase and not ctx.in_part_selection:
                if first_chars == ctx.current_phrase[1:-1]:
                    first_chars_label.config(text=first_chars)
                    ctx.current_phrase = ""
                else:
                    first_chars_label.config(text=first_chars + "   " + ctx.current_phrase)
            else:
                first_chars_label.config(text=first_chars)
        elif ctx.current_phrase:
            first_chars_label.config(text=ctx.current_phrase)

        if first_chars and ctx.in_part_selection and ctx.current_part_index >= 0 and ctx.current_part_index < len(ctx.split_parts):
            part = ctx.split_parts[ctx.current_part_index]
            part_candidates = query_single_char(part, ctx.current_page * 5)
            if part_candidates:
                ctx.current_phrase = ""
                ctx.current_candidates = part_candidates.split("/")
                current_part_label.config(text=part_candidates)
                selected_count = len(ctx.resolved_chars)
                total_count = ctx.original_split_count if ctx.original_split_count > 0 else len(ctx.split_parts)
                page_label.config(text=f"字 {selected_count + 1}/{total_count} 页 {ctx.current_page + 1}")

    elif ctx.query_type == "single":
        if candidates is None:
            candidates = query_single_char(split_text, ctx.current_page * 5)
        if candidates:
            ctx.current_candidates = candidates.split("/")
            current_part_label.config(text=candidates)
            page_label.config(text=f"页 {ctx.current_page + 1}")
            ctx.last_output_text = candidates.split("/")[0][0]

def handle_special_keys(input_text):
    """
    处理输入中的 '=' 和 '-' 键，用于多字部件导航。
    返回 (新文本, 新光标位置, 是否已处理) 三元组。
    """
    if '=' in input_text or '-' in input_text:
        cursor_pos = entry_box.index(tk.INSERT)
        if ctx.query_type == "multi_part" and ctx.split_parts:
            equals_pos = input_text.find('=')
            minus_pos = input_text.find('-')
            if equals_pos != -1:
                ctx.current_phrase = ""
                navigate_parts("next")
                new_text = input_text[:equals_pos] + input_text[equals_pos+1:]
                if cursor_pos > equals_pos:
                    new_cursor_pos = cursor_pos - 1
                else:
                    new_cursor_pos = cursor_pos
                return new_text, new_cursor_pos, True
            if minus_pos != -1:
                ctx.current_phrase = ""
                navigate_parts("prev")
                new_text = input_text[:minus_pos] + input_text[minus_pos+1:]
                if cursor_pos > minus_pos:
                    new_cursor_pos = cursor_pos - 1
                else:
                    new_cursor_pos = cursor_pos
                return new_text, new_cursor_pos, True
    return input_text, None, False

def get_current_candidates():
    """
    获取当前状态下显示的候选列表（用于选择符号上屏）。
    直接从 ctx.current_candidates 缓存读取，不重复扫描码表。
    若无缓存返回空列表。
    """
    return ctx.current_candidates

def handle_selection_keys(event):
    """
    处理候选选择符号 ! @ # $ % 以及短语直接上屏 !（当有短语时）
    返回 "break" 阻止事件继续传播，否则返回 None。
    
    多字模式新机制：选择字符时补全剩余编码，而非替换为汉字。
    直到所有部件都解析完毕（unresolved == 0），才拼接最终汉字串上屏。
    """
    # 短语直接上屏：当前有短语且按下 !
    if event.char == "!" and ctx.current_phrase:
        phrase_content = ctx.current_phrase[1:-1]
        input_text = real_time_var.get()
        replace_content(input_text, phrase_content, do_paste=True, reset_entry=True)
        reset_input_state()
        return "break"

    if event.char in SELECTION_SYMBOLS:
        candidates = get_current_candidates()
        if not candidates:
            return
        index = SYMBOL_TO_INDEX.get(event.char, -1)
        if 0 <= index < len(candidates):
            candidate_str = candidates[index]
            selected_char = candidate_str[0]  # 候选的第一个汉字
            remaining = candidate_str[1:]       # 剩余编码
            input_text = real_time_var.get()
            if ctx.query_type == "single":
                replace_content(input_text, selected_char, do_paste=True, reset_entry=True)
                reset_input_state()
            elif ctx.query_type == "multi_part" and ctx.split_parts and ctx.current_part_index >= 0:
                i = ctx.current_part_index
                parts = list(ctx.split_parts)  # 当前所有编码部件
                if i >= len(parts):
                    return "break"
                ctx.resolved_chars[i] = selected_char
                if ctx.original_split_count == 0:
                    ctx.original_split_count = len(parts)
                prefix = parts[i]
                parts[i] = prefix + remaining
                new_code_sequence = "'".join(parts)
                if ctx.is_all_resolved():
                    # 末字：拼接最终汉字串上屏
                    final_text = "".join(
                        ctx.resolved_chars[j] for j in sorted(ctx.resolved_chars.keys())
                    )
                    ctx.selection_updating = True
                    replace_content(input_text, final_text, do_paste=True, reset_entry=True)
                    ctx.selection_updating = False
                    reset_input_state()
                else:
                    # 非末字：更新输入框编码，跳到下一个未解部件
                    ctx.selection_updating = True
                    replace_content(input_text, new_code_sequence, do_paste=False, reset_entry=False)
                    ctx.selection_updating = False
                    navigate_parts("next")
        return "break"

def reset_input_state():
    """重置所有输入相关的状态，并清空显示标签。"""
    ctx.reset()
    first_chars_label.config(text='')
    current_part_label.config(text='')
    page_label.config(text='')

def main_function(*args):
    """
    输入框内容变化时的回调函数（由 real_time_var 的 trace 触发）。
    处理输入解析、自动上字、空格上屏等核心逻辑。
    """
    input_text = real_time_var.get()

    # 处理特殊键（= 和 -）
    processed_text, new_cursor_pos, key_processed = handle_special_keys(input_text)
    if key_processed:
        ctx.selection_updating = True
        entry_box.delete(0, tk.END)
        entry_box.insert(0, processed_text)
        ctx.selection_updating = False
        if new_cursor_pos is not None:
            entry_box.icursor(new_cursor_pos)
        return

    if input_text.replace(" ", "") != ctx.last_input_text:
        ctx.current_page = 0
        ctx.current_part_index = -1
        ctx.query_type = ""
        ctx.split_parts = []
        ctx.in_part_selection = False
        ctx.current_phrase = ""
        if not ctx.selection_updating:
            ctx.resolved_chars = {}
            ctx.original_split_count = 0

    # ── 空格快速路径：跳过重复扫描，直接用缓存上屏 ──
    if " " in input_text:
        output_text = ctx.last_output_text
        if ctx.phrase_priority == "1" and ctx.query_type == "multi_part" and ctx.current_phrase:
            output_text = ctx.current_phrase[1:-1]
        elif output_text == "":
            if ctx.current_phrase:
                output_text = ctx.current_phrase[1:-1]
            else:
                output_text = process_input(input_text)
        replace_content(input_text, output_text, do_paste=True, reset_entry=True)
        reset_input_state()
        return

    processed = process_input(input_text)
    split_text = split_sequence(processed)
    output_text = ''
    candidates = ''
    first_chars = ''

    if split_text != "" and ' ' not in split_text:
        if "'" not in split_text:
            ctx.query_type = "single"
            candidates = query_single_char(split_text, ctx.current_page * 5)
            # 自动上字逻辑
            if candidates and ctx.auto_commit_enabled == "1" and len(split_text) > 3:
                candidates_list = candidates.split("/")
                non_dot_candidates = []
                for candidate in candidates_list:
                    code_part = candidate[1:] if len(candidate) > 1 else ""
                    if "." not in code_part:
                        non_dot_candidates.append(candidate)
                if len(non_dot_candidates) == 1:
                    selected_char = non_dot_candidates[0][0]
                    replace_content(input_text, selected_char, do_paste=True, reset_entry=True)
                    reset_input_state()
                    return
            update_display(processed=processed, candidates=candidates)
            if candidates != '':
                if "/" in candidates:
                    output_text = candidates.split("/")[0][0]
                else:
                    output_text = candidates[0]
        else:
            # 多字模式
            ctx.query_type = "multi_part"
            if "'" in processed and ctx.phrase_priority == "1":
                # 优先上词开启 + 用户手动输入单引号 → 词语增强预览
                phrase_result = get_phrase_segments(processed)
                if phrase_result:
                    display_text, all_parts = phrase_result
                    ctx.split_parts = all_parts
                    first_chars = display_text
                else:
                    # 某段无候选 → 清空（打错）
                    ctx.split_parts = []
                    first_chars = ""
            else:
                ctx.split_parts = [p for p in split_text.split("'") if p]
                first_chars = query_multi_chars(split_text)
            update_display(processed=processed, first_chars=first_chars)
            output_text = first_chars

    if key_processed:
        ctx.current_phrase = ""

    # 缓存计算结果，供 navigate_pages/navigate_parts 复用，供空格快速上屏使用
    ctx.last_output_text = output_text
    ctx._cached_processed = processed
    ctx._cached_processed_input = input_text
    ctx._cached_split_text = split_text
    clear_display_if_no_code(input_text)
    ctx.last_input_text = input_text

def on_key_press(event):
    """处理输入框内的按键事件（上下翻页和候选选择符号）。"""
    if event.keysym == "Down":
        navigate_pages("down")
    elif event.keysym == "Up":
        navigate_pages("up")
    else:
        result = handle_selection_keys(event)
        if result == "break":
            return "break"

# ==================== 全局输入监听（外输模式） ====================

def toggle():
    if ctx.external_mode:
        ctx.external_mode = False
        ctx.window.title("解书音形-内输")
        ctx.window.geometry(f"{win_w}x{win_h_norm}+{init_x}+{init_y}")
    else:
        ctx.external_mode = True
        ctx.window.title("解书音形-外输")
        x, y = win32api.GetCursorPos()
        x -= int(100 * scale)
        y -= int(10 * scale)
        ctx.window.geometry(f"{win_w}x{win_h_norm}+{x}+{y}")
    entry_box.delete(0, tk.END)
    entry_count_var.set(f"{get_entry_count()}")
    keyboard.press_and_release("shift")
    # 重置计数器
    ctx.reset_cursor_counters()

def initial(event):
    """
    全局键盘监听回调（外输模式时有效）。
    捕获按键并模拟输入到输入框，同时处理功能键。
    """
    if keyboard.is_pressed('ctrl') or keyboard.is_pressed('alt') or keyboard.is_pressed('win'):
        return
    if not ctx.external_mode or ctx.window_closing:
        ctx.key_press_counter = 0
        ctx.reset_cursor_counters()
        return

    ctx.key_press_counter += 1
    if ctx.key_press_counter == 2:
        ctx.key_press_counter = 1
        # 处理字母数字等编码键
        if event.name in "qwertyuiopasdfghjklzcxvbnm" or (event.name in ";.'1234567890" and ctx.has_code_chars()):
            # 在光标位置插入字符，因此只增加光标前的编码计数
            ctx.code_char_before_cursor += 1
            entry_box.insert(tk.INSERT, event.name)
        # 处理功能键
        elif event.name in ["-", "=", "!", "@", "#", "$", "%", "space", "up", "down", "left", "right", "backspace","enter"] and ctx.has_code_chars():
            if event.name == "-":
                navigate_parts("prev")
                time.sleep(0.04)
                keyboard.press_and_release("backspace")
            elif event.name == "=":
                navigate_parts("next")
                time.sleep(0.04)
                keyboard.press_and_release("backspace")
            elif event.name == "up":
                navigate_pages("up")
            elif event.name == "down":
                navigate_pages("down")
            elif event.name == "left":
                # 光标左移：光标前编码数减1，光标后编码数加1
                if ctx.code_char_before_cursor > 0:
                    ctx.code_char_before_cursor -= 1
                    ctx.code_char_after_cursor += 1
                entry_box.icursor(entry_box.index(tk.INSERT) - 1)
            elif event.name == "right":
                # 光标右移：光标后编码数减1，光标前编码数加1
                if ctx.code_char_after_cursor > 0:
                    ctx.code_char_after_cursor -= 1
                    ctx.code_char_before_cursor += 1
                entry_box.icursor(entry_box.index(tk.INSERT) + 1)
            elif event.name == "backspace":
                current_text = entry_box.get()
                cursor_pos = entry_box.index(tk.INSERT)
                if ctx.code_char_before_cursor > 0:
                    ctx.code_char_before_cursor -= 1
                if cursor_pos > 0:
                    # 如果光标前有编码字符，则退格会删除一个编码字符
                    new_text = current_text[:cursor_pos-1] + current_text[cursor_pos:]
                    entry_box.delete(0, tk.END)
                    entry_box.insert(0, new_text)
                    entry_box.icursor(cursor_pos - 1)

            elif event.name == "enter":
                entry_box.delete(0, tk.END)
                ctx.reset_cursor_counters()
                time.sleep(0.11)
                keyboard.press_and_release("backspace")
            elif event.name in ["!", "@", "#", "$", "%", "space"]:
  
                if event.name == "space":
                    ctx.code_char_before_cursor += 1
                    entry_box.insert(tk.INSERT, " ")

                else:
                    time.sleep(0.04)
                    keyboard.press_and_release("backspace")
                    char = event.name
                    ev = tk.Event()
                    ev.char = char
                    handle_selection_keys(ev)
    if not ctx.has_code_chars():
        entry_box.delete(0, tk.END)

def paste_text(text, reset_entry=True):
    """
    将文本粘贴到外部程序（外输模式）。
    先退格删除光标前的编码字符，再按 Delete 删除光标后的编码字符，然后模拟 Ctrl+V 粘贴。
    """
    if not ctx.external_mode or not text:
        return
    pyperclip.copy(text)
    for _ in range(ctx.code_char_before_cursor):
        keyboard.press_and_release("backspace")
    for _ in range(ctx.code_char_after_cursor):
        keyboard.press_and_release("delete")

    # 重置计数器
    ctx.reset_cursor_counters()

    keyboard.release("shift")
    time.sleep(0.04)
    keyboard.press_and_release('ctrl+v')

    if reset_entry:
        entry_box.delete(0, tk.END)
        real_time_var.set('')
    return True

def start_keyboard_listener():
    keyboard.add_hotkey('left+right', toggle, suppress=False)
    keyboard.on_press(initial, suppress=False)
    keyboard.wait('esc+1')
    keyboard.clear_all_hotkeys()
    ctx.external_mode = False
    ctx.key_press_counter = 0
    ctx.reset_cursor_counters()
    if ctx.window:
        ctx.window.title("解书音形-仅内输")

# 启动监听线程
keyboard_thread = threading.Thread(target=start_keyboard_listener, daemon=True)
keyboard_thread.start()

# ==================== 图形界面构建 ====================

try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

def get_dpi_scale(window):
    try:
        dpi = window.winfo_fpixels('1i')
        return dpi / 96.0
    except:
        return 1.0
    
window = tk.Tk()
ctx.window = window
scale = get_dpi_scale(window)
def scale_size(x):
    return int(round(x * scale))
BASE_WINDOW_W = 300
BASE_WINDOW_H_NORMAL = 110
BASE_WINDOW_H_EXPANDED = 280
BASE_PAD = 1
BASE_BORDER = 0.5
BASE_ROW_PADY = 1
LABEL_SPACING = scale_size(5)   
SMALL_SPACING = scale_size(1) 
win_w = scale_size(BASE_WINDOW_W)
win_h_norm = scale_size(BASE_WINDOW_H_NORMAL)
win_h_exp = scale_size(BASE_WINDOW_H_EXPANDED)
screen_width = window.winfo_screenwidth()
screen_height = window.winfo_screenheight()
base_width = 2880
base_height = 1920
init_x = int(screen_width * (2250 / base_width))
init_y = int(screen_height * (1250 / base_height))

window.title("解书音形-内输")
window.geometry(f"{win_w}x{win_h_norm}+{init_x}+{init_y}")
window.configure(bg='#FFF3C7')
window.attributes('-topmost', True)
window.attributes('-alpha', 0.95)

drag_start_x = 0
drag_start_y = 0
def start_drag(event):
    global drag_start_x, drag_start_y
    drag_start_x = event.x
    drag_start_y = event.y
def do_drag(event):
    x = window.winfo_x() + (event.x - drag_start_x)
    y = window.winfo_y() + (event.y - drag_start_y)
    window.geometry(f"+{x}+{y}")

primary_font = get_primary_font_name(window)
font_medium = (primary_font, FONT_SIZE_INPUT)
font_small = (FONT_SMALL_NAME, FONT_SIZE_SMALL)
bg_color = '#FFF3C7'
label_bg = '#EFE3AE'

real_time_var = tk.StringVar()
real_time_var.trace_add("write", main_function)

main_frame = tk.Frame(window, bg=bg_color, padx=scale_size(BASE_PAD), pady=0)
main_frame.pack(fill=tk.BOTH, expand=False)

entry_box = tk.Entry(main_frame, textvariable=real_time_var, font=font_medium, width=44,
                    relief=tk.FLAT, bg='#EFE3AE', highlightthickness=1, highlightcolor='#000000')
entry_box.pack(pady=(0, scale_size(BASE_PAD)))
entry_box.focus_set()
entry_box.bind("<KeyPress>", on_key_press)

display_frame = tk.Frame(main_frame, bg=bg_color)
display_frame.pack(fill=tk.X)
display_frame.bind("<ButtonPress-1>", start_drag)
display_frame.bind("<B1-Motion>", do_drag)

first_chars_label = tk.Label(display_frame, text="", font=font_medium, bg=label_bg,
                            relief=tk.RAISED, bd=scale_size(BASE_BORDER), padx=scale_size(BASE_PAD), pady=scale_size(BASE_PAD), width=0, anchor='w')
first_chars_label.pack(fill=tk.X, pady=(0, scale_size(BASE_PAD)))
first_chars_label.bind("<ButtonPress-1>", start_drag)
first_chars_label.bind("<B1-Motion>", do_drag)

current_part_label = tk.Label(display_frame, text="", font=font_medium, bg=label_bg,
                             relief=tk.RAISED, bd=scale_size(BASE_BORDER), padx=scale_size(BASE_PAD), pady=scale_size(BASE_PAD), width=0, anchor='w')
current_part_label.pack(fill=tk.X, pady=(0, scale_size(BASE_PAD)))
current_part_label.bind("<ButtonPress-1>", start_drag)
current_part_label.bind("<B1-Motion>", do_drag)

page_label = tk.Label(display_frame, text="", font=font_small, bg=bg_color,
                     fg='#666666', padx=0, pady=0)
page_label.pack(fill=tk.X)
page_label.bind("<ButtonPress-1>", start_drag)
page_label.bind("<B1-Motion>", do_drag)

main_status_frame = tk.Frame(window, bg='#FFF3C7', padx=scale_size(BASE_PAD), pady=scale_size(BASE_PAD))
main_status_frame.pack(fill=tk.BOTH, expand=False)

settings_frame = tk.Frame(main_status_frame, bg='#FFF3C7')
settings_frame.pack(fill=tk.X, pady=(0, scale_size(BASE_PAD)))

# 自动上字开关
auto_commit_var = tk.StringVar(value=ctx.auto_commit_enabled)
def toggle_auto_commit():
    if auto_commit_var.get() == "1":
        ctx.auto_commit_enabled = "1"
        auto_commit_label.config(text="自动上字", fg='#006600')
    else:
        ctx.auto_commit_enabled = ""
        auto_commit_label.config(text="自动上字", fg='#990000')
auto_commit_label = tk.Label(settings_frame, text="自动上字",
                            font=(FONT_BUTTON_NAME, FONT_SIZE_BUTTON), bg='#FFF3C7',
                            fg='#006600' if ctx.auto_commit_enabled == '1' else '#990000',
                            cursor="hand2")
auto_commit_label.pack(side=tk.LEFT, padx=(0, LABEL_SPACING))
def toggle_auto_commit_click(event):
    ctx.auto_commit_enabled = "1" if ctx.auto_commit_enabled != "1" else ""
    auto_commit_label.config(fg='#006600' if ctx.auto_commit_enabled == '1' else '#990000')
    auto_commit_var.set(ctx.auto_commit_enabled)
auto_commit_label.bind("<Button-1>", toggle_auto_commit_click)

# 优先上词开关
phrase_priority_var = tk.StringVar(value=ctx.phrase_priority)
def toggle_phrase_priority():
    if phrase_priority_var.get() == "1":
        ctx.phrase_priority = "1"
        phrase_priority_label.config(text="优先上词", fg='#006600')
    else:
        ctx.phrase_priority = ""
        phrase_priority_label.config(text="优先上词", fg='#990000')
phrase_priority_label = tk.Label(settings_frame, text="优先上词",
                               font=(FONT_BUTTON_NAME, FONT_SIZE_BUTTON), bg='#FFF3C7',
                               fg='#006600' if ctx.phrase_priority == '1' else '#990000',
                               cursor="hand2")
phrase_priority_label.pack(side=tk.LEFT, padx=(0, LABEL_SPACING))
def toggle_phrase_priority_click(event):
    ctx.phrase_priority = "1" if ctx.phrase_priority != "1" else ""
    phrase_priority_label.config(fg='#006600' if ctx.phrase_priority == '1' else '#990000')
    phrase_priority_var.set(ctx.phrase_priority)
phrase_priority_label.bind("<Button-1>", toggle_phrase_priority_click)

# 部首表开关
radical_table_var = tk.BooleanVar(value=False)
radical_table_frame = tk.Frame(main_status_frame, bg='#FFF3C7', relief=tk.SUNKEN, bd=1)
radical_table_frame.pack(fill=tk.BOTH, expand=False, pady=(0, 2))
radical_table_frame.pack_forget()  # 默认隐藏

radical_table_data = {
    "a(副)": "丶一丨丿乙乛𠃌乚𡿨",
    "b": "宀阝冫贝疒白卜八匕癶",
    "c": "车艹厂凵寸卄屮",
    "d": "刀歹大亠冖丷斗豆",
    "f": "风方父缶臼辰非",
    "g": "工广弓光囗革戈瓜艮谷骨",
    "h": "火户禾⺌羊虍黑",
    "i": "虫页雨弋彐彑臣赤𡗗尺",
    "j": "金巾廴冂几𠘨卩己见斤皀",
    "k": "口又舌用角",
    "l": "娄云勹力龙老卤里卵",
    "m": "木彡釆马门皿毛目矛米麦",
    "n": "女牛鸟耒齿",
    "o": "耳匚二儿㔾",
    "p": "攴片殳丬皮髟㐅",
    "q": "气犬豸欠青",
    "r": "人肉入日リ",
    "s": "示丝石尸十厶巳",
    "t": "土彳幺夕田",
    "u": "攵水矢手食山士豕身",
    "v": "乑争舟止爪鬼支",
    "w": "王网瓦韦隹文",
    "x": "穴𰃮心西小巛血辛习",
    "y": "言酉月鱼衣尢聿业羽黾音",
    "z": "辶竹足子自走",
    "0-9": "口丨一八㐅中大厂乙复"
}

def create_radical_table():
    for widget in radical_table_frame.winfo_children():
        widget.destroy()
    title_frame = tk.Frame(radical_table_frame, bg='#FFF3C7')
    title_frame.pack(fill=tk.X, pady=(scale_size(BASE_PAD), scale_size(BASE_PAD)))
    tk.Label(title_frame, text="部首码", font=(primary_font, FONT_SIZE_RADICAL),
            bg='#FFF3C7', fg='#000000', width=8, anchor='w').pack(side=tk.LEFT, padx=(scale_size(BASE_PAD), 0))
    tk.Label(title_frame, text="对应部首", font=(primary_font, FONT_SIZE_RADICAL),
            bg='#FFF3C7', fg='#000000', anchor='w').pack(side=tk.LEFT, padx=(scale_size(10), 0))
    separator = tk.Frame(radical_table_frame, height=scale_size(1), bg='#000000')
    separator.pack(fill=tk.X, pady=scale_size(BASE_PAD))

    table_container = tk.Frame(radical_table_frame, bg='#FFF3C7')
    table_container.pack(fill=tk.BOTH, expand=False)
    canvas = tk.Canvas(table_container, bg='#FFF3C7', highlightthickness=0)
    scrollable_frame = tk.Frame(canvas, bg='#FFF3C7')
    scrollable_frame.bind(
        "<Configure>",
        lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

    def on_mousewheel(event):
        canvas.yview_scroll(int(-1 * (event.delta / 60)), "units")
    canvas.bind_all("<MouseWheel>", on_mousewheel)
    scrollable_frame.bind("<MouseWheel>", on_mousewheel)
    def unbind_mousewheel(event=None):
        canvas.unbind_all("<MouseWheel>")
    radical_table_frame.bind("<Unmap>", unbind_mousewheel)

    canvas.pack(side="left", fill="both")

    for i, (letter, radicals) in enumerate(radical_table_data.items()):
        row_frame = tk.Frame(scrollable_frame, bg='#FFF3C7')
        row_frame.pack(fill=tk.X, pady=scale_size(BASE_ROW_PADY))
        letter_label = tk.Label(row_frame, text=letter, font=(primary_font, FONT_SIZE_RADICAL),
                               bg='#FFF3C7', fg='#3232BE', width=8, anchor='w')
        letter_label.pack(side=tk.LEFT, padx=(2, 0))
        radical_label = tk.Label(row_frame, text=radicals, font=(primary_font, FONT_SIZE_RADICAL),
                                bg='#FFF3C7', fg='#000000', anchor='w')
        radical_label.pack(side=tk.LEFT, padx=(2, 0))
        if i % 2 == 0:
            letter_label.config(bg='#EFE3AE')
            radical_label.config(bg='#EFE3AE')
            row_frame.config(bg='#EFE3AE')

create_radical_table()

def toggle_radical_table():
    if radical_table_var.get():
        radical_table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, scale_size(10)))
        radical_table_label.config(text="部首表", fg='#006600')
        window.geometry(f"{win_w}x{win_h_exp}")
        create_radical_table()
    else:
        radical_table_frame.pack_forget()
        radical_table_label.config(text="部首表", fg='#990000')
        window.geometry(f"{win_w}x{win_h_norm}")

radical_table_label = tk.Label(settings_frame, text="部首表",
                              font=(FONT_BUTTON_NAME, FONT_SIZE_BUTTON), bg='#FFF3C7',
                              fg='#006600' if radical_table_var.get() else '#990000',
                              cursor="hand2")
radical_table_label.pack(side=tk.LEFT, padx=(0, LABEL_SPACING))
def toggle_radical_table_click(event):
    current_state = radical_table_var.get()
    radical_table_var.set(not current_state)
    radical_table_label.config(fg='#006600' if radical_table_var.get() else '#990000')
    toggle_radical_table()
radical_table_label.bind("<Button-1>", toggle_radical_table_click)

# 词条计数显示
entry_count_var = tk.StringVar()
entry_count_var.set(f"{get_entry_count()}")
entry_count_label = tk.Label(settings_frame, textvariable=entry_count_var,
                           font=(primary_font, FONT_SIZE_COUNT), bg='#FFF3C7', fg='#000000')
entry_count_label.pack(side=tk.LEFT, padx=(0, SMALL_SPACING))

def on_main_window_close():
    ctx.window_closing = True
    keyboard.unhook_all()  # 移除所有热键和全局监听钩子
    ctx.window.destroy()
window.protocol("WM_DELETE_WINDOW", on_main_window_close)
window.mainloop()
