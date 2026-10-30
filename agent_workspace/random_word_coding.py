# -*- coding: utf-8 -*-
import os
import random
import sys

try:                                    # PrintRedirector 等重定向对象没有 reconfigure
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import config


def load_dictionary(path):
    """读取 dictionary.txt：
    - 每行恰好一个空格，分为前后两部分
    - 第二部分长度 >= 4
    返回所有合法行的第二部分字符串列表。
    """
    seconds = []
    with open(path, encoding="utf-8") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.rstrip("\n")
            if not line.strip():
                continue
            parts = line.split(" ")
            if len(parts) != 2:
                print(f"[dictionary] 跳过第 {lineno} 行：不是恰好一个空格", file=sys.stderr)
                continue
            second = parts[1]
            if len(second) < 4:
                print(f"[dictionary] 跳过第 {lineno} 行：第二部分不足 4 个字符", file=sys.stderr)
                continue
            seconds.append(second)
    return seconds


def load_ciyu(path):
    """读取 ciyu.txt：
    - 每行可能有多个空格，取第 2 个及以后的字段（切片 [1:]）
    - 每个字段若长度 > 4 取前 4 位，否则取全部
    返回一个集合，用于后续前缀检测。
    """
    bad = set()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            for w in parts[1:]:
                s = w[:4] if len(w) > 4 else w
                bad.add(s)
    return bad


def has_bad_prefix(code, bad):
    """若 code 的任一前缀（含 code 本身）出现在 bad 中，返回 True。"""
    for L in range(1, len(code) + 1):
        if code[:L] in bad:
            return True
    return False


def main():
    seconds = load_dictionary(config.DATA_FILE)
    bad = load_ciyu(config.CIYU_FILE)

    if not seconds:
        print("dictionary.txt 没有可用数据", file=sys.stderr)
        return

    target = 10
    results = []
    used = set()
    attempts = 0
    max_attempts = 10_000_000  # 防止极端情况下死循环

    while len(results) < target and attempts < max_attempts:
        attempts += 1

        # 第 2 步：随机抽两次第二部分的前两个字符，前后拼成 4 码串
        s1 = random.choice(seconds)
        s2 = random.choice(seconds)
        code = s1[:2] + s2[:2]

        # 避免输出重复
        if code in used:
            continue

        # 第 5 步：只要 code 的任何前缀出现在 ciyu 集合里，就打回重来
        if has_bad_prefix(code, bad):
            continue

        used.add(code)
        results.append(code)

    if len(results) < target:
        print(f"警告：只收集到 {len(results)} 条（尝试 {attempts} 次）", file=sys.stderr)

    # 第 6 步：输出 10 条
    for i, r in enumerate(results, 1):
        print(f"{i}. {r}")


if __name__ == "__main__":
    main()
