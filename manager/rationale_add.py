"""
理据添加器 — 为 help/webpage/rationale-data.js 中的汉字补充手工理据
支持三种模式：
  1. 按序添加 — 从码表第一个缺少理据的合体字条目开始
  2. 随机添加 — 随机选取一个缺少理据的条目
  3. 指定汉字 — 用户输入汉字，逐条添加理据（支持批量）

理据独立于码表存放（rationale-data.js，每行 1 条、随码表顺序排序，正常入库），
因此添加理据不会触碰 dictionary-data.js（码表，整体生成、不入库）。
"""

import sys
import os
import re
import random

# ── 路径 ──
# 将项目根目录加入 sys.path，以便导入 config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from manager.file_processor import RATIONALE_FILE, read_rationale, write_rationale

DATA_FILE = config.DATA_FILE

# 独体字主码 → 数字类
SOLO_DIGITS = set("0123456789")


# ═══════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════

def is_hanzi(c):
    """判断单字符是否为汉字"""
    cp = ord(c)
    return (0x3400 <= cp <= 0x9FFF or
            0x20000 <= cp <= 0x33479 or
            0xF900 <= cp <= 0xFAD9)


def load_entries():
    """从 dictionary.txt 读取全部条目 → [(char, code), ...]"""
    entries = []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = re.split(r"\s+", line, maxsplit=1)
            if len(parts) == 2:
                entries.append((parts[0], parts[1]))
    return entries


def load_rationale():
    """从 rationale-data.js 读取理据对象"""
    return read_rationale(RATIONALE_FILE)


def save_rationale(rationale_dict):
    """将理据写回 rationale-data.js（每行 1 条，按码表顺序排序）"""
    try:
        write_rationale(rationale_dict, RATIONALE_FILE)
    except OSError as e:
        print(f"错误：理据文件写入失败 - {e}")
        return False
    return True


def needs_rationale(char, code):
    """判断条目是否需要手工理据

    需要：
      - 有补码且点后有编码（如 gj45.m）→ 一定需要
      - 无补码且为合体字（主码是字母）→ 需要
    不需要：
      - 仅一个点（如 ba13.）→ 不需要
      - 独体字（主码是数字）→ 不需要
    """
    dot_idx = code.find('.')
    if dot_idx != -1:
        # 点后有实质编码才需要（ba13. 不需要，gj45.m 需要）
        return dot_idx + 1 < len(code)

    # 无补码 → 合体字需要、独体字不需要
    if len(code) >= 4:
        d = code[3]
        return d not in SOLO_DIGITS
    return False


def build_char_map(entries):
    """预构建 char → [(char, code), ...] 映射，避免 O(n²) 扫描。"""
    char_map = {}
    for ch, code in entries:
        char_map.setdefault(ch, []).append((ch, code))
    return char_map


def get_char_codes(char_map, ch, filtered=True):
    """获取某字的所有编码列表。filtered=True 时仅返回 needs_rationale 的条目。"""
    entries = char_map.get(ch, [])
    if filtered:
        return [code for _, code in entries if needs_rationale(ch, code)]
    return [code for _, code in entries]


def show_char_codes(ch, codes, existing_rationale):
    print(f"====={ch}*{len(codes)}=====")
    for code in codes:
        print(f"  {ch} {code}")
    existing = existing_rationale.get(ch, "")
    if existing:
        print(f"已有: {existing}")
    return existing


# ═══════════════════════════════════════════
# 三种模式
# ═══════════════════════════════════════════

def mode_sequential(entries, rationale):
    """模式 1：按码表顺序，从第一个缺少理据的合体字条目开始"""
    char_map = build_char_map(entries)
    needed = []
    seen = set()
    for ch, code in entries:
        if ch in seen or ch in rationale:
            continue
        if needs_rationale(ch, code):
            seen.add(ch)
            codes = get_char_codes(char_map, ch, filtered=True)
            needed.append((ch, codes))

    if not needed:
        print("所有条目已有理据！")
        return

    total = sum(len(codes) for _, codes in needed)

    for char, codes in needed:
        show_char_codes(char, codes, rationale)
        val = input("理据: ").strip()
        if not val:
            print("退出\n")
            break
        if val.lower() == 'a':
            continue
        val = val.replace('\\n', '\n')
        rationale[char] = val
        save_rationale(rationale)
        print(f"✓ {char} → {val.replace(chr(10), ' / ')}")


def mode_random(entries, rationale):
    """模式 2：随机选一个缺少理据的条目"""
    char_map = build_char_map(entries)

    def pick_pool():
        pool = []
        seen = set()
        for ch, code in entries:
            if ch in seen or ch in rationale:
                continue
            if needs_rationale(ch, code):
                seen.add(ch)
                codes = get_char_codes(char_map, ch, filtered=True)
                pool.append((ch, codes))
        return pool

    pool = pick_pool()
    if not pool:
        print("所有条目已有理据！")
        return

    total = sum(len(codes) for _, codes in pool)

    while True:
        pool = pick_pool()
        if not pool:
            print("所有条目已有理据！")
            break

        ch, codes = random.choice(pool)
        show_char_codes(ch, codes, rationale)
        val = input("理据: ").strip()
        if not val:
            print("退出\n")
            break
        if val.lower() == 'a':
            continue
        val = val.replace('\\n', '\n')
        rationale[ch] = val
        save_rationale(rationale)
        print(f"✓ {ch} → {val.replace(chr(10), ' / ')}")


def mode_specified(entries, rationale):
    """模式 3：用户指定汉字，逐条添加（可批量），不限制独体字/补码字。"""
    char_map = build_char_map(entries)
    while True:
        inp = input("输入汉字: ").strip()
        if not inp:
            print("退出\n")
            break

        for ch in inp:
            if not is_hanzi(ch):
                print(f"「{ch}」不是汉字，跳过。")
                continue

            codes = get_char_codes(char_map, ch, filtered=False)
            if not codes:
                print(f"码表中未找到「{ch}」")
                continue

            show_char_codes(ch, codes, rationale)

            prompt = "理据: "
            val = input(prompt).strip()

            if not val:                # 回车退出
                print("退出\n")
                return
            if val.lower() == 'a':    # 跳过当前汉字
                continue

            val = val.replace('\\n', '\n')
            rationale[ch] = val
            save_rationale(rationale)
            print(f"✓ {ch} → {val.replace(chr(10), ' / ')}")


# ═══════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════

def main():
    print("解书音形 · 理据添加器")
    entries = load_entries()
    rationale = load_rationale()
    print(f"*码表条目{len(entries)}, 手工理据{len(rationale)}")
    print(f"*理据文件: {RATIONALE_FILE}")

    # 统计
    total_need = sum(1 for _, code in entries if needs_rationale("", code))
    remain = sum(1 for ch, code in entries
                 if needs_rationale(ch, code) and ch not in rationale)
    print(f"*需理据{total_need}条, 待补{remain}条")
    print("*a跳过，回车退出")
    print("*多音字换行用\\n\n")
    while True:
        print("1. 按序添加")
        print("2. 随机添加")
        print("3. 指定汉字(可批量)")

        choice = input("选: ").strip()

        if choice == '1':
            mode_sequential(entries, rationale)
        elif choice == '2':
            mode_random(entries, rationale)
        elif choice == '3':
            mode_specified(entries, rationale)
        elif choice == '':
            print("退出")
            break
        else:
            print("请重新输入\n")


if __name__ == "__main__":
    main()
