import re
from config import DATA_FILE, CIYU_FILE, DATA_NO_NUMBER_FILE


def char_priority(c):
    if c in '123456789.':
        return (0, c)
    elif c in '0abcdefghijklmnopqrstuvwxyz':
        return (1, c)
    elif c == ';':
        return (2, ';')
    else:
        return (3, c)


def sort_key(non_han_str):
    return tuple(char_priority(c) for c in non_han_str)


def get_abc_code(full_code):
    if len(full_code) < 3:
        return full_code
    return full_code[:3]


first_level_map = {
    '不': 'bu44', '从': 'cs2r', '的': 'de0b', '发': 'fa1k', '个': 'ge41',
    '好': 'hk3n', '成': 'ig2g', '就': 'jq4d', '可': 'ke3k', '了': 'le01',
    '们': 'mf0r', '你': 'ni3r', '哦': 'oo4k', '平': 'p;25', '去': 'qu4t',
    '人': 'rf22', '所': 'so3j', '他': 'ta1r', '是': 'ui4r', '这': 've4z',
    '我': 'wo3g', '小': 'xc33', '有': 'yb3r', '在': 'zl4t'
}


def process_file(input_file, output_file):
    """处理词典文件：去重、排序、首字置顶"""
    seen_entries = set()
    entries = []
    global first_level_map
    entries_by_first_char = {}

    # ---------- 原有：按行去重 ----------
    with open(input_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.rstrip()
            if not line:
                continue
            parts = line.split(' ', 1)
            if len(parts) < 2:
                continue
            hanzi, non_han = parts
            non_han_clean = non_han.rstrip()
            if len(non_han_clean) <= 3:
                continue
            entry_key = f"{hanzi} {non_han_clean}"
            if entry_key not in seen_entries:
                seen_entries.add(entry_key)
                entries.append((hanzi, non_han_clean))

    # ---------- 原有：按完整编码去重 ----------
    seen_codes = set()
    code_unique_entries = []
    for hanzi, code in entries:
        if code not in seen_codes:
            seen_codes.add(code)
            code_unique_entries.append((hanzi, code))

    # ========== 过滤：同一汉字同一音区只保留一次（异体字补码例外） ==========
    # 无补码(不含'.')的条目：用 (前三码, 汉字) 作为唯一键
    # 有补码(含'.')的条目：用 (汉字, 点前编码) 作为唯一键
    #   同一汉字指向不同源字的补码（点前编码不同）可共存（如 齐 ji1z.q vs 齐 ji1wj.q）
    #   同一汉字指向同源字的补码（点前编码相同）只保留第一个（如 齐 ji1z.q vs 齐 ji1z.w）
    seen_prefix_hanzi = set()
    filtered_entries = []
    for hanzi, code in code_unique_entries:
        if '.' in code:
            pre_dot = code.split('.')[0]
            key = (hanzi, pre_dot)
        else:
            prefix = get_abc_code(code)
            key = (prefix, hanzi)
        if key not in seen_prefix_hanzi:
            seen_prefix_hanzi.add(key)
            filtered_entries.append((hanzi, code))
    # 用过滤后的列表替代原列表，后续流程不变
    code_unique_entries = filtered_entries
    # =================================================================

    # ---------- 原有：按编码首字母分组 ----------
    for hanzi, code in code_unique_entries:
        if code and code[0].isalpha():
            first_char = code[0]
            if first_char not in entries_by_first_char:
                entries_by_first_char[first_char] = []
            entries_by_first_char[first_char].append((hanzi, code))

    # ---------- 原有：组内首字置顶与排序 ----------
    for first_char, entry_list in entries_by_first_char.items():
        first_level_hanzi = None
        for hanzi, target_code in first_level_map.items():
            if target_code[0] == first_char:
                first_level_hanzi = hanzi
                target_first_level_code = target_code
                break
        if first_level_hanzi:
            for i, (hanzi, code) in enumerate(entry_list):
                if hanzi == first_level_hanzi and code == target_first_level_code:
                    entry_list.insert(0, entry_list.pop(i))
                    break
        if len(entry_list) > 1:
            tail_entries = entry_list[1:]
            tail_entries.sort(key=lambda x: sort_key(x[1]))
            entry_list[1:] = tail_entries

    # ---------- 原有：按首字母顺序输出 ----------
    all_entries = []
    for first_char in sorted(entries_by_first_char.keys()):
        all_entries.extend(entries_by_first_char[first_char])

    with open(output_file, 'w', encoding='utf-8') as f:
        for hanzi, non_han in all_entries:
            f.write(f"{hanzi} {non_han}\n")

    return len(all_entries)


def sort_file_by_second_part(input_file, output_file):
    """按第二部分排序并去重，合并同词条目"""
    try:
        with open(input_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        # ---------- 初级去重：完全相同的行只保留一次 ----------
        seen_lines = set()
        parsed_entries = []
        for line in lines:
            if not line.strip():
                continue
            parts = line.split(' ', 1)
            if len(parts) < 2:
                continue
            first_part, second_part = parts
            second_part = second_part.rstrip()
            line_key = f"{first_part} {second_part}"
            if line_key not in seen_lines:
                seen_lines.add(line_key)
                parsed_entries.append((first_part, second_part))

        # ---------- 中级压缩：合并同词多条目的编码 ----------
        # 将同一词语的所有编码收集到一行，用空格分隔
        word_codes = {}  # word -> list of unique codes (preserving first-seen order)
        for word, code_str in parsed_entries:
            if word not in word_codes:
                word_codes[word] = []
            for code in code_str.split():
                if code not in word_codes[word]:
                    word_codes[word].append(code)

        # 重建为单行条目
        merged_entries = []
        for word, codes in word_codes.items():
            merged_code_str = ' '.join(codes)
            merged_entries.append((word, merged_code_str))

        # ---------- 清理：剔除单字编码（len<=1视为不合理） ----------
        # 若某条目所有编码均被剔除，则整个条目删除
        cleaned_entries = []
        for word, code_str in merged_entries:
            codes = code_str.split()
            filtered_codes = [c for c in codes if len(c) > 1]
            if filtered_codes:
                cleaned_entries.append((word, ' '.join(filtered_codes)))
        merged_entries = cleaned_entries

        # ---------- 排序 ----------
        merged_entries.sort(key=lambda x: x[1])

        # ---------- 终级去重：删除已在前面条目中出现过的编码 ----------
        seen_codes = set()                # 全局已出现编码
        unique_entries = []
        for word, code_str in merged_entries:
            codes = code_str.split()
            # 仅保留之前从未出现过的编码
            new_codes = [c for c in codes if c not in seen_codes]
            if new_codes:                 # 至少保留了一个编码
                seen_codes.update(new_codes)
                unique_entries.append((word, ' '.join(new_codes)))

        # ---------- 写入 ----------
        with open(output_file, 'w', encoding='utf-8') as f:
            for word, code_str in unique_entries:
                f.write(f"{word} {code_str}\n")

        return len(unique_entries)
    except FileNotFoundError:
        print(f"错误: 找不到输入文件 '{input_file}'")
    except Exception as e:
        print(f"错误: {e}")
    return None


def merge_files_to_ahk(dictionary_file, ciyu_file, output_file):
    """合并词典和词库生成AHK热键文件"""
    result_dict = {}
    try:
        with open(dictionary_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith(';'):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    value = parts[0]
                    key = parts[1]
                    result_dict[key] = value
                else:
                    print(f"警告: {dictionary_file} 第{line_num}行格式不正确: {line}")
    except FileNotFoundError:
        print(f"错误: 找不到文件 {dictionary_file}")
        return
    try:
        with open(ciyu_file, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line or line.startswith(';'):
                    continue
                parts = line.split()
                if len(parts) >= 2:
                    value = parts[0]
                    key = parts[1]
                    result_dict[key] = value
                else:
                    print(f"警告: {ciyu_file} 第{line_num}行格式不正确: {line}")
    except FileNotFoundError:
        print(f"错误: 找不到文件 {ciyu_file}")
        return
    try:
        with open(output_file, 'w', encoding='utf-8') as f:
            for zi, ma in first_level_map.items():
                f.write(f':o:{ma[0]} ::{zi}"\n')
            for key, value in result_dict.items():
                f.write(f':o:{key} ::{value}\n')
            print(f"成功生成AHK文件: {output_file}")
            print(f"共生成 {len(result_dict)} 个热键")
    except IOError as e:
        print(f"错误: 无法写入文件 {output_file}: {e}")


def process_second_part(text):
    """处理编码第二部分，转换为简化格式"""
    if '.' in text:
        text = text.split('.')[0]
    if len(text) < 2:
        return text.lower()
    daydue = ["pqwertyuio", "masdfghjkl", "zxcvbncvbn"]
    chars = list(text)
    if len(chars) >= 2 and chars[1] == ';':
        mapping = {
            'b': 'd', 'd': 'd', 'j': 'a', 'l': 'v', 'm': 'v',
            'n': 'v', 'p': 'd', 'q': 'a', 't': 'd', 'x': 'a', 'y': 'd'
        }
        first_char = chars[0].lower()
        chars[1] = mapping.get(first_char, 'a')
    while len(chars) < 4:
        chars.append('a')
    if chars[3].isdigit():
        tone = chars[2]
        d_digit = chars[3]
        third_char = 'a' if tone in ['1', '2'] else 'e'
        if tone == '0':
            row = 2
        elif tone in ['1', '3']:
            row = 0
        else:
            row = 1
        if d_digit.isdigit() and 0 <= int(d_digit) <= 9:
            fourth_char = daydue[row][int(d_digit)]
        else:
            fourth_char = 'a'
        result = chars[0] + chars[1] + third_char + fourth_char
    else:
        d_letter = chars[3]
        has_e_code = len(chars) >= 5 and (chars[4].isalpha() or chars[4] == ";")
        if has_e_code:
            e_code = chars[4]
            if e_code == ';':
                e_code = 'e'
            fourth_char = e_code
        else:
            tone = chars[2]
            fourth_char = 'a' if tone in ['1', '2'] else 'e'
        result = chars[0] + chars[1] + d_letter + fourth_char
    result = re.sub(r'[^a-z]', '', result)
    return result[:4]


def process_filey(input_file, output_file):
    """处理词典文件生成简化编码版本"""
    try:
        with open(input_file, 'r', encoding='utf-8') as infile:
            lines = infile.readlines()
        with open(output_file, 'w', encoding='utf-8') as outfile:
            for line in lines:
                line = line.strip()
                if not line:
                    outfile.write('\n')
                    continue
                parts = line.split(' ', 1)
                if len(parts) == 2:
                    first_part = parts[0]
                    second_part = parts[1]
                    processed_second = process_second_part(second_part)
                    if processed_second:
                        outfile.write(f"{first_part} {processed_second}\n")
                else:
                    outfile.write(f"{line}\n")
            for zi, ma in first_level_map.items():
                outfile.write(f'{zi} {ma[0]}\n')
    except FileNotFoundError:
        print(f"错误：找不到文件 {input_file}")
    except Exception as e:
        print(f"处理文件时发生错误: {e}")


def main_menu():
    """整理码表主入口"""
    single_count = process_file(DATA_FILE, DATA_FILE)
    phrase_count = sort_file_by_second_part(CIYU_FILE, CIYU_FILE)
    process_filey(DATA_FILE, DATA_NO_NUMBER_FILE)
    return single_count, phrase_count


if __name__ == "__main__":
    single, phrase = main_menu()
    print(f"整理完成！码表条目：{single}+{phrase} ")
    input()
