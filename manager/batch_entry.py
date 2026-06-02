import os
from config import DATA_FILE
from manager.pinyin_converter import hanzi_to_abc
from manager.dictionary import load_dictionary
from manager.file_processor import process_file


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
