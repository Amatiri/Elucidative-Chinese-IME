# -*- coding: utf-8 -*-
"""
解书拆分 → IDS 序列转换器
将解书拆分序列（支持部首双码、扩展字根、整字编码、部首变体注释）转换为 IDS 序列，并打开字统网。
"""
import sys
import urllib.parse
import webbrowser
import argparse
import re

# ============================================================
# 数据常量（硬编码，来源：radical_table.md / rules.md / dictionary.txt）
# ============================================================

# 部首变体映射（注释语法）
# 单变体用 (b)；多变体用复合注释如 (bl)/(bt)，区分字母由人工敲定。
# 不在映射表中的变体注释（如 dk(b)）不会匹配，自然报错。
RADICAL_VARIANT_MAP = {
    "ub(b)": "扌",   # 手 → 扌（提手旁）
    "dk(bl)": "刂",  # 刀 → 刂（立刀旁，l=立）
    "dk(bt)": "⺈",  # 刀 → ⺈（刀字头，t=头）
    "uv(b)": "氵",   # 水 → 氵（三点水）
    "ho(b)": "灬",   # 火 → 灬（四点底）
    "rf(b)": "亻",   # 人 → 亻（单人旁）
    "bs(b)": "⺊",
    "bi(b)": "𠤎",
    "cg(b)": "廾",
    "hd(b)": "龸",
    "hl(b)": "虎",
    "if(b)": "𦣞",
    "jr(b)": "钅",
    "lk(b)": "耂",
    "pj(f)": "爿",
    "qr(b)": "犭",
    "q;(b)": "龶",
    "rf(bt)": "𠂉", # 人 → 𠂉（人字头，t=头）
    "rb(b)": "⺼",  # 肉月旁
    "ri(b)": "冃",
    "si(b)": "纟",
    "si(bt)": "糸", # 丝 → 糸（t=幺(部首码)）
    "si(f)": "糹",
    "uw(bs)": "夊", # 攵 → 夊（s取音sv1）
    "uw(bv)": "夂", # 攵 → 夂（折文，v=折）
    "uv(bd)": "氺", # 水 → 氺（水字底，d=底）
    "ur(b)": "饣",
    "vi(b)": "疋", 
    "vi(bp)": "𤴔", # 止 → 𤴔（疋字旁，p=旁）
    "vi(bd)": "龰", # 止 → 龰（龰字底，d=底）
    "vw(b)": "爫",
    "wx(b)": "罒",
    "xn(b)": "忄",
    "xn(bd)": "㣺", # 心 → 㣺（心字底，d=底）
    "xi(by)": "襾", # 西 → 襾（y取音ya4）
    "xi(b)": "覀",
    "yj(b)": "讠",
    "yi(b)": "衤",
    "yi(d)": "𧘇",
    "yl(b)": "肀",
    "zr(b)": "𥫗",
    "zu(b)": "𧾷",
    "su(b)": "礻",
    "au(b)": "亅",
    "ob(b)": "匸",
    "gx(b)": "𭠍",
    "xp(b)": "巜",
    "ih24(b)": "镸", #“长”变体
    "gs4b(u)": "龷", #“共”上半
    "di(b)": "𠂔",
    "an(b)": "㇏", #捺
    "xl(x)": "⿱丿囗", #“囟”外框
}

RADICAL_DUAL_MAP = {
    "ad": "丶",
    "ah": "一",
    "au": "丨",
    "ap": "丿",
    "ay": "乙",
    "ag": "乛",
    "ak": "𠃌",
    "aw": "乚",
    "av": "𡿨",
    "at": "㇀", #提
    "an": "乀", #提捺
    "bk": "宀",
    "bu": "阝",
    "b;": "冫",
    "bz": "贝",
    "bg": "疒",
    "bl": "白",
    "bs": "卜",
    "ba": "八",
    "bi": "匕",
    "bo": "癶",
    "ce": "车",
    "ck": "艹",
    "ch": "厂",
    "cy": "凵",
    "cp": "寸",
    "cg": "卄",
    "ci": "屮",
    "dk": "刀",
    "dl": "歹",
    "da": "大",
    "dh": "亠",
    "dp": "冖",
    "dm": "丷",
    "db": "斗",
    "du": "豆",
    "fg": "风",
    "fh": "方",
    "fu": "父",
    "fb": "缶",
    "fq": "臼",
    "fi": "辰",
    "fz": "非",
    "gs": "工",
    "gd": "广",
    "gv": "弓",
    "gm": "光",
    "go": "囗",
    "ge": "革",
    "gx": "戈",
    "gw": "瓜",
    "gf": "艮",
    "gb": "谷",
    "gr": "骨",
    "ho": "火",
    "hu": "户",
    "he": "禾",
    "hd": "⺌",
    "hy": "羊",
    "hl": "虍",
    "hz": "黑",
    "is": "虫",
    "ie": "页",
    "iu": "雨",
    "ix": "弋",
    "io": "彐",
    "ih": "彑",
    "if": "臣",
    "it": "赤",
    "ip": "𡗗",
    "ii": "尺",
    "jr": "金",
    "jn": "巾",
    "jz": "廴",
    "jt": "冂",
    "ji": "几",
    "jf": "𠘨",
    "js": "卩",
    "jw": "己",
    "jm": "见",
    "jp": "斤",
    "jd": "皀",
    "kb": "口",
    "ky": "又",
    "ku": "舌",
    "ks": "用",
    "kj": "角",
    "lb": "娄",
    "ly": "云",
    "lp": "勹",
    "li": "力",
    "ls": "龙",
    "lk": "老",
    "lu": "卤",
    "lt": "里",
    "lr": "卵",
    "mu": "木",
    "ms": "彡",
    "mb": "釆",
    "ma": "马",
    "mf": "门",
    "mn": "皿",
    "mk": "毛",
    "mo": "目",
    "my": "矛",
    "mi": "米",
    "ml": "麦",
    "ny": "女",
    "nq": "牛",
    "nc": "鸟",
    "nl": "耒",
    "ni": "齿",
    "or": "耳",
    "ob": "匚",
    "oh": "二",
    "op": "儿",
    "oe": "㔾",
    "pu": "攴",
    "pm": "片",
    "py": "殳",
    "pj": "丬",
    "pi": "皮",
    "pb": "髟",
    "pn": "㐅",
    "qi": "气",
    "qr": "犬",
    "qv": "豸",
    "qm": "欠",
    "q;": "青",
    "rf": "人",
    "rb": "肉",
    "ru": "入",
    "ri": "日",
    "rl": "リ",
    "su": "示",
    "si": "丝",
    "sk": "石",
    "sp": "尸",
    "sj": "十",
    "sm": "厶",
    "sw": "巳",
    "tu": "土",
    "ti": "彳",
    "ty": "幺",
    "tx": "夕",
    "tm": "田",
    "uw": "攵",
    "uv": "水",
    "ui": "矢",
    "ub": "手",
    "ur": "食",
    "uj": "山",
    "uh": "士",
    "un": "豕",
    "uf": "身",
    "vs": "乑",
    "vg": "争",
    "vb": "舟",
    "vi": "止",
    "vw": "爪",
    "vm": "鬼",
    "vk": "支",
    "wh": "王",
    "wx": "网",
    "wa": "瓦",
    "wz": "韦",
    "wv": "隹",
    "wf": "文",
    "xt": "穴",
    "xd": "𰃮",
    "xn": "心",
    "xi": "西",
    "xc": "小",
    "xp": "巛",
    "xm": "血",
    "xs": "辛",
    "xb": "习",
    "yj": "言",
    "yb": "酉",
    "yt": "月",
    "yu": "鱼",
    "yi": "衣",
    "yh": "尢",
    "yl": "聿",
    "ye": "业",
    "yx": "羽",
    "yk": "黾",
    "yn": "音",
    "zv": "辶",
    "zr": "竹",
    "zu": "足",
    "zi": "子",
    "zp": "自",
    "zb": "走",
}

EXTENDED_ROOT_MAP = {
    "bh": "㡀",
    "bj": "𠬝",
    "bp": "卑",
    "bt": "鼻",
    "cj": "册",
    "cn": "𢆉",
    "di": "𢎨",
    "dr": "⿷⿻𠂆一二", #“段”左半
    "d;": "鼎",
    "fd": "负",
    "gc": "𢦏",
    "hb": "丌",
    "hh": "𰀁",
    "ib": "⿲𠄌⺀⿲𠄌⺀㇂", #“鼠”下半
    "ir": "㐄",
    "jc": "龹",
    "jg": "𠀎",
    "jj": "巿",
    "jk": "叚",
    "jq": "介",
    "ju": "丩",
    "ko": "コ",
    "kv": "亏",
    "ld": "立",
    "lg": "鹿",
    "ll": "𠂢",
    "md": "龴",
    "mg": "麻",
    "mh": "母",
    "mt": "买",
    "mz": "𠃜",
    "na": "𠂇",
    "nd": "犮",
    "nt": "𰀂",
    "nu": "在",
    "oj": "卬",
    "ok": "𫠤",
    "qc": "乔",
    "qw": "齐",
    "sb": "𰀉",
    "sd": "𣶒",
    "se": "𢀖",
    "ts": "𭕄",
    "ud": "冘",
    "vc": "𠂋",
    "vp": "𠂤",
    "wd": "亡",
    "wm": "毋",
    "wu": "戊",
    "xl": "囟",
    "xu": "卂",
    "yw": "𠃓",
}

# 整字词典（运行时从 dictionary.txt 加载）
import os as _os

_code_to_char_cache = None
_DICT_PATH = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "..", "dictionary.txt")
def _load_code_to_char():
    """延迟加载 dictionary.txt，返回 {编码: 汉字} 映射。"""
    global _code_to_char_cache
    if _code_to_char_cache is not None:
        return _code_to_char_cache
    mapping = {}
    try:
        with open(_DICT_PATH, encoding="utf-8") as f:
            for ln in f:
                ln = ln.rstrip("\r\n")
                if not ln.strip():
                    continue
                parts = ln.split()
                if len(parts) >= 2:
                    mapping[parts[1]] = parts[0]
    except FileNotFoundError:
        import sys as _sys
        _sys.stderr.write(f"警告: 词典文件不存在: {_DICT_PATH}\n")
    _code_to_char_cache = mapping
    return mapping


# ============================================================
# 合并两码表（部首双码 ∪ 扩展字根，已确认互斥）
# ============================================================
TWO_CHAR_MAP = {}
TWO_CHAR_MAP.update(RADICAL_DUAL_MAP)
TWO_CHAR_MAP.update(EXTENDED_ROOT_MAP)


# ============================================================
# 结构算子映射
# ============================================================
OPERATOR_MAP = {
    "r.": "⿰",   # 左右
    "rr.": "⿲",  # 左中右
    "i.": "⿱",   # 上下
    "ii.": "⿳",  # 上中下
    "x.": "⿻",   # 交错
}

# 包围结构方向映射（l. 的第三个参数）
DIRECTION_MAP = {
    "1": "⿹",  # 右上包围
    "2": "⿽",  # 右下包围
    "3": "⿺",  # 左下包围
    "4": "⿸",  # 左上包围
    "u": "⿵",  # 上三包围
    "x": "⿶",  # 下三包围
    "z": "⿷",  # 左三包围
    "y": "⿼",  # 右三包围
    "w": "⿴",  # 全包围
}


def _resolve_variant(token: str) -> str | None:
    """尝试解析变体注释 token，如 'ub(b)'、'dk(bl)' 等。
    若 token 存在于 RADICAL_VARIANT_MAP 中则返回对应字形，否则返回 None。
    """
    return RADICAL_VARIANT_MAP.get(token)


def resolve_leaf(token: str) -> str:
    """叶子 token 分类与查表，返回部件字形。失败则抛出 ValueError。"""
    # 0. 变体注释优先：如 ub(b)、dk(bl)、dk(bt)
    variant = _resolve_variant(token)
    if variant is not None:
        return variant

    # 1. 两码表查表（部首双码或扩展字根）
    if token in TWO_CHAR_MAP:
        return TWO_CHAR_MAP[token]

    # 2. 长度 1：视为汉字，原样保留
    if len(token) == 1:
        return token

    # 3. 长度 2 但不在两码表：报错
    if len(token) == 2:
        raise ValueError(
            f"编码「{token}」不存在：长度为 2 的编码应在部首双码或扩展字根中，但未找到匹配项"
        )

    # 4. 长度 > 2：查整字词典
    code_to_char = _load_code_to_char()
    if token in code_to_char:
        return code_to_char[token]

    raise ValueError(
        f"编码「{token}」不存在：在整字词典中未找到匹配项"
    )


def parse(tokens: list[str], index: int) -> tuple[str, int]:
    """递归解析 token 流，返回 (IDS 片段, 下一个 token 位置)"""
    if index >= len(tokens):
        return "", index

    token = tokens[index]

    # 包围结构 l. 需要特殊处理——它有第三个参数（方向）
    if token == "l.":
        index += 1
        part1, index = parse(tokens, index)
        part2, index = parse(tokens, index)
        if index >= len(tokens):
            raise ValueError("l. 缺少方向参数（如 1/2/3/4/u/x/z/y/w）")
        direction = tokens[index]
        index += 1
        if direction not in DIRECTION_MAP:
            raise ValueError(f"未知的包围方向: {direction}")
        ids = DIRECTION_MAP[direction]
        return ids + part1 + part2, index

    # 左中右结构，3 个部件
    if token == "rr.":
        index += 1
        part1, index = parse(tokens, index)
        part2, index = parse(tokens, index)
        part3, index = parse(tokens, index)
        return "⿲" + part1 + part2 + part3, index

    # 上中下结构，3 个部件
    if token == "ii.":
        index += 1
        part1, index = parse(tokens, index)
        part2, index = parse(tokens, index)
        part3, index = parse(tokens, index)
        return "⿳" + part1 + part2 + part3, index

    # 普通二元结构（r./i./x.）
    if token in OPERATOR_MAP:
        ids_op = OPERATOR_MAP[token]
        index += 1
        part1, index = parse(tokens, index)
        part2, index = parse(tokens, index)
        return ids_op + part1 + part2, index

    # 叶子节点：经分类器查表
    return resolve_leaf(token), index + 1


def convert(input_str: str) -> str:
    """将解书拆分序列转换为 IDS 序列。失败时返回空字符串并打印错误。"""
    tokens = input_str.strip().split()
    if not tokens:
        return ""

    try:
        ids, remaining = parse(tokens, 0)
    except ValueError as e:
        print(f"错误：{e}")
        return ""

    if remaining < len(tokens):
        leftover = " ".join(tokens[remaining:])
        print(f"警告：以下 token 未被消费: {leftover}")
    return ids


def open_zi_tools(ids: str) -> None:
    """用默认浏览器打开字统网对应页面"""
    encoded = urllib.parse.quote(ids, safe="")
    url = f"https://zi.tools/?secondary=ids&seq={encoded}"
    print(f"IDS 序列: {ids}")
    print(f"打开网址: {url}")
    webbrowser.open(url)


def main():
    parser = argparse.ArgumentParser(
        description="解书拆分 → IDS 序列转换器（默认不打开网页）"
    )
    parser.add_argument(
        "sequence", nargs="?",
        help="解书拆分序列（空格分隔的 token，如有空格请用引号括起）"
    )
    parser.add_argument(
        "--open", "-o", action="store_true",
        help="转换后自动打开字统网"
    )
    args = parser.parse_args()

    if args.sequence:
        ids = convert(args.sequence)
        if ids:
            if args.open:
                open_zi_tools(ids)
            else:
                # 不打开，只显示信息
                encoded = urllib.parse.quote(ids, safe="")
                url = f"https://zi.tools/?secondary=ids&seq={encoded}"
                print(f"IDS 序列: {ids}")
                print(f"字统网链接: {url}")
                print("（未自动打开，如需打开请使用 --open 选项）")
    else:
        # 交互模式：默认不打开网页
        while True:
            input_str = input("输入解书拆分序列：")
            if not input_str:
                break
            ids = convert(input_str)
            if ids:
                encoded = urllib.parse.quote(ids, safe="")
                url = f"https://zi.tools/?secondary=ids&seq={encoded}"
                print(f"IDS 序列: {ids}")
                print(f"字统网链接: {url}")
                # 不自动打开

if __name__ == "__main__":
    main()
