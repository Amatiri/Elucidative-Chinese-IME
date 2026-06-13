import os
from config import DATA_FILE


def read_dictionary(file_path=None):
    """读取词典文件，返回 {编码: 汉字} 字典"""
    if file_path is None:
        file_path = DATA_FILE
    dictionary = {}
    if not os.path.exists(file_path):
        print(f"错误：词典文件 {file_path} 不存在")
        return dictionary
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(' ', 1)
            if len(parts) < 2:
                continue
            hanzi, code = parts[0], parts[1]
            if '.' in code:
                continue
            if len(code) < 4:
                continue
            dictionary[code] = hanzi
    return dictionary


def get_abc_zone_entries(dictionary, abc_code):
    """获取指定音码区的所有条目"""
    zone_entries = {}
    for code, hanzi in dictionary.items():
        if code.startswith(abc_code):
            if len(code) > 4:
                d_code = code[3]
                e_code = code[4]
            else:
                d_code = code[3]
                e_code = 'a'
            zone_entries[hanzi] = {
                'full_code': code,
                'd_code': d_code,
                'e_code': e_code
            }
    return zone_entries


def generate_tables(zone_entries):
    """生成独体字表和合体字表"""
    one_dim_table = {}
    for i in range(10):
        one_dim_table[str(i)] = []
    d_letters = [chr(i) for i in range(ord('b'), ord('z')+1) if chr(i) != 'e']
    e_letters = [chr(i) for i in range(ord('a'), ord('z')+1)] + [';']

    two_dim_table = {}
    for d in d_letters:
        two_dim_table[d] = {}
        for e in e_letters:
            two_dim_table[d][e] = []
    for hanzi, info in zone_entries.items():
        d_code = info['d_code']
        e_code = info['e_code']
        if d_code.isdigit():
            one_dim_table[d_code].append(hanzi)
        else:
            if d_code in two_dim_table:
                if e_code in two_dim_table[d_code]:
                    two_dim_table[d_code][e_code].append(hanzi)
                else:
                    print(f"{hanzi}副码{e_code}不在有效范围内")
            else:
                print(f"{hanzi}主码{d_code}不在有效范围内")
    return one_dim_table, two_dim_table, d_letters, e_letters


def print_one_dim_table(one_dim_table, abc_code):
    print("独体字表：")
    d_codes = [str(i) for i in range(10)]
    first_row = "|" + " |".join(d_codes) + " |"
    print(first_row)
    second_row_parts = []
    for d_code in d_codes:
        hanzi_list = one_dim_table[d_code]
        if hanzi_list:
            hanzi_str = "、".join(hanzi_list)
            second_row_parts.append(f"{hanzi_str}")
        else:
            second_row_parts.append("  ")
    second_row = "|" + "|".join(second_row_parts) + "|"
    print(second_row)
    total_single = sum(len(hanzi_list) for hanzi_list in one_dim_table.values())


def print_two_dim_table(two_dim_table, d_letters, e_letters, abc_code):
    print("合体字表：")
    transposed_table = {}
    for e_letter in e_letters:
        transposed_table[e_letter] = {}
        for d_letter in d_letters:
            transposed_table[e_letter][d_letter] = two_dim_table[d_letter][e_letter]
    header = "E\\D|" + " |".join([f"{d}" for d in d_letters]) + " |"
    print(header)
    for e_letter in e_letters:
        row_parts = [f"{e_letter:}  "]
        for d_letter in d_letters:
            hanzi_list = transposed_table[e_letter][d_letter]
            if hanzi_list:
                if len(hanzi_list) > 2:
                    cell_content = "、".join(hanzi_list[:2]) + f"等{len(hanzi_list)}"
                else:
                    cell_content = "、".join(hanzi_list)
                row_parts.append(f"{cell_content}")
            else:
                row_parts.append(f"{'  '}")
        print("|".join(row_parts) + "|")
    total_combined = 0
    for d_letter in d_letters:
        for e_letter in e_letters:
            total_combined += len(two_dim_table[d_letter][e_letter])


def analyze_abc_zone(abc_code):
    """分析指定音码区"""
    dictionary = read_dictionary()
    if not dictionary:
        print("词典为空或读取失败")
        return
    zone_entries = get_abc_zone_entries(dictionary, abc_code)
    if not zone_entries:
        print(f"{abc_code}区为空")
        return
    one_dim_table, two_dim_table, d_letters, e_letters = generate_tables(zone_entries)
    print_one_dim_table(one_dim_table, abc_code)
    print_two_dim_table(two_dim_table, d_letters, e_letters, abc_code)
    print()
    print(f"{abc_code}区详细分析")
    single_count = sum(len(hanzi_list) for hanzi_list in one_dim_table.values())
    combined_count = 0
    for d_letter in d_letters:
        for e_letter in e_letters:
            combined_count += len(two_dim_table[d_letter][e_letter])
    total_count = single_count + combined_count
    if total_count > 0:
        single_ratio = single_count / total_count * 100
        print(f"独体率：{single_count}/{total_count} {single_ratio:.1f}%")
    else:
        print("独体率：0/0 0.0%")
    d_code_stats = {}
    for hanzi, info in zone_entries.items():
        d_code = info['d_code']
        d_code_stats[d_code] = d_code_stats.get(d_code, 0) + 1
    print(f"主码分布：")
    if total_count > 0:
        for d_code, count in sorted(d_code_stats.items()):
            percentage = count / total_count * 100
            print(f"  D={d_code}: {count}字 ({percentage:.1f}%)")
    used_d_codes = set(d_code_stats.keys())
    print(f"使用的主码数量：{len(used_d_codes)}")
    e_not_a_count = 0
    for hanzi, info in zone_entries.items():
        if info['e_code'] != 'a':
            e_not_a_count += 1
    if total_count > 0:
        e_rate = e_not_a_count / total_count * 100
        print(f"副码率：{e_rate:.1f}%")
    else:
        print(f"副码率：0.0%")


def interactive_mode():
    """交互式音区分析"""
    if not os.path.exists(DATA_FILE):
        print("错误：找不到 dictionary.txt 文件")
        print("请确保 dictionary.txt 文件与程序在同一目录下")
        return
    print("解书音形 - 音区分析工具")
    while True:
        user_input = input("音区: ").strip().lower()
        if user_input == '':
            break
        elif len(user_input) < 2 or not (user_input[0].isalpha() and user_input[-1].isdigit()):
            print("音码格式错误")
            continue
        analyze_abc_zone(user_input)
        print()
