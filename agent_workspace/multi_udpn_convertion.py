# -*- coding: utf-8 -*-
"""
双拼转换工具
  搜狗双拼 → 全拼 → 小鹤双拼
"""

import re
import sys

# ============================================================
# 一、小鹤双拼：全拼 → 双拼（原 xiaohe.py）
# ============================================================

# 小鹤双拼韵母 → 键位映射
# 注意：多韵母共用一键时，此处直接登记，后续按精确匹配处理
_YUNMU_MAP = {
    "iu": "q",
    "ei": "w",
    "uan": "r", "van": "r",
    "ve": "t", 
    "un": "y", "vn":"y",
    "uo": "o",
    "ie": "p",
    "ong": "s", "iong": "s",
    "ing": "k", "uai": "k",
    "ai": "d",
    "en": "f",
    "eng": "g",
    "iang": "l", "uang": "l",
    "ang": "h",
    "ian": "m",
    "an": "j",
    "ou": "z",
    "ua": "x", "ia": "x",
    "iao": "n",
    "ao": "c",
    "ui": "v",
    "in": "b",
}
# 小鹤双拼零声母不规则鼻音特殊编码
_SPECIAL_NASAL = {
    "n": "on",
    "m": "om",
    "ng": "og",
}

# 按指定规则做等价全拼后再转换
_SPECIAL_AS_NORMAL = {
    "hng": "heng",
    "hm": "hen",
}
# 声母映射：全拼 → 小鹤
_SHENGMU_MAP = {
    "zh": "v",
    "ch": "i",
    "sh": "u",
}

# 单韵母（保持原样）
_DANYUNMU = set("aoeiuü")

# 零声母双字母韵母中，双拼形式与全拼一致的集合
_ZERO_DOUBLE_AS_IS = {"ai", "ei", "ao", "ou", "an", "en", "er"}


def _split_sheng_yun(pinyin: str):
    """将全拼音节拆分为 (声母, 韵母)。声母可能为空。"""
    for slen in (2, 1):
        if len(pinyin) >= slen:
            candidate = pinyin[:slen]
            if candidate in ("zh", "ch", "sh") and slen == 2:
                return candidate, pinyin[slen:]
            if candidate in "bpmfdtnlgkhjqxrzcsyw" and slen == 1:
                return candidate, pinyin[slen:]
    return "", pinyin  # 零声母


def _normalize_v(pinyin: str) -> str:
    """将 j/q/x/y 后的 u 规范为 v（代表 ü），便于统一映射。"""
    if len(pinyin) >= 2 and pinyin[0] in "jqxy" and pinyin[1] == "u":
        return pinyin[0] + "v" + pinyin[2:]
    return pinyin


def full2flypy(pinyin: str) -> str:
    """
    将全拼音节转换为小鹤双拼。
    非拼音字符或无法识别时原样返回。
    """
    pinyin = pinyin.strip().lower()
    if not pinyin:
        return ""

    raw = re.sub(r"[^a-zü]", "", pinyin)
    if not raw:
        return pinyin

    # 规范 ü 的写法
    raw = raw.replace("ü", "v")  # 统一用 v 代表 ü，与映射表一致
    raw = _normalize_v(raw)
    # 不规则鼻音特殊处理
    if raw in _SPECIAL_NASAL:
        return _SPECIAL_NASAL[raw]

    # hng 视为 heng，hm 视为 hen 后再走正常转换
    raw = _SPECIAL_AS_NORMAL.get(raw, raw)
    sheng, yun = _split_sheng_yun(raw)

    # ---------- 零声母分支 ----------
    if sheng == "":
        if len(yun) == 1:
            return yun + yun          # 单字母韵母：双写
        if yun in _ZERO_DOUBLE_AS_IS:
            return yun                # 双字母韵母，形式同全拼
        if yun in _YUNMU_MAP:
            return yun[0] + _YUNMU_MAP[yun]   # 三字母及以上
        return yun                    # 兜底

    # ---------- 有声母分支 ----------
    sheng_key = _SHENGMU_MAP.get(sheng, sheng)

    if yun in _DANYUNMU:
        yun_key = yun
    elif yun in _YUNMU_MAP:
        yun_key = _YUNMU_MAP[yun]
    else:
        yun_key = yun                 # 未在映射表中的韵母，原样拼接

    return sheng_key + yun_key


# ============================================================
# 二、搜狗双拼：双拼 → 全拼（原 udpn_to_quanpin.py）
# ============================================================

# ---- 纠错表：错误双拼 → 正确全拼（可多个，用"/"分隔）----
CORRECTION = {
    "yy": "yu",
    "jy": "ju",
    "qy": "qu",
    "xy": "xu",
    "oc": "yao",
    "od": "yang/wang",
    "oi": "yi",
    "om": "yan",
    "op": "wen/yun",
    "oq": "you",
    "ot": "yue",
    "ou": "wu",
    "ov": "wei",
    "ow": "ya/wa",
    "ox": "ye",
    "oy": "yu/wai",
}

# ---- 特殊语气词音节: 双拼码 → 全拼（优先应用）----
SPECIAL = {
    "hn": "hng",
    "hm": "hm",
    "nv": "ng",
    "mv": "m",
    "on": "n",
}

# ---- 声母键 → 声母 ----
# ch→i, sh→u, zh→v, 零声母→o, 其余（含形式声母 y/w）同字母
INITIAL_MAP = {"i": "ch", "u": "sh", "v": "zh", "o": ""}

# ---- 韵母键 → 韵母候选（顺序即默认优先级）----
FINAL_MAP = {
    "q": ["iu"],
    "w": ["ia", "ua"],
    "e": ["e"],
    "r": ["uan", "er"],
    "t": ["üe", "ue"],
    "y": ["uai", "ü"],
    "u": ["u"],
    "i": ["i"],
    "o": ["uo", "o"],
    "p": ["un", "ün"],
    "a": ["a"],
    "s": ["ong", "iong"],
    "d": ["iang", "uang"],
    "f": ["en"],
    "g": ["eng"],
    "h": ["ang"],
    "j": ["an"],
    "k": ["ao"],
    "l": ["ai"],
    "z": ["ei"],
    "x": ["ie"],
    "c": ["iao"],
    "v": ["ui"],
    "b": ["ou"],
    "n": ["in"],
    "m": ["ian"],
    ";": ["ing"],
}

# ---- 歧义拼音定向表（无声调）, 用于多韵母候选的存在性判断 ----
VALID = set("""
mua fua gua kua hua zhua chua shua rua zua cua sua er
yue jue que xue nü lü bo po mo fo wo o jiong qiong xiong
fuang duang guang kuang huang zhuang chuang shuang zuang cuang suang ruang
""".split())


def spell(initial, final):
    """声母+韵母 → 全拼拼写。j/q/x/y 后的 ü 按规范改写为 u。"""
    if initial in "jqxy":
        final = final.replace("ü", "u")
    return initial + final


def convert(token):
    """双拼（两位）→ 全拼; 无法解析时原样返回。"""
    t = token.strip().lower()
    if t in CORRECTION:
        return CORRECTION[t] + "(纠)"
    if t in SPECIAL:
        return SPECIAL[t]
    if len(t) != 2 or t[1] not in FINAL_MAP:
        return token
    initial = INITIAL_MAP.get(t[0], t[0])
    candidates = [spell(initial, f) for f in FINAL_MAP[t[1]]]
    for c in candidates:
        if c in VALID:
            return c
    return candidates[0]


def split_tokens(text):
    """把用户输入拆成若干双拼音节：
       有空格按空格分；无空格时按两位切分（末位不足补 'a'）。"""
    text = text.strip()
    if not text:
        return []
    if " " in text:
        return text.split()
    if len(text) > 2:
        tokens = [text[i:i + 2] for i in range(0, len(text), 2)]
        if len(tokens[-1]) == 1:
            tokens[-1] += "a"
        return tokens
    return [text]


def convert_batch(text):
    """搜狗双拼整串 → 全拼列表（每个元素对应一个音节）。"""
    return [convert(t) for t in split_tokens(text)]


# ============================================================
# 三、全拼 → 小鹤双拼（批量，处理纠错标记与多候选）
# ============================================================

def quanpin_to_flypy(qp: str) -> str:
    """把一段全拼（可能带 '(纠)' 标记、可能用 '/' 分隔多候选）转成小鹤双拼。"""
    if not qp:
        return ""
    clean = qp.replace("(纠)", "")
    return "/".join(full2flypy(p) for p in clean.split("/"))


# ============================================================
# 四、主流程
# ============================================================

MENU = {
    "1": "搜狗双拼 → 全拼 → 小鹤双拼",
}


def choose_option():
    """显示菜单并返回用户选择；返回 None 表示用户取消。"""
    print("可用转换选项：")
    for key, desc in MENU.items():
        print(f"  {key}. {desc}")
    while True:
        choice = input("请选择转换选项（回车退出）：").strip()
        if choice == "":
            return None
        if choice in MENU:
            return choice
        print("无效选项，请重新输入。")


def main():
    try:
        sys.stdin.reconfigure(encoding="utf-8")
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

    option = choose_option()
    if option is None:
        print("已退出。")
        return

    print(f"\n当前模式：{MENU[option]}")
    print("输入搜狗双拼（可用空格分隔，也可连续输入自动两位切分；直接回车退出）\n")

    while True:
        user_input = input("搜狗双拼：").strip()
        if user_input == "":
            break

        quanpin_list = convert_batch(user_input)
        flypy_list = [quanpin_to_flypy(q) for q in quanpin_list]

        print(f"全拼：{' '.join(quanpin_list)}")
        print(f"小鹤双拼：{' '.join(flypy_list)}")
        print()

    print("已退出。")


if __name__ == "__main__":
    main()
