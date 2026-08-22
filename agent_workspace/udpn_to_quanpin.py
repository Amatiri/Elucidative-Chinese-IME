import sys

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


def convert_batch(text):
    """批量转换：支持空格分隔，或无空格时自动按两位拆分（最后补'a'）。"""
    text = text.strip()
    if not text:
        return ""
    if ' ' in text:
        tokens = text.split()
    else:
        # 无空格：长度 > 2 时自动切分，最后不足两位补 'a'
        if len(text) > 2:
            tokens = [text[i:i+2] for i in range(0, len(text), 2)]
            if len(tokens[-1]) == 1:
                tokens[-1] += 'a'
        else:
            tokens = [text]

    return " ".join(convert(t) for t in tokens)


def main():
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) > 1:
        user_input = " ".join(sys.argv[1:])
        print(convert_batch(user_input))
    else:
        print("双拼→全拼")
        while True:
            user_input = input("双拼:")
            if user_input == "":
                break
            result = convert_batch(user_input)
            print(f"全拼:{result}")


if __name__ == "__main__":
    main()
