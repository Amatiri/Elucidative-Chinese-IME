import os
from config import DATA_FILE
from manager.dictionary import load_dictionary
from manager.file_processor import process_file
import re
from pypinyin import pinyin, Style

import re
from pypinyin import pinyin, Style

final_dict = {
    "q": ["iu"], "w": ["ia", "ua"], "e": ["e"], "r": ["uan", "er"],
    "t": ["ve", "ue"], "y": ["uai", "v"], "u": ["u"], "i": ["i"],
    "o": ["o", "uo"], "p": ["un", "vn"], "a": ["a"], "s": ["ong", "iong"],
    "d": ["iang", "uang"], "f": ["en"], "g": ["eng"], "h": ["ang"],
    "j": ["an"], "k": ["ao"], "l": ["ai"], "z": ["ei"], "x": ["ie"],
    "c": ["iao"], "v": ["ui"], "b": ["ou"], "n": ["in"], "m": ["ian"],
    ";": ["ing"]
}

special_cases = {
    "hng": "hn",
    "hm": "hm",
    "ng": "nv",
    "m": "mv",
    "n": "on"
}


def get_initial(pinyin_str):
    pinyin_clean = re.sub(r'\d', '', pinyin_str)
    if not pinyin_clean:
        return 'o'
    if pinyin_clean[0] in 'jqxyw':
        return pinyin_clean[0]
    if pinyin_clean.startswith('ch'):
        return 'i'
    if pinyin_clean.startswith('sh'):
        return 'u'
    if pinyin_clean.startswith('zh'):
        return 'v'
    if pinyin_clean[0] in 'aeiou':
        return 'o'
    if pinyin_clean[0] in 'bpmfdtnlgkhzcsr':
        return pinyin_clean[0]
    return 'o'


def get_final(pinyin_str):
    pinyin_str = pinyin_str.replace('\u00fc', 'v')
    pinyin_clean = re.sub(r'\d', '', pinyin_str)
    initial = get_initial(pinyin_str)
    if initial in 'jqxyw':
        pinyin_clean = pinyin_clean.replace('v', 'u')
    if initial == 'o':
        remaining = pinyin_clean
    elif initial in 'jqxyw':
        remaining = pinyin_clean[1:] if len(pinyin_clean) > 1 else ""
    else:
        if pinyin_clean.startswith('ch'):
            remaining = pinyin_clean[2:] if len(pinyin_clean) > 2 else ""
        elif pinyin_clean.startswith('sh'):
            remaining = pinyin_clean[2:] if len(pinyin_clean) > 2 else ""
        elif pinyin_clean.startswith('zh'):
            remaining = pinyin_clean[2:] if len(pinyin_clean) > 2 else ""
        else:
            remaining = pinyin_clean[1:] if len(pinyin_clean) > 1 else ""

    if not remaining and initial == 'o':
        remaining = 'a'

    matched_final = ""
    result = ""
    final_items = sorted(final_dict.items(), key=lambda x: max(len(p) for p in x[1]), reverse=True)
    for final_code, patterns in final_items:
        for pattern in patterns:
            if remaining == pattern or remaining.startswith(pattern):
                if len(pattern) > len(matched_final):
                    matched_final, result = pattern, final_code

    return result if matched_final else ""


def get_tone(pinyin_str):
    tone_match = re.search(r'\d', pinyin_str)
    if tone_match:
        tone_num = int(tone_match.group())
        return '0' if tone_num == 5 else str(tone_num)
    return '0'


def hanzi_to_abc(hanzi):
    pinyin_list = pinyin(hanzi, style=Style.TONE3, heteronym=True)
    abc_codes = []

    for pinyin_variants in pinyin_list:
        for py in pinyin_variants:
            if not py:
                continue

            py_with_tone = py
            if py.endswith('5'):
                py_with_tone = py[:-1] + '0'

            # 去掉声调数字，得到纯拼音，例如 ng4 -> ng
            base = re.sub(r'\d', '', py_with_tone)

            if base in special_cases:
                mapped = special_cases[base]   # 例如 "nv"
                a_code = mapped[0]
                b_code = mapped[1]
                c_code = get_tone(py_with_tone)
            else:
                a_code = get_initial(py_with_tone)
                b_code = get_final(py_with_tone)
                c_code = get_tone(py_with_tone)

            if a_code and b_code and c_code:
                abc_code = f"{a_code}{b_code}{c_code}"
                if abc_code not in abc_codes:
                    abc_codes.append(abc_code)

    return abc_codes if abc_codes else []


def generate_pending_list(hanzi_string):
    """生成待录入列表，拼音转换失败时提示手动输入音码"""
    existing_dict, full_dict = load_dictionary()
    pending_list = []
    for hanzi in hanzi_string:
        abc_codes = hanzi_to_abc(hanzi)
        if not abc_codes:
            manual_code = input(f"{hanzi} 音码转换失败，请手动输入，回车则bb0: ").strip()
            if manual_code:
                if len(manual_code) == 3 and not manual_code[0].isdigit() and not manual_code[1].isdigit() and manual_code[2].isdigit():
                    abc_codes = [manual_code]
                else:
                    print(f"{manual_code}格式错误，使用bb0")
                    abc_codes = ['bb0']
            else:
                abc_codes = ['bb0']
        missing_codes = []
        all_exist = True
        for abc_code in abc_codes:
            if (hanzi, abc_code) not in existing_dict:
                missing_codes.append(abc_code)
                all_exist = False
        if all_exist:
            pending_list.append((hanzi, ''))
        else:
            for abc_code in missing_codes:
                pending_list.append((hanzi, abc_code))
    return pending_list, len(pending_list), full_dict


def handle_conflict(han_zi, abc_code, check_list, full_code, modified_entries):
    """重码递归处理"""
    conflict_found = False
    conflict_hanzi = ""
    conflict_full_code = ""
    for entry in check_list:
        if entry[1] == full_code and entry[0] != han_zi:
            conflict_found = True
            conflict_hanzi = entry[0]
            conflict_full_code = entry[1]
            break
    if not conflict_found:
        return full_code, modified_entries
    print(f"{han_zi}与{conflict_hanzi}重码")
    new_conflict_full_code = abc_code + input(f"{conflict_hanzi}{abc_code} 形码改: ")
    new_check_list = [entry for entry in check_list if not (entry[0] == conflict_hanzi and entry[1] == conflict_full_code)]
    new_conflict_in_list = any(entry[1] == new_conflict_full_code for entry in new_check_list)
    if new_conflict_in_list:
        new_conflict_full_code, modified_entries = handle_conflict(
            conflict_hanzi, abc_code, new_check_list, new_conflict_full_code, modified_entries
        )
    modified_entries.append((conflict_hanzi, new_conflict_full_code))
    new_full_code = abc_code + input(f"{han_zi}{abc_code} 形码改: ")
    final_check_list = [entry for entry in new_check_list]
    final_check_list.append((conflict_hanzi, new_conflict_full_code))
    new_in_list = any(entry[1] == new_full_code for entry in final_check_list)
    if new_in_list:
        new_full_code, modified_entries = handle_conflict(
            han_zi, abc_code, final_check_list, new_full_code, modified_entries
        )
    abc_to_entries = {}
    for entry in modified_entries:
        key = (entry[0], entry[1][:3])
        abc_to_entries[key] = entry
    cleaned_modified_entries = list(abc_to_entries.values())
    return new_full_code, cleaned_modified_entries


def batch_add_entries():
    """批量录入汉字编码"""
    while True:
        user_input = input("连续汉字: ").strip()
        if not user_input:
            return
        all_non_chinese = True
        chinese_input = ''
        for char in user_input:
            if '\u3400' <= char <= '\u9fff' or 0x20000 <= ord(char) <= 0x33479 or '\uf900' <= char <= '\ufad9':
                chinese_input += char
                all_non_chinese = False
        if all_non_chinese:
            print("全非中文,请重新输入:")
            continue
        break
    pending_list, count, full_dict = generate_pending_list(chinese_input)
    new_entries = []
    modified_entries = []
    hanzi_abc_map = {}
    for hanzi, abc_code in pending_list:
        if abc_code:
            if hanzi not in hanzi_abc_map:
                hanzi_abc_map[hanzi] = []
            if abc_code not in hanzi_abc_map[hanzi]:
                hanzi_abc_map[hanzi].append(abc_code)
    i = 0
    while i < count:
        hanzi, abc_code = pending_list[i]
        if abc_code:
            current_abc_list = hanzi_abc_map[hanzi]
            index = current_abc_list.index(abc_code)
            if abc_code == current_abc_list[0]:
                print(f"========{hanzi}========")
            position = f"{index + 1}/{len(current_abc_list)}"
            print(f"{position}", end="")
            existing_entries = []
            if abc_code in full_dict:
                for entry in full_dict[abc_code]:
                    existing_entries.append(entry)
            if existing_entries:
                print("存在")
                for entry_hanzi, entry_code in existing_entries:
                    print(f"***{entry_hanzi} {entry_code}***")
            else:
                print("暂无")
            d_code_input = input(f"{hanzi}{abc_code} 形码: ")
            if d_code_input == "a":
                i += 1
                new_entries.append((hanzi, abc_code))
                print(f"跳过{abc_code}")
                continue
            elif d_code_input == "e":
                i -= 1
                if i == -1:
                    return
                else:
                    hanzi, abc_code = pending_list[i]
                    print(f"返回{hanzi}{abc_code}")
                    continue
            full_code = abc_code + d_code_input
            check_list = []
            for entry in new_entries:
                if entry[1][:3] == abc_code:
                    check_list.append(entry)
            for entry in modified_entries:
                if entry[1][:3] == abc_code:
                    check_list.append(entry)
            for entry_hanzi, entry_code in existing_entries:
                modified = False
                for mod_entry in modified_entries:
                    if mod_entry[0] == entry_hanzi and mod_entry[1][:3] == abc_code:
                        modified = True
                        break
                if not modified:
                    check_list.append((entry_hanzi, entry_code))
            is_conflict = any(entry[1] == full_code and entry[0] != hanzi for entry in check_list)
            if is_conflict:
                full_code, modified_entries = handle_conflict(
                    hanzi, abc_code, check_list, full_code, modified_entries
                )
            print(hanzi, full_code)
            new_entries.append((hanzi, full_code))
        else:
            print(f"========{hanzi}========")
            print(f"{hanzi} 已编码完毕")
        i += 1
    abc_to_entries_dict = {}
    for entry in new_entries:
        abc_part = entry[1][:3] if len(entry[1]) >= 3 else entry[1]
        key = (entry[0], abc_part)
        abc_to_entries_dict[key] = entry
    new_entries = list(abc_to_entries_dict.values())
    original_entries = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line:
                    parts = line.split(' ', 1)
                    if len(parts) == 2:
                        original_entries.append((parts[0], parts[1]))
    modified_map = {}
    for hanzi, full_code in modified_entries:
        abc_prefix = full_code[:3]
        modified_map[(hanzi, abc_prefix)] = full_code
    final_entries = []
    for hanzi, full_code in original_entries:
        abc_prefix = full_code[:3] if len(full_code) >= 3 else full_code
        key = (hanzi, abc_prefix)
        if key not in modified_map:
            final_entries.append((hanzi, full_code))
    for key, full_code in modified_map.items():
        hanzi = key[0]
        final_entries.append((hanzi, full_code))
    for hanzi, full_code in new_entries:
        final_entries.append((hanzi, full_code))
    temp_file = os.path.join(os.path.dirname(DATA_FILE), "dictionary_temp.txt")
    with open(temp_file, 'w', encoding='utf-8') as f:
        for hanzi, full_code in final_entries:
            f.write(f"{hanzi} {full_code}\n")
    try:
        single_count = process_file(temp_file, DATA_FILE)
        print(f"完成！汉字条目：{single_count}")
        os.remove(temp_file)
    except ImportError:
        import subprocess
        subprocess.run(["python", "vgli.py"])
        if os.path.exists(temp_file):
            os.remove(temp_file)
