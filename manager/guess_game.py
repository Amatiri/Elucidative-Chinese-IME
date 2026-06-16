import random
import os
from config import DATA_FILE

class GuessCodingGame:
    def __init__(self):
        self.all_entries = []          # 原 self.dictionary
        self.entries_with_e = []       # 原 self.e_codes_dict

    def load_dictionary(self):
        try:
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if line and ' ' in line:
                        parts = line.split(' ')
                        if len(parts) >= 2:
                            word = parts[0]
                            code = parts[1]
                            # 新增：若编码中包含 '.' 则忽略该条目
                            if '.' in code:
                                continue
                            self.all_entries.append((word, code))
                            # 只有长度>=5且第5位不是 '.' 才认为有副码
                            # 由于已过滤 '.'，code[4] 不会是 '.'，但保留原判断逻辑更安全
                            if len(code) >= 5 and code[4] != '.':
                                self.entries_with_e.append((word, code))
        except FileNotFoundError:
            return False
        except Exception:
            return False
        return True

    def get_random_word_with_d(self):
        if not self.all_entries:
            return None
        return random.choice(self.all_entries)

    def get_random_word_with_e(self):
        if not self.entries_with_e:
            return None
        return random.choice(self.entries_with_e)

    def get_d_code(self, code):
        if len(code) >= 4:
            return code[3]
        return None

    def get_e_code(self, code):
        if len(code) >= 5 and code[4] != '.':
            return code[4]
        return None

    def _ask_for_code(self, word, code, extract_func, prompt_text, success_msg_func, on_fail=None):
        target = extract_func(code)
        if target is None:
            print("该词无此编码位，跳过。")
            return True

        ABC = code[:3]
        print(f"*{word}*, 音码{ABC}")
        attempts = 0
        while True:
            user_input = input(prompt_text).strip()
            # 修改点：输入 'a' 或 空字符串 均退出
            if user_input.lower() == 'a' or user_input == '':
                return False
            if len(user_input) != 1:
                print("请输入一个字符")
                continue
            attempts += 1
            if user_input == target:
                print(success_msg_func(target, code))
                return True
            else:
                print("错误，请再试一次")
                if on_fail:
                    on_fail(attempts, target, self.get_d_code(code) if hasattr(self, 'get_d_code') else None)

    def guess_d_mode(self):
        print("猜主码")
        while True:
            item = self.get_random_word_with_d()
            if not item:
                print("无数据，返回菜单")
                return
            word, code = item
            result = self._ask_for_code(
                word, code,
                extract_func=self.get_d_code,
                prompt_text="猜主码: ",
                success_msg_func=lambda t, c: f"正确！主码是{t}，完整编码{c}",
                on_fail=None   # 猜主码时无额外提示
            )
            if not result:   # 用户按了 a
                return

    def guess_e_mode(self):
        print("猜副码")
        while True:
            item = self.get_random_word_with_e()
            if not item:
                print("无副码数据，返回菜单")
                return
            word, code = item
            # 定义猜错时的回调：第二次错时提示主码
            def on_e_fail(attempts, e_code, d_code):
                if attempts > 1 and d_code:
                    print(f"提示主码：{d_code}")

            result = self._ask_for_code(
                word, code,
                extract_func=self.get_e_code,
                prompt_text="猜副码: ",
                success_msg_func=lambda t, c: f"正确！副码是{t}，完整编码{c}",
                on_fail=on_e_fail
            )
            if not result:
                return

    def show_menu(self):
        print("解书音形 - 猜编码小游戏")
        print("D - 猜主码(形部)")
        print("E - 猜副码")

    def run(self):
        if not self.load_dictionary():
            return
        while True:
            self.show_menu()
            choice = input("选择: ").strip().upper()
            if choice == '':
                break
            elif choice == 'D':
                self.guess_d_mode()
            elif choice == 'E':
                if not self.entries_with_e:
                    print("当前没有含副码的词条，请先检查数据文件。")
                    continue
                self.guess_e_mode()
            else:
                print("请重新输入")

# 入口函数保持不变，但函数名 bmmamain 建议保留（尽管可能是笔误）
def bmmamain():
    game = GuessCodingGame()
    if not os.path.exists(DATA_FILE):
        print("未找到 dictionary.txt 文件")
    game.run()
