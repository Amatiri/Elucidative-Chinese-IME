#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""待录入表同步：以 待录入.txt 为准，审查 / 排序 / 音码化 待录入_拼音.txt。

处理三步：
  1. 审查
     - 辅表有、主表没有的字 → 删除该字在辅表中的全部条目（多音字删除多条）；
     - 主表有、辅表没有的字 → 用 pypinyin 生成该字的全部异读条目；
  2. 排序：按主表中的出现顺序重排（同一字的条目保持原相对次序）；
  3. 格式化：每行改写为「汉字 空格 音码」，音码由 manager.batch_entry 的转换逻辑产生。

路径均由 config.DATA_FILE 推导（与 manager.batch_entry.PENDING_FILE 同目录）。

用法：
    python agent_workspace/sync_pending_pinyin.py           # 出报告后交互询问是否写回
    python agent_workspace/sync_pending_pinyin.py --write   # 直接写回辅表
也可在「解书音形 - 管理中心 → agent_workspace 工具表」中调用（走无参数路径）。

注意：导入本模块会重新配置 sys.stdout 为 UTF-8（用于输出扩展区汉字）；
GUI 会把 sys.stdout 换成 PrintRedirector，此时自动跳过。
"""
import os
import re
import sys
from collections import OrderedDict

try:                                    # PrintRedirector 等重定向对象没有 reconfigure
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import config
from manager.batch_entry import extract_chinese, hanzi_to_abc, pinyin_to_abc

DICT_DIR = os.path.dirname(config.DATA_FILE)
PENDING_FILE = os.path.join(DICT_DIR, "待录入.txt")
PENDING_PINYIN_FILE = os.path.join(DICT_DIR, "待录入_拼音.txt")

CODE_RE = re.compile(r"[a-z][a-z;][0-9]")

TONE_MARKS = {
    "ā": ("a", "1"), "á": ("a", "2"), "ǎ": ("a", "3"), "à": ("a", "4"),
    "ē": ("e", "1"), "é": ("e", "2"), "ě": ("e", "3"), "è": ("e", "4"),
    "ī": ("i", "1"), "í": ("i", "2"), "ǐ": ("i", "3"), "ì": ("i", "4"),
    "ō": ("o", "1"), "ó": ("o", "2"), "ǒ": ("o", "3"), "ò": ("o", "4"),
    "ū": ("u", "1"), "ú": ("u", "2"), "ǔ": ("u", "3"), "ù": ("u", "4"),
    "ǖ": ("v", "1"), "ǘ": ("v", "2"), "ǚ": ("v", "3"), "ǜ": ("v", "4"),
    "ü": ("v", None), "ê": ("e", None),
    "ń": ("n", "2"), "ň": ("n", "3"), "ǹ": ("n", "4"), "ḿ": ("m", "2"), "m̀": ("m", "4"),
}


def read_text(path):
    """返回 (文本, 换行风格)；文本用 utf-8-sig 解码以兼容 BOM。"""
    with open(path, "rb") as f:
        raw = f.read()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    return raw.decode("utf-8-sig"), newline


def read_main_chars():
    """主表 待录入.txt → 去重后的汉字列表（保持出现顺序）。"""
    text, _ = read_text(PENDING_FILE)
    return list(OrderedDict.fromkeys(extract_chinese(text)))


def read_aux_entries():
    """辅表 待录入_拼音.txt → [(汉字, 原值, 行号), ...]；格式异常直接报错退出。"""
    text, _ = read_text(PENDING_PINYIN_FILE)
    entries, bad = [], []
    for lineno, line in enumerate(text.splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"[\t ]+", line, maxsplit=1)
        if len(parts) != 2 or not parts[0] or not parts[1].strip():
            bad.append((lineno, line))
            continue
        entries.append((parts[0].strip(), parts[1].strip(), lineno))
    if bad:
        print("辅表存在格式异常的行，已终止（未写文件）：")
        for lineno, line in bad:
            print(f"  第 {lineno} 行：{line}")
        sys.exit(1)
    return entries


def to_tone3(value):
    """辅表第二列 → 数字调拼音（如 yà → ya4）；已是数字调则原样返回。"""
    if re.fullmatch(r"[a-z]+[0-9]?", value):
        return value
    out, tone = [], None
    for ch in value:
        if ch.isdigit():
            tone = ch
            continue
        mapped = TONE_MARKS.get(ch)
        if mapped:
            base, mark_tone = mapped
            out.append(base)
            if mark_tone and tone is None:
                tone = mark_tone
        else:
            out.append(ch)
    if tone is None:
        tone = "0"
    return "".join(out).lower() + tone


def sync(write=False):
    """审查 → 排序 → 音码化，返回最终 [(汉字, 音码), ...]；write=True 时写回辅表。"""
    main_chars = read_main_chars()
    aux_entries = read_aux_entries()
    main_set = set(main_chars)
    aux_chars = list(OrderedDict.fromkeys(h for h, _, _ in aux_entries))
    aux_set = set(aux_chars)

    # ---- 1. 审查 ----
    removed = [h for h in aux_chars if h not in main_set]
    removed_lines = [(h, v) for h, v, _ in aux_entries if h in set(removed)]
    added = [h for h in main_chars if h not in aux_set]

    kept = [(h, v, ln) for h, v, ln in aux_entries if h in main_set]

    entries = []          # [(汉字, 音码)]
    conv_fail = []        # 现有条目转换失败（致命）
    for hanzi, value, lineno in kept:
        code = value if CODE_RE.fullmatch(value) else pinyin_to_abc(to_tone3(value))
        if not code:
            conv_fail.append((lineno, hanzi, value))
            continue
        entries.append((hanzi, code))

    new_fail = []         # 新增字 pypinyin 无结果（告警）
    for hanzi in added:
        codes = hanzi_to_abc(hanzi)
        if not codes:
            new_fail.append(hanzi)
        for code in codes:
            entries.append((hanzi, code))

    if conv_fail:
        print("辅表条目音码转换失败，已终止（未写文件）：")
        for lineno, hanzi, value in conv_fail:
            print(f"  第 {lineno} 行：{hanzi} {value}")
        sys.exit(1)

    # ---- 去重（同字同音码保留首次出现） ----
    deduped, seen = [], set()
    dup_count = 0
    for hanzi, code in entries:
        if (hanzi, code) in seen:
            dup_count += 1
            continue
        seen.add((hanzi, code))
        deduped.append((hanzi, code))

    # ---- 2. 排序：按主表顺序（同字条目稳定保持原次序） ----
    order = {ch: i for i, ch in enumerate(main_chars)}
    deduped.sort(key=lambda item: order[item[0]])

    # ---- 报告 ----
    print(f"主表 {os.path.basename(PENDING_FILE)}：{len(main_chars)} 字")
    print(f"辅表 {os.path.basename(PENDING_PINYIN_FILE)}：{len(aux_entries)} 条 / {len(aux_chars)} 字")
    print(f"\n[审查] 删除（辅表有、主表无）：{len(removed)} 字 / {len(removed_lines)} 条"
          f"{'：' + ' '.join(removed) if removed else ''}")
    print(f"[审查] 新增（主表有、辅表无）：{len(added)} 字"
          f"{'：' + ' '.join(added) if added else ''}")
    print(f"[去重] 同字同音码重复条目：{dup_count} 条")
    if new_fail:
        print(f"[告警] pypinyin 无结果的字（未生成条目）：{''.join(new_fail)}")
    print(f"[排序] 按主表顺序重排，共 {len(deduped)} 条")
    head = " / ".join(f"{h} {c}" for h, c in deduped[:5])
    tail = " / ".join(f"{h} {c}" for h, c in deduped[-3:])
    print(f"[格式] 汉字 空格 音码；首：{head} … 尾：{tail}")

    # ---- 3. 写回 ----
    if write:
        write_entries(deduped)
    return deduped


def write_entries(entries):
    """写回辅表：沿用原文件换行风格，不带 BOM。"""
    _, newline = read_text(PENDING_PINYIN_FILE)
    with open(PENDING_PINYIN_FILE, "w", encoding="utf-8", newline="") as f:
        for hanzi, code in entries:
            f.write(f"{hanzi} {code}{newline}")
    print(f"\n已写回 {PENDING_PINYIN_FILE}（{len(entries)} 条）")


def ask_write():
    """交互询问是否写回；非交互环境（EOF/中断）一律视为不写回。"""
    try:
        answer = input("是否写回？(y/n): ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in ("y", "yes")


def main():
    """入口。

    - 命令行：带 --write 直接写回，其它参数只出预览；
    - 无参数（agent_work 工具表调用的即是这一路径）：先出报告，再用 input 询问是否写回。
    """
    args = sys.argv[1:]
    entries = sync(write="--write" in args)
    if args:
        if "--write" not in args:
            print("\n未写回（加 --write 可直接写回）。")
        return
    if entries and ask_write():
        write_entries(entries)
    else:
        print("未写回，文件保持不变。")


if __name__ == "__main__":
    main()
