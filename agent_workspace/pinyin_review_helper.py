# -*- coding: utf-8 -*-
"""
音码审查辅助脚本
================
给定若干 (字, 音码) 对，输出判定所需的全部原始证据：

1. 该音码能解码成哪些拼音音节（音码 == 初码+韵码+调码）
2. 该字在 char_with_pinyin.txt 里登记的读音（参考表）
3. 该字在 dictionary.txt 里登记的全部音码（码表）
4. pypinyin 给出的全部异读（TONE3）
5. 该字各读音在 dictionary.txt 中是否存在（含形码）

用法：
  python pinyin_review_helper.py 虾:ha2 吽:hb3 ...
  或直接编辑 PAIRS
"""

import io
import os
import re
import sys
from collections import defaultdict

if hasattr(sys.stdout, "buffer"):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, PROJECT_ROOT)

from manager.batch_entry import get_initial, get_final, get_tone, special_cases  # noqa: E402
from pypinyin import pinyin, Style  # noqa: E402
from pypinyin.pinyin_dict import pinyin_dict  # noqa: E402


# ---------------------------------------------------------------------------
# 声调符号 → 数字（pypinyin 0.55 的 pinyin_dict 值是带调符号形式）
# ---------------------------------------------------------------------------
TONE_MARKS = {
    "ā": "a1", "á": "a2", "ǎ": "a3", "à": "a4",
    "ē": "e1", "é": "e2", "ě": "e3", "è": "e4",
    "ī": "i1", "í": "i2", "ǐ": "i3", "ì": "i4",
    "ō": "o1", "ó": "o2", "ǒ": "o3", "ò": "o4",
    "ū": "u1", "ú": "u2", "ǔ": "u3", "ù": "u4",
    "ǖ": "v1", "ǘ": "v2", "ǚ": "v3", "ǜ": "v4",
    # 部分数据里出现的 ü 上标组合
    "ń": "n2", "ň": "n3", "ǹ": "n4",
    "ḿ": "m2", "m̀": "m4",
}


def mark_to_tone3(py):
    """带调符号拼音 → 数字调拼音（bā→ba1，lǜ→lv4）。无声调符号则视为轻声5。"""
    out, tone = [], None
    for ch in py:
        if ch in TONE_MARKS:
            out.append(TONE_MARKS[ch][0])
            tone = TONE_MARKS[ch][1]
        else:
            out.append(ch)
    return "".join(out) + (tone or "5")


# ---------------------------------------------------------------------------
# 1) 用 pypinyin 的全音节表建立 「音码 -> 候选音节」 反查
# ---------------------------------------------------------------------------
def build_syllable_index():
    bases = set()
    for _cp, val in pinyin_dict.items():
        for s in val.split(","):
            s = s.strip()
            if not s:
                continue
            bases.add(re.sub(r"\d", "", mark_to_tone3(s)))
    # 语气词整读音
    bases.update(["n", "ng", "m", "hm", "hng"])
    idx = defaultdict(set)
    for b in bases:
        a, bf = get_initial(b), get_final(b)
        if not a or not bf:
            continue
        for tone in "01234":
            idx[f"{a}{bf}{tone}"].add(b)
    return idx


SYLL_INDEX = build_syllable_index()


def decode_code(code):
    """音码 -> [(基础音节, 声调), ...]"""
    if code in ("bb0",):
        return [("(无拼音)", "0")]
    a, b, t = code[0], code[1], code[2]
    syls = SYLL_INDEX.get(code, set())
    return sorted((s, t) for s in syls)


# ---------------------------------------------------------------------------
# 2) 载入两张表
# ---------------------------------------------------------------------------
CHAR_PINYIN_FILE = os.path.join(PROJECT_ROOT, "dict", "char_with_pinyin.txt")
DICTIONARY_FILE = os.path.join(PROJECT_ROOT, "dict", "dictionary.txt")


def load_cwp():
    t = defaultdict(set)
    with open(CHAR_PINYIN_FILE, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            p = re.split(r"\s+", line, maxsplit=1)
            if len(p) == 2:
                t[p[0]].add(p[1])
    return t


def load_dict_entries():
    t = defaultdict(list)
    with open(DICTIONARY_FILE, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line:
                continue
            p = re.split(r"\s+", line, maxsplit=1)
            if len(p) == 2:
                t[p[0]].append(p[1])
    return t


TONE_MARKS_OLD = None  # 已上移


def abc_of(py_tone3):
    base = re.sub(r"\d", "", py_tone3)
    if base in special_cases:
        m = special_cases[base]
        return m + get_tone(py_tone3)
    a, b, c = get_initial(py_tone3), get_final(py_tone3), get_tone(py_tone3)
    return (a + b + c) if a and b and c else "?"


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
SUMMARY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pinyin_audit_summary.txt")


def load_pairs_from_summary(limit=20):
    """从 pinyin_audit_summary.txt 读取 (字, 音码) 对，取前 limit 个字。

    文件格式： 音码 : 汉字1 汉字2 ...
    例：      li4 : 仂 叻 珞
    """
    pairs = []
    with open(SUMMARY_FILE, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or ":" not in line:
                continue
            code, _, chars = line.partition(":")
            code = code.strip()
            for ch in chars.split():
                pairs.append((ch, code))
                if len(pairs) >= limit:
                    return pairs
    return pairs


def main():
    if len(sys.argv) > 1:
        pairs = []
        for a in sys.argv[1:]:
            ch, _, code = a.partition(":")
            pairs.append((ch, code))
    else:
        pairs = load_pairs_from_summary(20)

    cwp = load_cwp()
    dic = load_dict_entries()

    print("=" * 78)
    for ch, code in pairs:
        print(f"\n【{ch} / {code}】")
        cands = decode_code(code)
        print(f"  音码 {code} 可解码为： " +
              "、".join(f"{s}{t}" for s, t in cands) if cands else f"  音码 {code} 无可解码音节")

        cwp_py = sorted(cwp.get(ch, []))
        cwp_abc = sorted(set(abc_of(mark_to_tone3(p)) for p in cwp_py))
        print(f"  参考表 char_with_pinyin： {' '.join(cwp_py) if cwp_py else '(无此字)'}"
              f"   → 音码 {cwp_abc}")

        print(f"  码表 dictionary 全部条目： {dic.get(ch, ['(无此字)'])}")

        py_list = pinyin(ch, style=Style.TONE3, heteronym=True)
        flat = py_list[0] if py_list else []
        print(f"  pypinyin 异读： {' '.join(flat)}   → 音码 "
              f"{sorted(set(abc_of(x) for x in flat))}")

        # 该音码对应的音节是否被 pypinyin 认可为该字读音
        hits = [x for x in flat if abc_of(x) == code]
        print(f"  → 码表此条 {code} 对应读音 "
              f"{'、'.join(hits) if hits else '**不在 pypinyin 读音列表中**'}")
    print("\n" + "=" * 78)


if __name__ == "__main__":
    main()
