import tkinter as tk
import os
import pyperclip
import keyboard
import threading
import time
import win32api

# ==================== 导入模块化组件 ====================
from config import DATA_FILE, CODE_CHARS, SURROUND_CHARS, SELECTION_SYMBOLS, SYMBOL_TO_INDEX, CIYU_FILE
from manager.dictionary import ensure_data_file as _ensure_data_file, query_phrase as _query_phrase, get_entry_count as _get_entry_count, query_by_prefix as _query_by_prefix

# ==================== 常量定义（备用兼容） ====================
# DATA_FILE 在 config 中定义
# CODE_CHARS 在 config 中定义  
# SURROUND_CHARS 在 config 中定义
# SELECTION_SYMBOLS 在 config 中定义
# SYMBOL_TO_INDEX 在 config 中定义

# ==================== 全局状态变量 ====================
current_page = 0                           # 当前候选页码（0起始）
current_query_type = ""                     # 当前查询类型："single"单字 / "multi_part"多字
current_phrase = ""                         # 当前匹配到的短语，格式如"(词语)"
current_part_index = -1                      # 多字选择时当前部件索引
current_split_parts = []                     # 多字输入时拆分后的部件列表
in_part_selection = False                    # 是否处于多字部件选择模式
last_input_text = ""                         # 上一次输入的文本，用于检测变化重置状态
auto_commit_enabled = "1"                    # 自动上字开关（"1"启用）
phrase_priority = "1"                        # 优先上词开关（"1"启用）
external_mode = False                        # 外输模式开关（True表示外输）
window = None                               # 主窗口对象
window_closing = False   # 窗口是否正在关闭
# 外输模式下的辅助变量
key_press_counter = 0           # 按键计数防抖
code_char_before_cursor = 0     # 光标前的编码字符数
code_char_after_cursor = 0      # 光标后的编码字符数

# ==================== 词典文件操作 ====================

def ensure_data_file():
    """确保词典文件存在，若不存在则创建空文件"""
    return _ensure_data_file()

def query_phrase(code):
    """从词库文件 ciyu.txt 中查询短语"""
    return _query_phrase(code)

def get_entry_count():
    """返回词典文件中的词条总数"""
    return _get_entry_count()

def query_by_prefix(prefix, start_idx=0, count=5):
    """
    根据编码前缀查询候选词。支持副码a和补码规则
    注：输入法特有的补码处理逻辑，保留本地实现
    """
    # 直接调用 manager 模块的实现
    return _query_by_prefix(prefix, start_idx, count)

# ==================== 输入处理核心函数 ====================

def process_input(input_text):#从输入文本中提取连续的合法编码字符（CODE_CHARS）。
    result = ""
    start_collecting = False
    for char in input_text:
        if not start_collecting and 'a' <= char <= 'z':
            start_collecting = True
        if start_collecting and char in CODE_CHARS:
            result += char
    return result

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
    if do_paste and external_mode:
        paste_text(output, reset_entry)
    else:
        pyperclip.copy(output)
        entry_box.delete(0, tk.END)
        entry_box.insert(0, output)
        real_time_var.set(output)

def split_sequence(original):
    """
    对连续编码进行自动分词（插入单引号）。
    根据多种条件递归分割，使每个部件长度合理。
    返回用单引号分隔的字符串。
    """
    parts = original.split("'")
    can_split_more = True
    while can_split_more:
        can_split_more = False
        new_parts = []
        for part in parts:
            # 判断各种需要分割的条件
            condition1 = False   # 连续双拼
            condition2 = False   # 调码定位
            condition3 = False   # 独体字四码打全
            condition4 = False   # 合体字五码打全
            condition5 = False   # 补码打全
            positions = []       # 用于条件2的插入位置
            positions3 = []      # 用于条件3的数字位置（在其后插入）
            if not any(char.isdigit() for char in part) and len(part) > 2:
                condition1 = True
            for index, char in enumerate(part):
                if char.isdigit() and index > 2 and not part[index-1].isdigit():
                    condition2 = True
                    positions.append(index)
                if (char.isdigit() and index > 0 and part[index-1].isdigit()
                        and index + 1 < len(part)):
                    if part[index+1]!="." and not part[index+1].isdigit():
                        condition3 = True
                        positions3.append(index)
            if len(part) > 5 and '.' not in part:
                condition4 = True
            if '.' in part and len(part.split(".")[1]) > 1:
                condition5 = True

            if condition1:
                new_part = "'".join([part[i:i+2] for i in range(0, len(part), 2)])
                new_parts.extend(new_part.split("'"))
                can_split_more = True
            elif condition2:
                new_part = part
                for pos in sorted(positions, reverse=True):
                    new_part = new_part[:pos-2] + "'" + new_part[pos-2:]
                new_parts.extend(new_part.split("'"))
                can_split_more = True
            elif condition3:
                new_part = part
                for pos in sorted(positions3, reverse=True):
                    new_part = new_part[:pos+1] + "'" + new_part[pos+1:]
                new_parts.extend(new_part.split("'"))
                can_split_more = True
            elif condition4:
                new_part = part[:5] + "'" + part[5:]
                new_parts.extend(new_part.split("'"))
                can_split_more = True
            elif condition5:
                ff = len(part.split(".")[0]) + 2
                new_part = part[:ff] + "'" + part[ff:]
                new_parts.extend(new_part.split("'"))
                can_split_more = True
            else:
                new_parts.append(part)
        parts = new_parts
    parts = [part for part in parts if part != '']
    return "'".join(parts)

def query_single_char(split_text, start_idx=0):
    """
    查询单字候选，返回用'/'连接的候选字符串（每个候选带后缀）。
    若没有候选返回空字符串。
    """
    candidates = query_by_prefix(split_text, start_idx)
    if candidates:
        return "/".join(candidates)
    else:
        return ""

def query_multi_chars(split_text):
    """
    多字输入时，获取每个部件的第一候选的首字，拼接成预览串。
    若某个部件无候选，返回空字符串。
    """
    char_codes = split_text.split("'")
    first_chars = ''
    for code in char_codes:
        candidates = query_by_prefix(code)
        if candidates:
            first_char = candidates[0][0]
            first_chars += first_char
        else:
            return ""
    return first_chars

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
    direction: "next" 或 "prev"
    """
    global current_part_index, current_page, in_part_selection, current_phrase
    if current_query_type != "multi_part" or not current_split_parts:
        return
    if not in_part_selection:
        if direction == "next":
            in_part_selection = True
            current_phrase = ""
            current_part_index = 0
    else:
        current_phrase = ""
        if direction == "next":
            current_part_index = (current_part_index + 1) % len(current_split_parts)
        elif direction == "prev":
            current_part_index = (current_part_index - 1) % len(current_split_parts)
    current_page = 0
    update_display()

def navigate_pages(direction):
    """
    翻页：direction "down" 下一页， "up" 上一页。
    """
    global current_page
    if direction == "down":
        input_text = real_time_var.get()
        processed = process_input(input_text)
        split_text = split_sequence(processed)
        if current_query_type == "single":
            next_page_candidates = query_single_char(split_text, (current_page + 1) * 5)
            if next_page_candidates:
                current_page += 1
        elif current_query_type == "multi_part" and current_split_parts and current_part_index >= 0:
            part = current_split_parts[current_part_index]
            next_page_candidates = query_single_char(part, (current_page + 1) * 5)
            if next_page_candidates:
                current_page += 1
    elif direction == "up" and current_page > 0:
        current_page -= 1
    update_display()

def update_display():
    """
    根据当前状态更新下方的三个显示标签：
      - first_chars_label: 多字预览串（或短语）
      - current_part_label: 当前部件的候选列表
      - page_label: 页码信息
    """
    global current_part_index, current_page, current_query_type, current_split_parts, in_part_selection, current_phrase
    input_text = real_time_var.get()
    processed = process_input(input_text)
    split_text = split_sequence(processed)
    current_phrase = query_phrase(processed)

    # 清空标签，准备重新显示
    first_chars_label.config(text='')
    current_part_label.config(text='')
    page_label.config(text='')

    if current_query_type == "multi_part":
        first_chars = query_multi_chars(split_text)
        if first_chars:
            if current_phrase and not in_part_selection:
                # 如果短语存在且不在部件选择模式，显示预览串和短语
                if first_chars == current_phrase[1:-1]:
                    first_chars_label.config(text=first_chars)
                    current_phrase = ""
                else:
                    first_chars_label.config(text=first_chars + "   " + current_phrase)
            else:
                first_chars_label.config(text=first_chars)
        elif current_phrase:
            first_chars_label.config(text=current_phrase)

        if first_chars and in_part_selection and current_part_index >= 0 and current_part_index < len(current_split_parts):
            part = current_split_parts[current_part_index]
            candidates = query_single_char(part, current_page * 5)
            if candidates:
                current_phrase = ""
                current_part_label.config(text=candidates)
                page_label.config(text=f"字 {current_part_index + 1}/{len(current_split_parts)} 页 {current_page + 1}")

    elif current_query_type == "single":
        candidates = query_single_char(split_text, current_page * 5)
        if candidates:
            current_part_label.config(text=candidates)
            page_label.config(text=f"页 {current_page + 1}")

def handle_special_keys(input_text):
    """
    处理输入中的 '=' 和 '-' 键，用于多字部件导航。
    返回 (新文本, 新光标位置, 是否已处理) 三元组。
    """
    global current_phrase
    if '=' in input_text or '-' in input_text:
        cursor_pos = entry_box.index(tk.INSERT)
        if current_query_type == "multi_part" and current_split_parts:
            equals_pos = input_text.find('=')
            minus_pos = input_text.find('-')
            if equals_pos != -1:
                current_phrase = ""
                navigate_parts("next")
                new_text = input_text[:equals_pos] + input_text[equals_pos+1:]
                if cursor_pos > equals_pos:
                    new_cursor_pos = cursor_pos - 1
                else:
                    new_cursor_pos = cursor_pos
                return new_text, new_cursor_pos, True
            if minus_pos != -1:
                current_phrase = ""
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
    返回字符串列表，若无候选返回空列表。
    """
    input_text = real_time_var.get()
    processed = process_input(input_text)
    split_text = split_sequence(processed)
    if current_query_type == "single":
        candidates = query_single_char(split_text, current_page * 5)
        if candidates:
            return candidates.split("/")
    elif current_query_type == "multi_part" and current_split_parts and current_part_index >= 0:
        part = current_split_parts[current_part_index]
        candidates = query_single_char(part, current_page * 5)
        if candidates:
            current_phrase = ""
            return candidates.split("/")
    return []

def handle_selection_keys(event):
    """
    处理候选选择符号 ! @ # $ % 以及短语直接上屏 !（当有短语时）
    返回 "break" 阻止事件继续传播，否则返回 None。
    """
    global current_split_parts, current_phrase
    # 短语直接上屏：当前有短语且按下 !
    if event.char == "!" and current_phrase:
        phrase_content = current_phrase[1:-1]
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
            selected_char = candidates[index][0]  # 取候选的第一个汉字
            input_text = real_time_var.get()
            if current_query_type == "single":
                replace_content(input_text, selected_char, do_paste=True, reset_entry=True)
                reset_input_state()
            elif current_query_type == "multi_part" and current_split_parts and current_part_index >= 0:
                processed = process_input(input_text)
                split_text = split_sequence(processed)
                if "'" in split_text:
                    parts = split_text.split("'")
                    if current_part_index < len(parts):
                        new_parts = parts.copy()
                        new_parts[current_part_index] = selected_char
                        new_processed = "".join(new_parts)
                        is_last_part = current_part_index == len(parts) - 1
                        if is_last_part:
                            replace_content(input_text, new_processed, do_paste=True, reset_entry=True)
                            reset_input_state()
                        else:
                            replace_content(input_text, new_processed, do_paste=False, reset_entry=False)
                            navigate_parts("next")
        return "break"

def reset_input_state():
    """重置所有输入相关的状态变量，并清空显示标签。"""
    global current_page, current_part_index, current_query_type, current_split_parts, in_part_selection, current_phrase
    current_page = 0
    current_part_index = -1
    current_query_type = ""
    current_split_parts = []
    in_part_selection = False
    current_phrase = ""
    first_chars_label.config(text='')
    current_part_label.config(text='')
    page_label.config(text='')

def main_function(*args):
    """
    输入框内容变化时的回调函数（由 real_time_var 的 trace 触发）。
    处理输入解析、自动上字、空格上屏等核心逻辑。
    """
    global current_page, current_part_index, current_query_type, current_split_parts, last_input_text
    global in_part_selection, current_phrase, auto_commit_enabled
    input_text = real_time_var.get()

    # 处理特殊键（= 和 -）
    processed_text, new_cursor_pos, key_processed = handle_special_keys(input_text)
    if key_processed:
        entry_box.delete(0, tk.END)
        entry_box.insert(0, processed_text)
        if new_cursor_pos is not None:
            entry_box.icursor(new_cursor_pos)
        return

    # 如果输入发生变化，重置状态（除了 previous_input 的比较）
    if input_text.strip() != last_input_text:
        current_page = 0
        current_part_index = -1
        current_query_type = ""
        current_split_parts = []
        in_part_selection = False
        current_phrase = ""

    processed = process_input(input_text)
    split_text = split_sequence(processed)
    output_text = ''
    candidates = ''
    first_chars = ''

    if split_text != "" and ' ' not in split_text:
        if "'" not in split_text:
            # 单字模式
            current_query_type = "single"
            candidates = query_single_char(split_text, current_page * 5)
            # 自动上字逻辑
            if candidates and auto_commit_enabled == "1" and len(processed) > 3:
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
            update_display()
            if candidates != '':
                if "/" in candidates:
                    output_text = candidates.split("/")[0][0]
                else:
                    output_text = candidates[0]
        else:
            # 多字模式
            current_query_type = "multi_part"
            first_chars = query_multi_chars(split_text)
            if first_chars:
                current_split_parts = split_text.split("'")
            update_display()
            output_text = first_chars

    if key_processed:
        current_phrase = ""

    # 处理空格上屏
    if " " in input_text:
        if phrase_priority == "1" and current_query_type == "multi_part" and current_phrase:
            output_text = current_phrase[1:-1]
        elif output_text == "":
            if current_phrase:
                output_text = current_phrase[1:-1]
            else:
                output_text = processed
                
        replace_content(input_text, output_text, do_paste=True, reset_entry=True)
        reset_input_state()
        return

    clear_display_if_no_code(input_text)
    last_input_text = input_text

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
    """切换内外输模式，热键：左+右"""
    global external_mode, code_char_before_cursor, code_char_after_cursor
    if external_mode:
        external_mode = False
        window.title("解书音形-内输")
        window.geometry(f"+2250+1250")
    else:
        external_mode = True
        window.title("解书音形-外输")
        x, y = win32api.GetCursorPos()
        x -= 230
        y -= 10
        window.geometry(f"+{x}+{y}")
    entry_box.delete(0, tk.END)
    entry_count_var.set(f"{get_entry_count()}")
    keyboard.press_and_release("shift")
    # 重置计数器
    code_char_before_cursor = 0
    code_char_after_cursor = 0
def initial(event):
    """
    全局键盘监听回调（外输模式时有效）。
    捕获按键并模拟输入到输入框，同时处理功能键。
    """
    global key_press_counter, code_char_before_cursor, code_char_after_cursor, external_mode, window_closing
    if keyboard.is_pressed('ctrl') or keyboard.is_pressed('alt') or keyboard.is_pressed('win'):
        return
    if not external_mode or window_closing:
        key_press_counter = 0
        code_char_before_cursor = 0
        code_char_after_cursor = 0
        return

    key_press_counter += 1
    if key_press_counter == 2:
        key_press_counter = 1
        # 处理字母数字等编码键
        if event.name in "qwertyuiopasdfghjklzcxvbnm" or (event.name in ";.'1234567890" and code_char_before_cursor + code_char_after_cursor != 0):
            # 在光标位置插入字符，因此只增加光标前的编码计数
            code_char_before_cursor += 1
            entry_box.insert(tk.INSERT, event.name)
        # 处理功能键
        elif event.name in ["-", "=", "!", "@", "#", "$", "%", "space", "up", "down", "left", "right", "backspace","enter"] and code_char_before_cursor + code_char_after_cursor != 0:
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
                if code_char_before_cursor > 0:
                    code_char_before_cursor -= 1
                    code_char_after_cursor += 1
                entry_box.icursor(entry_box.index(tk.INSERT) - 1)
            elif event.name == "right":
                # 光标右移：光标后编码数减1，光标前编码数加1
                if code_char_after_cursor > 0:
                    code_char_after_cursor -= 1
                    code_char_before_cursor += 1
                entry_box.icursor(entry_box.index(tk.INSERT) + 1)
            elif event.name == "backspace":
                current_text = entry_box.get()
                cursor_pos = entry_box.index(tk.INSERT)
                if cursor_pos > 0:
                    # 如果光标前有编码字符，则退格会删除一个编码字符
                    new_text = current_text[:cursor_pos-1] + current_text[cursor_pos:]
                    entry_box.delete(0, tk.END)
                    entry_box.insert(0, new_text)
                    entry_box.icursor(cursor_pos - 1)
                if code_char_before_cursor > 0:
                    code_char_before_cursor -= 1
            elif event.name == "enter":
                entry_box.delete(0, tk.END)
                code_char_before_cursor = 0
                code_char_after_cursor = 0
                keyboard.press_and_release("left")
            elif event.name in ["!", "@", "#", "$", "%", "space"]:
  
                if event.name == "space":
                    code_char_before_cursor += 1
                    entry_box.insert(tk.INSERT, " ")

                else:
                    time.sleep(0.04)
                    keyboard.press_and_release("backspace")
                    char = event.name
                    ev = tk.Event()
                    ev.char = char
                    handle_selection_keys(ev)
    if code_char_before_cursor + code_char_after_cursor == 0:
        entry_box.delete(0, tk.END)

def paste_text(text, reset_entry=True):
    """
    将文本粘贴到外部程序（外输模式）。
    先退格删除光标前的编码字符，再按 Delete 删除光标后的编码字符，然后模拟 Ctrl+V 粘贴。
    """
    global external_mode, code_char_before_cursor, code_char_after_cursor
    if not external_mode or not text:
        return
    pyperclip.copy(text)
    for _ in range(code_char_before_cursor):
        keyboard.press_and_release("backspace")
    for _ in range(code_char_after_cursor):
        keyboard.press_and_release("delete")

    # 重置计数器
    code_char_before_cursor = 0
    code_char_after_cursor = 0

    keyboard.release("shift")
    time.sleep(0.02)
    keyboard.press_and_release('ctrl+v')

    if reset_entry:
        entry_box.delete(0, tk.END)
        real_time_var.set('')
    return True

def start_keyboard_listener():
    global external_mode, key_press_counter, code_char_before_cursor, code_char_after_cursor
    keyboard.add_hotkey('left+right', toggle, suppress=False)
    keyboard.on_press(initial, suppress=False)
    keyboard.wait('esc+1')
    keyboard.clear_all_hotkeys()
    external_mode = False
    key_press_counter = 0
    code_char_before_cursor = 0
    code_char_after_cursor = 0
    if window:
        window.title("解书音形-仅内输")

# 启动监听线程
keyboard_thread = threading.Thread(target=start_keyboard_listener, daemon=True)
keyboard_thread.start()

# ==================== 图形界面构建 ====================

try:
    from ctypes import windll
    windll.shcore.SetProcessDpiAwareness(1)
except:
    pass

window = tk.Tk()
window.title("解书音形-内输")
window.geometry(f"600x215+2250+1250")
window.configure(bg='#FFF3C7')
window.attributes('-topmost', True)
window.attributes('-alpha', 0.95)

# 窗口拖动功能
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

font_medium = ("华文中宋", 13)
font_small = ("黑体", 8)
bg_color = '#FFF3C7'
label_bg = '#EFE3AE'

real_time_var = tk.StringVar()
real_time_var.trace_add("write", main_function)

main_frame = tk.Frame(window, bg=bg_color, padx=2, pady=0)
main_frame.pack(fill=tk.BOTH, expand=False)

entry_box = tk.Entry(main_frame, textvariable=real_time_var, font=font_medium, width=44,
                    relief=tk.FLAT, bg='#EFE3AE', highlightthickness=1, highlightcolor='#000000')
entry_box.pack(pady=(0, 2))
entry_box.focus_set()
entry_box.bind("<KeyPress>", on_key_press)

display_frame = tk.Frame(main_frame, bg=bg_color)
display_frame.pack(fill=tk.X)
display_frame.bind("<ButtonPress-1>", start_drag)
display_frame.bind("<B1-Motion>", do_drag)

first_chars_label = tk.Label(display_frame, text="", font=font_medium, bg=label_bg,
                            relief=tk.RAISED, bd=1, padx=2, pady=2, width=0, anchor='w')
first_chars_label.pack(fill=tk.X, pady=(0, 2))
first_chars_label.bind("<ButtonPress-1>", start_drag)
first_chars_label.bind("<B1-Motion>", do_drag)

current_part_label = tk.Label(display_frame, text="", font=font_medium, bg=label_bg,
                             relief=tk.RAISED, bd=1, padx=2, pady=2, width=0, anchor='w')
current_part_label.pack(fill=tk.X, pady=(0, 2))
current_part_label.bind("<ButtonPress-1>", start_drag)
current_part_label.bind("<B1-Motion>", do_drag)

page_label = tk.Label(display_frame, text="", font=font_small, bg=bg_color,
                     fg='#666666', padx=0, pady=0)
page_label.pack(fill=tk.X)
page_label.bind("<ButtonPress-1>", start_drag)
page_label.bind("<B1-Motion>", do_drag)

main_status_frame = tk.Frame(window, bg='#FFF3C7', padx=2, pady=2)
main_status_frame.pack(fill=tk.BOTH, expand=False)

settings_frame = tk.Frame(main_status_frame, bg='#FFF3C7')
settings_frame.pack(fill=tk.X, pady=(0, 2))

# 自动上字开关
auto_commit_var = tk.StringVar(value=auto_commit_enabled)
def toggle_auto_commit():
    global auto_commit_enabled
    if auto_commit_var.get() == "1":
        auto_commit_enabled = "1"
        auto_commit_label.config(text="自动上字", fg='#006600')
    else:
        auto_commit_enabled = ""
        auto_commit_label.config(text="自动上字", fg='#990000')
auto_commit_label = tk.Label(settings_frame, text="自动上字",
                            font=("楷体", 14), bg='#FFF3C7',
                            fg='#006600' if auto_commit_enabled == '1' else '#990000',
                            cursor="hand2")
auto_commit_label.pack(side=tk.LEFT, padx=(0, 10))
def toggle_auto_commit_click(event):
    global auto_commit_enabled
    auto_commit_enabled = "1" if auto_commit_enabled != "1" else ""
    auto_commit_label.config(fg='#006600' if auto_commit_enabled == '1' else '#990000')
    auto_commit_var.set(auto_commit_enabled)
auto_commit_label.bind("<Button-1>", toggle_auto_commit_click)

# 优先上词开关
phrase_priority_var = tk.StringVar(value=phrase_priority)
def toggle_phrase_priority():
    global phrase_priority
    if phrase_priority_var.get() == "1":
        phrase_priority = "1"
        phrase_priority_label.config(text="优先上词", fg='#006600')
    else:
        phrase_priority = ""
        phrase_priority_label.config(text="优先上词", fg='#990000')
phrase_priority_label = tk.Label(settings_frame, text="优先上词",
                               font=("楷体", 14), bg='#FFF3C7',
                               fg='#006600' if phrase_priority == '1' else '#990000',
                               cursor="hand2")
phrase_priority_label.pack(side=tk.LEFT, padx=(0, 10))
def toggle_phrase_priority_click(event):
    global phrase_priority
    phrase_priority = "1" if phrase_priority != "1" else ""
    phrase_priority_label.config(fg='#006600' if phrase_priority == '1' else '#990000')
    phrase_priority_var.set(phrase_priority)
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
    "i": "虫页雨弋彐彑臣赤尺",
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
    """创建部首表内容（带滚动条）"""
    for widget in radical_table_frame.winfo_children():
        widget.destroy()
    title_frame = tk.Frame(radical_table_frame, bg='#FFF3C7')
    title_frame.pack(fill=tk.X, pady=(2, 2))
    tk.Label(title_frame, text="部首码", font=("华文中宋", 11),
            bg='#FFF3C7', fg='#000000', width=8, anchor='w').pack(side=tk.LEFT, padx=(2, 0))
    tk.Label(title_frame, text="对应部首", font=("华文中宋", 11),
            bg='#FFF3C7', fg='#000000', anchor='w').pack(side=tk.LEFT, padx=(10, 0))
    separator = tk.Frame(radical_table_frame, height=1, bg='#000000')
    separator.pack(fill=tk.X, pady=2)

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
        row_frame.pack(fill=tk.X, pady=1)
        letter_label = tk.Label(row_frame, text=letter, font=("华文中宋", 11),
                               bg='#FFF3C7', fg='#3232BE', width=8, anchor='w')
        letter_label.pack(side=tk.LEFT, padx=(2, 0))
        radical_label = tk.Label(row_frame, text=radicals, font=("华文中宋", 11),
                                bg='#FFF3C7', fg='#000000', anchor='w')
        radical_label.pack(side=tk.LEFT, padx=(2, 0))
        if i % 2 == 0:
            letter_label.config(bg='#EFE3AE')
            radical_label.config(bg='#EFE3AE')
            row_frame.config(bg='#EFE3AE')

create_radical_table()

def toggle_radical_table():
    """展开/折叠部首表"""
    if radical_table_var.get():
        radical_table_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        radical_table_label.config(text="部首表", fg='#006600')
        window.geometry("600x565")
        create_radical_table()
    else:
        radical_table_frame.pack_forget()
        radical_table_label.config(text="部首表", fg='#990000')
        window.geometry("600x215")

radical_table_label = tk.Label(settings_frame, text="部首表",
                              font=("楷体", 14), bg='#FFF3C7',
                              fg='#006600' if radical_table_var.get() else '#990000',
                              cursor="hand2")
radical_table_label.pack(side=tk.LEFT, padx=(0, 10))
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
                           font=("华文中宋", 14), bg='#FFF3C7', fg='#000000')
entry_count_label.pack(side=tk.LEFT, padx=(0, 2))

def on_main_window_close():
    global window_closing
    window_closing = True
    keyboard.unhook_all()  # 移除所有热键和全局监听钩子
    window.destroy()
window.protocol("WM_DELETE_WINDOW", on_main_window_close)
window.mainloop()
