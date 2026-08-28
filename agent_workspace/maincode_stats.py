# -*- coding: utf-8 -*-
"""合体字主码（部首码）分布统计。
口径与技能 memory/01《码表中主码数据分析》及 manager/abc_analyzer.py 一致：
- 跳过含 . 的条目（点补/补码）、长度 < 4 的条目
- 编码结构 ABCD(E)：ABC=音码(音区)，D=主码(第4位)
- 独体字主码为数字 0-9，合体字为字母
- 每字母统计：字数、占比、需副码率(≥5码)、涉及音区数、单字音区率
"""
import sys
import collections
import os

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from config import DATA_FILE


def read_dictionary(file_path=DATA_FILE):
    """读取码表，返回 {编码: 汉字} 字典，跳过含点补或长度<4的条目。"""
    dictionary = {}
    with open(file_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(' ', 1)
            if len(parts) < 2:
                continue
            hanzi, code = parts[0], parts[1]
            if '.' in code or len(code) < 4:
                continue
            dictionary[code] = hanzi
    return dictionary


def main():
    dictionary = read_dictionary()
    print(f"有效条目（不含点补/补码）：{len(dictionary)}")

    digits = collections.Counter()                     # 独体字主码
    letter_count = collections.Counter()               # 合体字每字母字数
    letter_sub = collections.Counter()                 # 合体字每字母需副码(≥5码)字数
    letter_zones = collections.defaultdict(lambda: collections.Counter())  # 字母→音区→字数

    for code in dictionary:
        abc, d = code[:3], code[3]
        if d.isdigit():
            digits[d] += 1
        else:
            letter_count[d] += 1
            letter_zones[d][abc] += 1
            if len(code) > 4:
                letter_sub[d] += 1

    n_single = sum(digits.values())
    n_compound = sum(letter_count.values())
    total = len(dictionary)
    print(f"独体字 {n_single}（{n_single / total * 100:.2f}%） | 合体字 {n_compound}（{n_compound / total * 100:.2f}%）")

    mean = n_compound / len(letter_count) if letter_count else 0
    vals = sorted(letter_count.values())
    if vals:
        median = (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2 if len(vals) % 2 == 0 else vals[len(vals) // 2]
    else:
        median = 0
    print(f"合体字母码位 {len(letter_count)} 个 | 均值 {mean:.1f} | 中位数 {median:.1f}")
    print()
    print(f"{'主码':<4}{'字数':>5}{'占比':>8}{'需副码率':>9}{'音区数':>6}{'单字音区率':>10}")
    for d, cnt in sorted(letter_count.items(), key=lambda x: x[1]):
        zones = letter_zones[d]
        single_zones = sum(1 for z in zones.values() if z == 1)
        print(f"{d:<6}{cnt:>5}{cnt / n_compound * 100:>7.2f}%"
              f"{letter_sub[d] / cnt * 100:>8.2f}%"
              f"{len(zones):>6}{single_zones / len(zones) * 100:>9.2f}%")
    print()
    print("独体字数字主码分布:", " ".join(f"{k}:{v}" for k, v in sorted(digits.items())))
    input("回车以退出...")

if __name__ == "__main__":
    main()
