import os
from config import CIYU_FILE
from manager.code_parser import parse_code, generate_all_combinations, generate_default_codes_for_word
from manager.dictionary import query_chars


def process_two_char_word(word):
    """处理双字词语的编码生成"""
    code_str, missing = query_chars(word)
    if missing:
        print(f"未录入：{''.join(missing)}")
    codes_per_char = code_str.split()
    for i, codes in enumerate(codes_per_char):
        if codes == "--":
            return None
    code1 = codes_per_char[0].split('/')
    code2 = codes_per_char[1].split('/')
    print(f"{word[0]}{codes_per_char[0]}")
    print(f"{word[1]}{codes_per_char[1]}")
    
    # 处理第一个字的读音选择
    if len(code1) > 1:
        while True:
            choice = input(f"{word[0]} 读音选: ").strip()
            if not choice.isdigit():
                print("请输入数字")
                continue
            choice_num = int(choice)
            if 1 <= choice_num <= len(code1):
                code1xr = code1[choice_num - 1]
                break
            else:
                print(f"请输入1到{len(code1)}之间的数字")
    else:
        code1xr = code1[0]
    
    # 处理第二个字的读音选择
    if len(code2) > 1:
        while True:
            choice = input(f"{word[1]} 读音选: ").strip()
            if not choice.isdigit():
                print("请输入数字")
                continue
            choice_num = int(choice)
            if 1 <= choice_num <= len(code2):
                code2xr = code2[choice_num - 1]
                break
            else:
                print(f"请输入1到{len(code2)}之间的数字")
    else:
        code2xr = code2[0]
    
    all_combinations = generate_all_combinations(code1xr, code2xr)
    if not all_combinations:
        print("无法生成任何编码组合")
        return None
    for i, combo in enumerate(all_combinations, 1):
        print(f"{i:2d}.{combo}")
    while True:
        try:
            choice = input("编码选：")
            if choice == "":
                return None
            start_index = int(choice)
            if 1 <= start_index <= len(all_combinations):
                selected_combinations = [all_combinations[start_index-1]]
                return selected_combinations
            else:
                print(f"请输入1到{len(all_combinations)}之间的数字")
        except ValueError:
            print("请输入有效的数字")


def process_multi_char_word(word):
    """处理多字词语的编码生成"""
    code_str, missing = query_chars(word)
    if missing:
        print(f"未录入：{''.join(missing)}")
    codes_per_char = code_str.split()
    for i, codes in enumerate(codes_per_char):
        if codes == "--":
            return None
    selected_codes = []
    for i, char in enumerate(word):
        codes = codes_per_char[i].split('/')
        print(f"{char}{codes_per_char[i]}")
        if len(codes) > 1:
            while True:
                choice = input(f"{char} 读音选: ").strip()
                if not choice.isdigit():
                    print("请输入数字")
                    continue
                choice_num = int(choice)
                if 1 <= choice_num <= len(codes):
                    selected_codes.append(codes[choice_num - 1])
                    break
                else:
                    print(f"请输入1到{len(codes)}之间的数字")
        else:
            selected_codes.append(codes[0])
    default_code = generate_default_codes_for_word(word, selected_codes)
    print(f"默认：{default_code}")
    choice = input("输入1添加默认编码，或直接输入自定义编码：").strip()
    if choice == "1":
        selected_codes_list = [default_code]
    else:
        if choice == "":
            print("未输入编码，放弃添加")
            return None
        selected_codes_list = choice.split()
    return selected_codes_list


def add_to_ciyu(word, codes, overwrite=False):
    """添加词语到 ciyu.txt"""
    if not word or not codes:
        return False
    lines = []
    if os.path.exists(CIYU_FILE):
        with open(CIYU_FILE, 'r', encoding="utf-8") as f:
            lines = f.readlines()
    new_lines = [line for line in lines if not line.startswith(word + " ")]
    existing = (len(new_lines) != len(lines))
    if existing and not overwrite:
        print(f"词语 '{word}' 已存在，原有编码将被保留。若要覆盖，请使用覆盖模式。")
        return False
    entry = word + " " + " ".join(codes) + "\n"
    new_lines.append(entry)
    with open(CIYU_FILE, 'w', encoding="utf-8") as f:
        f.writelines(new_lines)
    if existing:
        print(f"已覆盖原编码")
    return True


def ciyumain():
    """词语添加主入口"""
    if not os.path.exists(CIYU_FILE):
        with open(CIYU_FILE, 'w', encoding='utf-8') as f:
            pass
    while True:
        line = input("连续词语：").strip()
        if not line:
            break
        words = line.split()
        for word in words:
            print(f"========{word}========")
            if len(word) == 2:
                codes = process_two_char_word(word)
            elif len(word) == 1:
                general_symbol = input("识别为通用符号，请输入自定义编码：").strip()
                codes = general_symbol.split()
            else:
                codes = process_multi_char_word(word)
            if not word or not codes:
                print(f"跳过 {word}")
                continue
            print(f"{word}{' '.join(codes)}")
            add_to_ciyu(word, codes, overwrite=True)
