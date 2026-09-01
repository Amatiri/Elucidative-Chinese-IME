# -*- coding: utf-8 -*-
"""
拼音审查脚本（修订版）
================
按用户要求严格比较 char_with_pinyin.txt 与 dictionary.txt，不引入 pypinyin。

流程：
1. 取 char_with_pinyin.txt 与 dictionary.txt 的汉字交集（按字形）
2. 仅使用 manager/batch_entry.py 里的 字符串规则函数
   (get_initial / get_final / get_tone / special_cases)，
   把 char_with_pinyin.txt 中每个汉字的全拼带调转换为三位音码集合。
3. 相比 dictionary.txt 中实际录入的音码（前 3 位），
   - 缺少的：char_with_pinyin 期望有、dictionary 未录
   - 多出的：dictionary 录了、char_with_pinyin 没给出（且不属于 special_cases）
"""

import os
import sys
import re
import io as _io
from collections import defaultdict

# PowerShell 默认 GBK 控制台，强制 UTF-8 输出
if hasattr(sys.stdout, "buffer"):
    sys.stdout = _io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "buffer"):
    sys.stderr = _io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
sys.path.insert(0, PROJECT_ROOT)

from manager.batch_entry import (  # noqa: E402
    get_initial, get_final, get_tone, special_cases,
)

# 审查脚本专用的特殊读音扩展（不动 batch_entry.py，避免影响批量录入流程）：
#   呒 ḿ  → mv2
#   呣 ḿ  → mv2
#   呣 m̀  → mv4
#   嗯 ńg → nv2
#   嗯 ňg → nv3
#   嗯 ǹg → nv4
# key 是"带声调符号但无数字声调"的全拼；value 是 (两位字母音码主体, 声调数字)。
EXTENDED_SPECIAL_CASES = {
    "ḿ":  ("mv", "2"),
    "m̀":  ("mv", "4"),
    "ńg": ("nv", "2"),
    "ňg": ("nv", "3"),
    "ǹg": ("nv", "4"),
}

CHAR_PINYIN_FILE = os.path.join(PROJECT_ROOT, "dict", "char_with_pinyin.txt")
DICTIONARY_FILE = os.path.join(PROJECT_ROOT, "dict", "dictionary.txt")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "agent_workspace")


# ---------------------------------------------------------------------------
# 1) 加载 char_with_pinyin.txt  -> {汉字: set(全拼带调)}
# ---------------------------------------------------------------------------
def load_char_with_pinyin(path):
    table = defaultdict(set)
    order = []
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            parts = re.split(r"\s+", line, maxsplit=1)
            if len(parts) != 2:
                continue
            hanzi, pinyin_full = parts
            if hanzi not in table:
                order.append(hanzi)
            table[hanzi].add(pinyin_full)
    return table, order


# ---------------------------------------------------------------------------
# 2) 加载 dictionary.txt  -> {汉字: set(音码 = 编码前3位)}
# ---------------------------------------------------------------------------
def load_dictionary(path):
    table = defaultdict(set)
    entries = 0
    with open(path, "r", encoding="utf-8") as f:
        for raw in f:
            line = raw.rstrip("\n").rstrip("\r")
            if not line.strip():
                continue
            parts = re.split(r"\s+", line, maxsplit=1)
            if len(parts) != 2:
                continue
            hanzi, code = parts
            if len(code) < 3:
                continue
            ab = code[:3]
            table[hanzi].add(ab)
            entries += 1
    return table, entries


# ---------------------------------------------------------------------------
# 3) 全拼带调（yī / bā / shuāng / lüè ...） → 三位音码
# ---------------------------------------------------------------------------
# 声调符号 → (基础字母, 声调数字)；不在表里的字母原样保留
_TONE_MARK_MAP = {
    "ā": ("a", "1"), "á": ("a", "2"), "ǎ": ("a", "3"), "à": ("a", "4"),
    "ē": ("e", "1"), "é": ("e", "2"), "ě": ("e", "3"), "è": ("e", "4"),
    "ī": ("i", "1"), "í": ("i", "2"), "ǐ": ("i", "3"), "ì": ("i", "4"),
    "ō": ("o", "1"), "ó": ("o", "2"), "ǒ": ("o", "3"), "ò": ("o", "4"),
    "ū": ("u", "1"), "ú": ("u", "2"), "ǔ": ("u", "3"), "ù": ("u", "4"),
    "ǖ": ("v", "1"), "ǘ": ("v", "2"), "ǚ": ("v", "3"), "ǜ": ("v", "4"),
}


def tone_mark_to_pinyin_with_tone(pinyin_full):
    """bā -> ba1, shuāng -> shuang1, lüè -> lve4。
    若全串没有任何声调符号，按 get_tone 规则视作轻声（5）。"""
    base_chars = []
    tone = None
    for ch in pinyin_full:
        if ch in _TONE_MARK_MAP:
            base_chars.append(_TONE_MARK_MAP[ch][0])
            tone = _TONE_MARK_MAP[ch][1]
        else:
            base_chars.append(ch)
    if tone is None:
        tone = "5"
    return "".join(base_chars) + tone


def pinyin_to_abc(pinyin_full):
    """单条带声调符号的全拼 → [音码]。
    复用 batch_entry 里的初始/韵母/声调解析（与 hanzi_to_abc 内的转换规则一致），
    但不调用 pypinyin，而是直接用我们构造的"数字声调全拼"作为输入。
    special_cases 里的整读音（hng/hm/ng/m/n）也走特殊映射。
    另：审查专用扩展 EXTENDED_SPECIAL_CASES 覆盖 呒/嗯/呣 三字。
    """
    # 1) 先看审查专用扩展（key 含声调符号，例如 "ḿ" / "ńg"）
    if pinyin_full in EXTENDED_SPECIAL_CASES:
        ab_body, tone = EXTENDED_SPECIAL_CASES[pinyin_full]
        return [f"{ab_body}{tone}"]

    py_with_tone = tone_mark_to_pinyin_with_tone(pinyin_full)
    base = re.sub(r"\d", "", py_with_tone)  # 去掉数字声调

    # 2) 走 batch_entry.hanzi_to_abc 一致的 special_cases 路径
    if base in special_cases:
        mapped = special_cases[base]  # 例如 "nv"
        # 与 hanzi_to_abc 内部一致：声调位仍用 get_tone() 解析
        c = get_tone(py_with_tone)
        return [f"{mapped[0]}{mapped[1]}{c}"]

    a = get_initial(py_with_tone)
    b = get_final(py_with_tone)
    c = get_tone(py_with_tone)
    if a and b and c:
        return [f"{a}{b}{c}"]
    return []


def cwp_expected_ab(cwp_set):
    """char_with_pinyin 全拼集合 → 三位音码集合。"""
    codes = set()
    for py in cwp_set:
        codes.update(pinyin_to_abc(py))
    return codes


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
def main():
    print("加载 char_with_pinyin.txt ...")
    cwp_table, cwp_order = load_char_with_pinyin(CHAR_PINYIN_FILE)
    print(f"  字形数：{len(cwp_table)}  条目数：{sum(len(v) for v in cwp_table.values())}")

    print("加载 dictionary.txt ...")
    dict_table, dict_entries = load_dictionary(DICTIONARY_FILE)
    print(f"  字形数：{len(dict_table)}  条目数：{dict_entries}")

    common_chars = set(cwp_table.keys()) & set(dict_table.keys())
    print(f"\n汉字交集（按字形）：{len(common_chars)}")

    # 对每个交集字分别生成「期望音码」与「实际音码」
    expected_per_char = {}
    actual_per_char = {}
    skipped = []
    for ch in common_chars:
        exp = cwp_expected_ab(cwp_table[ch])
        if not exp:
            skipped.append(ch)
        expected_per_char[ch] = exp
        actual_per_char[ch] = dict_table[ch]

    if skipped:
        print(f"\n⚠ {len(skipped)} 个汉字 cwp 全拼转换不出音码：")
        print("  " + " ".join(skipped))

    # (字, 音码) 级差
    rows_missing = []  # 期望有、实际无
    rows_extra = []    # 实际有、期望无
    rows_match = 0
    rows_partial = 0
    for ch in common_chars:
        exp = expected_per_char[ch]
        if not exp:
            continue
        act = actual_per_char[ch]
        miss = exp - act
        extra = act - exp
        if miss or extra:
            rows_partial += 1
        else:
            rows_match += 1
        for m in sorted(miss):
            rows_missing.append((ch, m))
        for e in sorted(extra):
            rows_extra.append((ch, e))

    missing_codes = set(c for _, c in rows_missing)
    extra_codes = set(c for _, c in rows_extra)

    all_expected = set().union(*expected_per_char.values())
    all_actual = set().union(*[actual_per_char[ch] for ch in common_chars])

    # 音码 → 关联字集合
    expected_code_to_chars = defaultdict(set)
    actual_code_to_chars = defaultdict(set)
    for ch, codes in expected_per_char.items():
        for c in codes:
            expected_code_to_chars[c].add(ch)
    for ch, codes in actual_per_char.items():
        for c in codes:
            actual_code_to_chars[c].add(ch)

    # 输出
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    summary = []
    summary.append("=" * 72)
    summary.append("拼音审查结果（仅基于 char_with_pinyin.txt，不使用 pypinyin）")
    summary.append("=" * 72)
    summary.append(f"char_with_pinyin.txt 字形数：{len(cwp_table)}")
    summary.append(f"dictionary.txt      字形数：{len(dict_table)}")
    summary.append(f"汉字交集（按字形）：          {len(common_chars)}")
    summary.append(f"交集内完全匹配的字数：      {rows_match}")
    summary.append(f"交集内部分匹配的字数：      {rows_partial}")
    summary.append(f"交集内期望音码种数：        {len(all_expected)}")
    summary.append(f"交集内实际音码种数：        {len(all_actual)}")
    summary.append(f"缺少音码种数：            {len(missing_codes)}")
    summary.append(f"多出音码种数：            {len(extra_codes)}")

    summary.append("")
    summary.append("-" * 72)
    summary.append("A. 缺少的音码（char_with_pinyin 期望、dictionary 未录）")
    summary.append("-" * 72)
    summary.append(f"共 {len(missing_codes)} 个音码，{len(rows_missing)} 条 (字, 音码)")
    summary.append("")
    summary.append("【按音码聚合】")
    for code in sorted(missing_codes):
        chars = sorted(expected_code_to_chars[code] - actual_code_to_chars.get(code, set()))
        summary.append(f"  {code} : {' '.join(chars)}")
    summary.append("")
    summary.append("【按字聚合】")
    by_char_missing = defaultdict(list)
    for ch, code in rows_missing:
        by_char_missing[ch].append(code)
    for ch in sorted(by_char_missing.keys()):
        summary.append(f"  {ch} : {' '.join(sorted(by_char_missing[ch]))}")

    summary.append("")
    summary.append("-" * 72)
    summary.append("B. 多出的音码（dictionary 已录、char_with_pinyin 不期望）")
    summary.append("-" * 72)
    summary.append(f"共 {len(extra_codes)} 个音码，{len(rows_extra)} 条 (字, 音码)")
    summary.append("")
    summary.append("【按音码聚合】")
    for code in sorted(extra_codes):
        chars = sorted(actual_code_to_chars[code] - expected_code_to_chars.get(code, set()))
        summary.append(f"  {code} : {' '.join(chars)}")
    summary.append("")
    summary.append("【按字聚合】")
    by_char_extra = defaultdict(list)
    for ch, code in rows_extra:
        by_char_extra[ch].append(code)
    for ch in sorted(by_char_extra.keys()):
        summary.append(f"  {ch} : {' '.join(sorted(by_char_extra[ch]))}")

    summary.append("")
    summary.append("-" * 72)
    summary.append("C. 交集内已录入的所有音码一览（按种类）")
    summary.append("-" * 72)
    summary.append(f"共 {len(all_actual)} 个音码")
    for code in sorted(all_actual):
        chars = sorted(actual_code_to_chars[code])
        summary.append(f"  {code} : {' '.join(chars)}")

    summary_path = os.path.join(OUTPUT_DIR, "pinyin_audit_summary.txt")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("\n".join(summary))
    print(f"\n汇总已写入：{summary_path}")

    # 不再生成 missing_codes.txt, extra_codes.txt, intersection_chars.txt

    # 终端摘要
    print("\n" + "=" * 72)
    print("摘要")
    print("=" * 72)
    print(f"交集字形：{len(common_chars)}  期望音码种数：{len(all_expected)}  实际音码种数：{len(all_actual)}")
    print(f"缺少音码种数：{len(missing_codes)}  多出音码种数：{len(extra_codes)}")
    print(f"完全匹配的字数：{rows_match}  部分匹配的字数：{rows_partial}")
    if missing_codes:
        print("\n缺少音码（按种类）：", " ".join(sorted(missing_codes)))
    if extra_codes:
        print("多出音码（按种类）：", " ".join(sorted(extra_codes)))


if __name__ == "__main__":
    main()
