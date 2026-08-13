

"""
命令行模拟输入法前端
- 默认词语优先
- 输入末尾自动补空格
- 每次输入独立
- 支持管道输入/输出
"""

import sys
import os
dep_dir = os.environ.get("JIESHU_IME_HOME", r"D:\USB\Py\输入法")
if dep_dir not in sys.path:
    sys.path.insert(0, dep_dir)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import DATA_FILE, CODE_CHARS, SURROUND_CHARS, SELECTION_SYMBOLS, SYMBOL_TO_INDEX, CIYU_FILE
from manager.dictionary_frontend import (
    ensure_data_file, query_phrase, get_entry_count,
    query_by_prefix, process_input, split_sequence,
    query_single_char, query_multi_chars, query_multi_chars_phrase,
    get_phrase_segments
)


class SimulatedIME:
    def __init__(self):
        # 全局状态（与前端一致）
        self.current_page = 0
        self.current_query_type = ""
        self.current_phrase = ""
        self.current_part_index = -1
        self.current_split_parts = []
        self.in_part_selection = False
        self.last_input_text = ""
        self.selection_updating = False
        self.resolved_chars = {}
        self.original_split_count = 0
        self.auto_commit_enabled = "1"
        self.phrase_priority = "1"          # 默认词语优先

        self.input_text = ""
        self.output_history = []

    def reset_state(self):
        self.current_page = 0
        self.current_part_index = -1
        self.current_query_type = ""
        self.current_split_parts = []
        self.in_part_selection = False
        self.current_phrase = ""
        self.resolved_chars = {}
        self.original_split_count = 0

    def reset_all(self):
        self.input_text = ""
        self.last_input_text = ""
        self.output_history = []
        self.reset_state()

    # ---------- 核心处理函数 ----------

    def _replace_content(self, original, processed, do_paste=False, reset_entry=True):
        first_letter_pos = -1
        for i, char in enumerate(original):
            if 'a' <= char <= 'z':
                first_letter_pos = i
                break
        last_letter_pos = -1
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

        if do_paste:
            if output:
                self.output_history.append(output)
            if reset_entry:
                self.input_text = ""
                self.reset_state()
            else:
                self.input_text = output
        else:
            self.input_text = output
        return output

    def _navigate_parts(self, direction):
        if self.current_query_type != "multi_part" or not self.current_split_parts:
            return
        if not self.in_part_selection:
            if direction == "next":
                self.in_part_selection = True
                self.current_phrase = ""
                for idx in range(len(self.current_split_parts)):
                    if idx not in self.resolved_chars:
                        self.current_part_index = idx
                        break
        else:
            self.current_phrase = ""
            n = len(self.current_split_parts)
            if direction == "next":
                for offset in range(1, n + 1):
                    candidate = (self.current_part_index + offset) % n
                    if candidate not in self.resolved_chars:
                        self.current_part_index = candidate
                        break
            elif direction == "prev":
                for offset in range(1, n + 1):
                    candidate = (self.current_part_index - offset) % n
                    if candidate not in self.resolved_chars:
                        self.current_part_index = candidate
                        break
        self.current_page = 0

    def _navigate_pages(self, direction):
        if direction == "down":
            processed = process_input(self.input_text)
            split_text = split_sequence(processed)
            if self.current_query_type == "single":
                next_page_candidates = query_single_char(split_text, (self.current_page + 1) * 5)
                if next_page_candidates:
                    self.current_page += 1
            elif self.current_query_type == "multi_part" and self.current_split_parts and self.current_part_index >= 0:
                part = self.current_split_parts[self.current_part_index]
                next_page_candidates = query_single_char(part, (self.current_page + 1) * 5)
                if next_page_candidates:
                    self.current_page += 1
        elif direction == "up" and self.current_page > 0:
            self.current_page -= 1

    def _get_current_candidates(self):
        processed = process_input(self.input_text)
        split_text = split_sequence(processed)
        if self.current_query_type == "single":
            candidates = query_single_char(split_text, self.current_page * 5)
            if candidates:
                return candidates.split("/")
        elif self.current_query_type == "multi_part" and self.current_split_parts and self.current_part_index >= 0:
            part = self.current_split_parts[self.current_part_index]
            candidates = query_single_char(part, self.current_page * 5)
            if candidates:
                self.current_phrase = ""
                return candidates.split("/")
        return []

    def _handle_selection_keys(self, ch):
        if ch == "!" and self.current_phrase:
            phrase_content = self.current_phrase[1:-1]
            self._replace_content(self.input_text, phrase_content, do_paste=True, reset_entry=True)
            self.reset_state()
            return True

        if ch in SELECTION_SYMBOLS:
            candidates = self._get_current_candidates()
            if not candidates:
                return False
            index = SYMBOL_TO_INDEX.get(ch, -1)
            if 0 <= index < len(candidates):
                candidate_str = candidates[index]
                selected_char = candidate_str[0]
                remaining = candidate_str[1:]
                original = self.input_text

                if self.current_query_type == "single":
                    self._replace_content(original, selected_char, do_paste=True, reset_entry=True)
                    self.reset_state()
                elif self.current_query_type == "multi_part" and self.current_split_parts and self.current_part_index >= 0:
                    i = self.current_part_index
                    parts = list(self.current_split_parts)
                    if i >= len(parts):
                        return False
                    self.resolved_chars[i] = selected_char
                    if self.original_split_count == 0:
                        self.original_split_count = len(parts)
                    prefix = parts[i]
                    parts[i] = prefix + remaining
                    new_code_sequence = "'".join(parts)
                    unresolved = self.original_split_count - len(self.resolved_chars)
                    if unresolved == 0:
                        final_text = "".join(
                            self.resolved_chars[j] for j in sorted(self.resolved_chars.keys())
                        )
                        self.selection_updating = True
                        self._replace_content(original, final_text, do_paste=True, reset_entry=True)
                        self.selection_updating = False
                        self.reset_state()
                    else:
                        self.selection_updating = True
                        self._replace_content(original, new_code_sequence, do_paste=False, reset_entry=False)
                        self.selection_updating = False
                        self._navigate_parts("next")
                return True
        return False

    def _on_input_change(self):
        """
        核心处理函数 —— 修复点：在这里查询短语并更新 self.current_phrase
        """
        input_text = self.input_text
        if input_text.strip() != self.last_input_text:
            self.current_page = 0
            self.current_part_index = -1
            self.current_query_type = ""
            self.current_split_parts = []
            self.in_part_selection = False
            self.current_phrase = ""
            if not self.selection_updating:
                self.resolved_chars = {}
                self.original_split_count = 0

        processed = process_input(input_text)
        split_text = split_sequence(processed)

        # 整串查询短语（不含手动单引号分隔的场景）
        if "'" not in processed:
            self.current_phrase = query_phrase(processed)
        else:
            self.current_phrase = ""

        output_text = ''
        candidates = ''
        first_chars = ''

        if split_text != "" and ' ' not in split_text:
            if "'" not in split_text:
                self.current_query_type = "single"
                candidates = query_single_char(split_text, self.current_page * 5)
                if candidates and self.auto_commit_enabled == "1" and len(processed) > 3:
                    candidates_list = candidates.split("/")
                    non_dot_candidates = []
                    for candidate in candidates_list:
                        code_part = candidate[1:] if len(candidate) > 1 else ""
                        if "." not in code_part:
                            non_dot_candidates.append(candidate)
                    if len(non_dot_candidates) == 1:
                        selected_char = non_dot_candidates[0][0]
                        self._replace_content(input_text, selected_char, do_paste=True, reset_entry=True)
                        self.reset_state()
                        return
                if candidates != '':
                    if "/" in candidates:
                        output_text = candidates.split("/")[0][0]
                    else:
                        output_text = candidates[0]
            else:
                self.current_query_type = "multi_part"
                if "'" in processed and self.phrase_priority == "1":
                    # 优先上词开启 + 用户手动输入单引号 → 词语增强预览
                    phrase_result = get_phrase_segments(processed)
                    if phrase_result:
                        display_text, all_parts = phrase_result
                        self.current_split_parts = all_parts
                        first_chars = display_text
                    else:
                        # 某段无候选 → 清空（打错）
                        self.current_split_parts = []
                        first_chars = ""
                else:
                    self.current_split_parts = split_text.split("'")
                    first_chars = query_multi_chars(split_text)
                output_text = first_chars

        # 处理空格上屏
        if " " in input_text:
            # 词语优先判断
            if self.phrase_priority == "1" and self.current_query_type == "multi_part" and self.current_phrase:
                output_text = self.current_phrase[1:-1]
            elif output_text == "":
                if self.current_phrase:
                    output_text = self.current_phrase[1:-1]
                else:
                    output_text = processed

            self._replace_content(input_text, output_text, do_paste=True, reset_entry=True)
            self.reset_state()
            return

        self.last_input_text = input_text

    def process_char(self, ch):
        if ch == '=' or ch == '-':
            if self.current_query_type == "multi_part" and self.current_split_parts:
                self.current_phrase = ""
                direction = "next" if ch == '=' else "prev"
                self._navigate_parts(direction)
            return False

        if ch in SELECTION_SYMBOLS:
            handled = self._handle_selection_keys(ch)
            return handled

        self.input_text += ch
        self._on_input_change()
        return False


def main():
    import sys

    # 交互式终端模式
    if sys.stdin.isatty():
        print("解书音形命令行模拟器")
        print("输入编码串（支持空格、!@#$%选词、=/-切换部件），按 Enter 提交")
        print("输入 'exit' 或 'quit' 退出")
        while True:
            try:
                line = input("> ")
            except EOFError:
                break
            if line.lower() in ('exit', 'quit'):
                break
            if not line.strip():
                continue
            if not line.endswith(' '):
                line += ' '
            ime = SimulatedIME()
            for ch in line:
                ime.process_char(ch)
            if ime.output_history:
                print("上屏结果:", ''.join(ime.output_history))
            else:
                print("（无上屏）")
            if ime.input_text:
                print("剩余输入:", ime.input_text)
    else:
        # 管道模式（非交互）
        for line in sys.stdin:
            line = line.rstrip('\n')
            if not line.strip():
                sys.stdout.write('\n')      # 空行对应空输出
                continue
            if not line.endswith(' '):
                line += ' '
            ime = SimulatedIME()
            for ch in line:
                ime.process_char(ch)
            if ime.output_history:
                sys.stdout.write(''.join(ime.output_history) + '\n')
            else:
                sys.stdout.write('\n')


if __name__ == "__main__":
    main()
