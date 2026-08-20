import re
import os
import json
from datetime import datetime
from config import DATA_FILE, CIYU_FILE, DATA_NO_NUMBER_FILE, BASE_DIR


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
    with open(input_file, 'r', encoding='utf-8-sig') as f:
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
    seen_codes = set()
    code_unique_entries = []
    for hanzi, code in entries:
        if code not in seen_codes:
            seen_codes.add(code)
            code_unique_entries.append((hanzi, code))
            
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
    code_unique_entries = filtered_entries

    for hanzi, code in code_unique_entries:
        if code and code[0].isalpha():
            first_char = code[0]
            if first_char not in entries_by_first_char:
                entries_by_first_char[first_char] = []
            entries_by_first_char[first_char].append((hanzi, code))

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
        with open(input_file, 'r', encoding='utf-8-sig') as f:
            lines = f.readlines()

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

        word_codes = {}  
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

        cleaned_entries = []
        for word, code_str in merged_entries:
            codes = code_str.split()
            filtered_codes = [c for c in codes if len(c) > 1]
            if filtered_codes:
                cleaned_entries.append((word, ' '.join(filtered_codes)))
        merged_entries = cleaned_entries

        merged_entries.sort(key=lambda x: x[1])

        seen_codes = set()               
        unique_entries = []
        for word, code_str in merged_entries:
            codes = code_str.split()
            new_codes = [c for c in codes if c not in seen_codes]
            if new_codes:                
                seen_codes.update(new_codes)
                unique_entries.append((word, ' '.join(new_codes)))

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
        with open(dictionary_file, 'r', encoding='utf-8-sig') as f:
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
        with open(ciyu_file, 'r', encoding='utf-8-sig') as f:
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
        with open(input_file, 'r', encoding='utf-8-sig') as infile:
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


def _read_existing_rationale(output_path):
    """读取已有 dictionary-data.js 中的 rationale 对象，保留已填充的理据。"""
    try:
        with open(output_path, "r", encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        return {}

    match = re.search(r'rationale:\s*(\{)', content)
    if not match:
        return {}

    start = match.start(1)
    depth = 0
    end = start
    for i in range(start, len(content)):
        if content[i] == '{':
            depth += 1
        elif content[i] == '}':
            depth -= 1
            if depth == 0:
                end = i + 1
                break

    try:
        return json.loads(content[start:end])
    except json.JSONDecodeError:
        return {}


def _format_json_lines(obj, per_line=20):
    """
    将 dict/list 序列化为每行最多 per_line 个条目的 JSON 字符串。
    适用于字典的键值对或列表的元素分行显示。
    """
    if isinstance(obj, dict):
        entries = []
        for k, v in obj.items():
            k_json = json.dumps(k, ensure_ascii=False, separators=(',', ':'))
            v_json = json.dumps(v, ensure_ascii=False, separators=(',', ':'))
            entries.append(f"{k_json}:{v_json}")
        open_ch, close_ch = "{", "}"
    elif isinstance(obj, list):
        entries = [
            json.dumps(item, ensure_ascii=False, separators=(',', ':'))
            for item in obj
        ]
        open_ch, close_ch = "[", "]"
    else:
        return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))

    if not entries:
        return open_ch + close_ch

    lines = []
    for i in range(0, len(entries), per_line):
        lines.append("    " + ",".join(entries[i:i + per_line]))

    return (
        open_ch + "\n"
        + ",\n".join(lines)
        + "\n  " + close_ch
    )


def build_web_data():
    """生成网页查询用的 JS 数据文件"""
    help_dir = os.path.join(BASE_DIR, "help/webpage")
    output_path = os.path.join(help_dir, "dictionary-data.js")

    # 汉字码表 → charMap
    entry_count = 0
    char_map = {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = re.split(r"\s+", line, maxsplit=1)
            if len(parts) == 2:
                char, code = parts[0], parts[1]
                char_map.setdefault(char, []).append(code)
                entry_count += 1

    # 词语码表 → phraseMap
    phrase_map = {}
    with open(CIYU_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = re.split(r"\s+", line, maxsplit=1)
            if len(parts) == 2:
                phrase, codes_str = parts[0], parts[1]
                codes = codes_str.split()
                phrase_map[phrase] = codes

    # 保留已有 rationale，不覆盖手工填充的内容
    existing_rationale = _read_existing_rationale(output_path)

    # 按 chars 顺序重排 rationale
    sorted_rationale = {}
    for ch in char_map:
        if ch in existing_rationale:
            sorted_rationale[ch] = existing_rationale[ch]
    for ch, val in existing_rationale.items():
        if ch not in sorted_rationale:
            sorted_rationale[ch] = val
    existing_rationale = sorted_rationale

    # 写出 JS（每行最多 20 个条目）
    js = (
        "// 解书音形 · 码表数据 — 由 manager.file_processor 自动生成，勿手动编辑\n"
        f"// 生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"// 汉字条目：{entry_count} | 去重后字符：{len(char_map)} | 词语：{len(phrase_map)}\n"
        "window.jieshuDict = {\n"
        f"  entryCount: {entry_count},\n"
        f"  phraseCount: {len(phrase_map)},\n"
        f"  chars: {_format_json_lines(char_map, 20)},\n"
        f"  phrases: {_format_json_lines(phrase_map, 20)},\n"
        f"  rationale: {_format_json_lines(existing_rationale, 20)}\n"
        "};\n"
    )
    os.makedirs(help_dir, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(js)
    return entry_count, len(phrase_map)


def main_menu():
    """整理码表主入口"""
    single_count = process_file(DATA_FILE, DATA_FILE)
    phrase_count = sort_file_by_second_part(CIYU_FILE, CIYU_FILE)
    process_filey(DATA_FILE, DATA_NO_NUMBER_FILE)
    web_chars, web_phrases = build_web_data()
    return single_count, phrase_count, web_chars, web_phrases


if __name__ == "__main__":
    single, phrase = main_menu()
    print(f"整理完成！码表条目：{single}+{phrase} ")
    input()
