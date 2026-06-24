"""前端查询模块 - 输入法 ime.py 使用的查询与编码处理函数"""
import os
from config import DATA_FILE, CIYU_FILE, CODE_CHARS
from manager.dictionary import ensure_data_file


def query_phrase(code):
    """从词库文件 ciyu.txt 中查询短语"""
    try:
        with open(CIYU_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                parts = line.strip().split(" ")
                if len(parts) >= 2 and code in parts[1:]:
                    return "(" + parts[0] + ")"
    except FileNotFoundError:
        pass
    return ""


def get_entry_count():
    """返回词典文件中的词条总数"""
    ensure_data_file()
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            return len(f.readlines())
    return 0


def query_by_prefix(prefix, start_idx=0, count=5):
    """根据编码前缀查询候选词。支持副码a和补码规则"""
    ensure_data_file()
    if not os.path.exists(DATA_FILE) or os.path.getsize(DATA_FILE) == 0:
        return []
    results = []
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split(' ', 1)
            if len(parts) == 2:
                word = parts[0]
                code = parts[1]
                # 处理特殊规则：前缀长度>=5且副码为a
                if len(prefix) >= 5 and prefix[4] == 'a':
                    if len(prefix) == 5 and code == prefix[:4]:
                        results.append(f"{word}")
                    elif len(code) >= 5 and code.startswith(prefix[:4]):
                        if code[4:].startswith(prefix[5:]) and code[4] == ".":
                            rest = code[len(prefix)-1:]
                            results.append(f"{word}{rest}")
                elif code.startswith(prefix):
                    # 处理补码
                    if "." in code[:6]:
                        if '.' in prefix:
                            rest = code[len(prefix):]
                            results.append(f"{word}{rest}")
                        elif (len(code) > 5 and "." == code[5]) or (len(prefix) == 4 and prefix[3].isdigit()):
                            code_before_dot = code.split('.')[0]
                            if prefix == code_before_dot:
                                rest = code[len(prefix):]
                                results.append(f"{word}{rest}")
                    else:
                        rest = code[len(prefix):]
                        results.append(f"{word}{rest}")
    return results[start_idx:start_idx + count]


def process_input(input_text):
    """从输入文本中提取连续的合法编码字符（CODE_CHARS）"""
    result = ""
    start_collecting = False
    for char in input_text:
        if not start_collecting and 'a' <= char <= 'z':
            start_collecting = True
        if start_collecting and char in CODE_CHARS:
            result += char
    return result


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
                    if part[index+1] != "." and not part[index+1].isdigit():
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
        if not code:
            return ""
        candidates = query_by_prefix(code)
        if candidates:
            first_char = candidates[0][0]
            first_chars += first_char
        else:
            return ""
    return first_chars


def query_multi_chars_phrase(processed):
    """
    用户手动用单引号分隔的多段输入，优先查询词语码表。

    流程：
      1. 按用户手动输入的 ' 分隔 processed（注意：processed 中的 ' 都是用户打的，
         自动拆分的 ' 只出现在 split_sequence 输出里）
      2. 对每段：
         - 长度 < 3 → 自动拆分后取首选字
         - 长度 >= 3 → 先 query_phrase，命中则用词语文字；
           未命中则自动拆分取首选字
      3. 任一段无候选（含 query_phrase 未命中且首选字也为空）→ 返回 ""

    Args:
        processed: process_input() 的输出，即用户输入的合法编码字符（可含 '）

    Returns:
        拼接后的预览串，或 "" (表示某段无法解析)
    """
    segments = processed.split("'")
    result = ''
    for seg in segments:
        if not seg:
            return ""
        if len(seg) < 3:
            # 短段不走词语查询，直接自动拆分取首选字
            split_seg = split_sequence(seg)
            chars = query_multi_chars(split_seg)
            if chars:
                result += chars
            else:
                return ""
        else:
            # 先查词语
            phrase = query_phrase(seg)
            if phrase:
                # 命中词语，去掉括号直接取词语文字
                result += phrase[1:-1]
            else:
                # 未命中，降级到自动拆分取首选字
                split_seg = split_sequence(seg)
                chars = query_multi_chars(split_seg)
                if chars:
                    result += chars
                else:
                    return ""
    return result


def get_phrase_segments(processed):
    """
    将用户手动 ' 分隔的各段解析为 (display_text, split_parts_list) 的列表。
    display_text 为预览显示用的文字（词语或首选字组合），split_parts_list
    为每段经自动拆分后的部件列表（供逐字选择）。

    某段无候选则返回 None。
    """
    segments = processed.split("'")
    parts_list = []
    display_parts = []
    for seg in segments:
        if not seg:
            return None
        if len(seg) < 3:
            split_seg = split_sequence(seg)
            chars = query_multi_chars(split_seg)
            if chars:
                display_parts.append(chars)
                parts_list.append(split_seg.split("'"))
            else:
                return None
        else:
            phrase = query_phrase(seg)
            if phrase:
                display_parts.append(phrase[1:-1])
                # 词语命中时仍需自动拆分供逐字选择
                split_seg = split_sequence(seg)
                parts_list.append(split_seg.split("'"))
            else:
                split_seg = split_sequence(seg)
                chars = query_multi_chars(split_seg)
                if chars:
                    display_parts.append(chars)
                    parts_list.append(split_seg.split("'"))
                else:
                    return None
    # 展平所有部件的 split_parts
    all_parts = []
    for part_group in parts_list:
        all_parts.extend(part_group)
    return (''.join(display_parts), all_parts)
