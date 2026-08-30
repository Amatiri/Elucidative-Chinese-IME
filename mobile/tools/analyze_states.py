#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""状态机真值表反推 —— 用真引擎算出每一位的合法字符集，供设计稿校验。

计划 §3.2 的状态规则表是人工推演的，这个脚本用引擎实测反推。
两者对不上，说明设计稿要改（或引擎要改）。

判定的正确口径：
    不能只看 query_by_prefix(p + ch) —— 那只测单段。
    真实流程是 process_input → split_sequence → get_phrase_segments，
    多字模式下输入字母会切成新段（"bab" → "ba'b"），单段查不到但整体有输出。
    所以「这个键能不能按」必须用完整流程判定。

用法：
    python tools/analyze_states.py [最大位数]
"""

import io
import json
import sys
from collections import defaultdict
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE))

import manager.dictionary_frontend as df  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "tests" / "state_truth_table.json"

LETTERS = "abcdefghijklmnopqrstuvwxyz"
DIGITS = "0123456789"
ALL_CHARS = DIGITS + LETTERS + ";'."


def fast_query_phrase(code):
    code = code.replace(" ", "")
    m = _pmap()
    return "(" + m[code] + ")" if code in m else ""


_p = None


def _pmap():
    global _p
    if _p is None:
        m = {}
        with open(BASE / "dict" / "ciyu.txt", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(" ", 1)
                if len(parts) != 2:
                    continue
                for c in parts[1].split(" "):
                    if c and c not in m:
                        m[c] = parts[0]
        _p = m
    return _p


def load_codes():
    codes = []
    with open(BASE / "dict" / "dictionary.txt", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2:
                codes.append(parts[1])
    return codes


def group(cs):
    ds = sorted(c for c in cs if c in DIGITS)
    ls = sorted(c for c in cs if c in LETTERS)
    other = sorted(c for c in cs if c not in DIGITS and c not in LETTERS)
    out = []
    if ds:
        out.append("数字[" + "".join(ds) + "]")
    if ls:
        out.append("字母[" + "".join(ls) + "]")
    if other:
        out.append("其它[" + " ".join(other) + "]")
    return " ".join(out) if out else "（空）"


def shape_of(c):
    """逻辑位序形态。

    副码与补码都可省略，靠 '.' 引导符区分：引导符之前（或没有引导符）为副码，
    之后为补码。所以：
      - 第 5 位出现 '.'  → **没有副码**（a 占位且省略），是补码引导符提前，
        统计上必须归到第 6 位引导，不能记进副码；
      - 第 6 位出现字母  → 逻辑第 7 位补码 F，因第 5 位省略而左移一位。
    """
    dot = c.find(".")
    if dot == -1:
        return "ABCD" if len(c) == 4 else "ABCDE"
    if dot == 4:
        return "ABCD." if len(c) == 5 else "ABCD.F"
    return "ABCDE." if len(c) == 6 else "ABCDE.F"


def structure(codes):
    """按逻辑位序统计，并给出副码 / 引导符 / 补码的正确计数。"""
    shape = defaultdict(int)
    fuma = daoyin = buma = dot_at5 = 0
    for c in codes:
        shape[shape_of(c)] += 1
        if len(c) >= 5 and c[4] != ".":
            fuma += 1
        if "." in c:
            daoyin += 1
            if len(c) > c.find(".") + 1:
                buma += 1
        if c[4:5] == ".":
            dot_at5 += 1
    return {
        "shape": dict(shape),
        "fuma": fuma,           # 逻辑第 5 位副码（真出现）
        "daoyin": daoyin,       # 逻辑第 6 位引导符
        "buma": buma,           # 逻辑第 7 位补码 F
        "dotAtPos5": dot_at5,   # 物理第 5 位为 '.' —— 不得计入副码
    }


def has_output(s):
    """完整流程：用户按下这一串后，屏幕上有没有东西。"""
    segs = df.get_phrase_segments(df.split_sequence(s))
    display, all_parts, _ = segs
    # 有预览文本，或解析出了部件，都算有输出
    return bool(display) or bool(all_parts)


def main():
    max_pos = int(sys.argv[1]) if len(sys.argv) > 1 else 5

    df.query_phrase = fast_query_phrase  # 加速：1999 编码全唯一，语义等价

    codes = load_codes()

    # 前缀 → 该前缀之后出现过的字符（朴素口径，不含多字分词）
    next_chars = defaultdict(set)
    prefixes_by_len = defaultdict(set)
    for c in codes:
        for i in range(len(c)):
            next_chars[c[:i]].add(c[i])
            if i > 0:
                prefixes_by_len[i].add(c[:i])

    st = structure(codes)

    print(f"编码 {len(codes)} 条 | 最长 {max(len(c) for c in codes)} 位")
    print("判定口径 = process_input → split_sequence → get_phrase_segments 有无输出")
    print("⚠ 仅覆盖 dictionary.txt（单字）；ciyu.txt（词语 / 通用符号）不适用本表\n")
    print("-- 逻辑位序形态（'.' 是补码引导符，不是副码）--------------------------")
    for k in ("ABCD", "ABCDE", "ABCD.", "ABCD.F", "ABCDE.", "ABCDE.F"):
        print(f"   {k:<9} {st['shape'].get(k, 0):>5} 条")
    print(f"   副码 E  {st['fuma']:>5} 条（物理第 5 位为字母）")
    print(f"   引导符  {st['daoyin']:>5} 条（物理第 5 位 {st['dotAtPos5']} 条 + 第 6 位 "
          f"{st['daoyin'] - st['dotAtPos5']} 条）")
    print(f"   补码 F  {st['buma']:>5} 条（物理第 6 位 {st['shape'].get('ABCD.F', 0)} 条 "
          f"+ 第 7 位 {st['shape'].get('ABCDE.F', 0)} 条）")
    print("=" * 76)

    table = {}
    for pos in range(0, max_pos):
        prefixes = prefixes_by_len.get(pos, set()) if pos > 0 else {""}
        simple_ok, multi_ok, dead = set(), set(), set()

        for p in prefixes:
            # 只测朴素口径下可能出现的字符，外加全部字母（多字分词靠字母触发）
            candidates = set(next_chars.get(p, set())) | set(LETTERS)
            for ch in candidates:
                s = p + ch
                if not has_output(s):
                    dead.add(ch)
                    continue
                if ch in next_chars.get(p, set()):
                    simple_ok.add(ch)
                else:
                    multi_ok.add(ch)

        alive = simple_ok | multi_ok
        table[str(pos)] = {
            "prefixCount": len(prefixes),
            "simple": "".join(sorted(simple_ok)),
            "multiOnly": "".join(sorted(multi_ok)),
            "dead": "".join(sorted(dead)),
        }
        print(f"已输入 {pos} 位 → 第 {pos + 1} 位可按：")
        print(f"   单字命中  {group(simple_ok)}")
        if multi_ok:
            print(f"   仅多字    {group(multi_ok)}")
        print(f"   无输出    {group(dead)}")
        print("-" * 76)

    table["_structure"] = st

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(table, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写出 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
