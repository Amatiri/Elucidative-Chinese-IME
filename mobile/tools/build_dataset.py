#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""移动端数据集构建脚本。

独立于 manager/file_processor.py —— 不读取、不修改仓库内任何文件。
只做一件事：把 dict/ 下的两份码表转成 mobile/src/data/dataset.ts。

用法：
    python mobile/tools/build_dataset.py

产出结构的设计要点：
  1. entries 是 flat 字符串 "字码,字码,..."，严格按 dictionary.txt 行序。
     移动端需要「编码 → 字」的有序索引，而网页版 dictionary-data.js 的
     chars 是「字 → [码]」反查结构，无法还原全局行序，故必须独立产出。
  2. 每项从尾部向前扫描解析：连续属于 CODE_CHARS 的部分是 code，剩余前缀是 word。
     这样即使 word 是非 BMP 字符（152 条，UTF-16 代理对），解析也不会错位。
  3. phraseIndex 是「编码 → 词语」正向索引，替代 query_phrase 每次全扫 1939 行。
"""
import gzip
import hashlib
import io
import json
import sys
from datetime import datetime
from pathlib import Path

# 与 config.py:17 保持一致。不 import config —— 它带 tkinter 依赖。
CODE_CHARS = "1234567890qwertyuiopasdfghjklzxcvbnm;'."
CODE_CHAR_SET = set(CODE_CHARS)

BASE = Path(__file__).resolve().parents[2]  # 项目根 D:\USB\Py\输入法
DICT_FILE = BASE / "dict" / "dictionary.txt"
CIYU_FILE = BASE / "dict" / "ciyu.txt"
OUT_FILE = Path(__file__).resolve().parents[1] / "src" / "data" / "dataset.ts"


def read_dictionary():
    """按行序读 (字, 码)。分割语义与 dictionary_frontend.py:39 一致：严格单空格。"""
    entries = []
    with open(DICT_FILE, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) != 2:
                raise ValueError(f"dictionary.txt:{lineno} 格式异常: {line!r}")
            entries.append((parts[0], parts[1]))
    return entries


def read_ciyu():
    """读 (词, 码) 列表，保持行序 + 行内顺序。分割语义与 query_phrase 一致。"""
    pairs = []
    phrase_count = 0
    with open(CIYU_FILE, encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) != 2:
                raise ValueError(f"ciyu.txt:{lineno} 格式异常: {line!r}")
            phrase, codes_str = parts
            phrase_count += 1
            fields = codes_str.split(" ")
            if any(not c for c in fields):
                raise ValueError(f"ciyu.txt:{lineno} 存在连续空格: {line!r}")
            for c in fields:
                pairs.append((phrase, c))
    return pairs, phrase_count


def validate(entries, pairs):
    """产出前的数据自检。任何一条不满足就中止，不产出半成品。"""
    errs = []

    for i, (w, c) in enumerate(entries):
        if len(w) != 1:
            errs.append(f"dictionary 第 {i} 条 word 非单码点: {w!r}")
        if any(ch in CODE_CHAR_SET for ch in w):
            errs.append(f"dictionary 第 {i} 条 word 含编码字符: {w!r}")
        if not c or any(ch not in CODE_CHAR_SET for ch in c):
            errs.append(f"dictionary 第 {i} 条 code 含非法字符: {c!r}")
        if "," in w or "," in c:
            errs.append(f"dictionary 第 {i} 条含逗号（flat 分隔符冲突）: {w!r}+{c!r}")

    for i, (p, c) in enumerate(pairs):
        if not c or any(ch not in CODE_CHAR_SET for ch in c):
            errs.append(f"ciyu 第 {i} 条 code 含非法字符: {c!r}")
        if "," in p or "," in c:
            errs.append(f"ciyu 第 {i} 条含逗号（flat 分隔符冲突）: {p!r}+{c!r}")

    # 编码唯一性：dictionary 侧
    codes = [c for _, c in entries]
    if len(set(codes)) != len(codes):
        dup = [c for c in set(codes) if codes.count(c) > 1][:5]
        errs.append(f"dictionary 编码不唯一，样例: {dup}")

    # 编码唯一性：ciyu 侧（phraseIndex 的结构前提）
    pcodes = [c for _, c in pairs]
    if len(set(pcodes)) != len(pcodes):
        dup = [c for c in set(pcodes) if pcodes.count(c) > 1][:5]
        errs.append(f"ciyu 编码不唯一（无法建正向索引），样例: {dup}")

    return errs


def encode_flat(entries):
    return ",".join(w + c for w, c in entries)


def decode_flat(flat):
    """与 TS 侧 parseEntries 完全一致的解析逻辑。用于 round-trip 自检。"""
    out = []
    for item in flat.split(","):
        if not item:
            continue
        i = len(item)
        while i > 0 and item[i - 1] in CODE_CHAR_SET:
            i -= 1
        out.append((item[:i], item[i:]))
    return out


def compute_source_sha():
    h = hashlib.sha256()
    h.update(DICT_FILE.read_bytes())
    h.update(b"\x00")
    h.update(CIYU_FILE.read_bytes())
    return h.hexdigest()[:16]


def fmt_phrase_index(pidx, per_line=8):
    """每行 8 条，兼顾可读性与体积。"""
    items = [f"{json.dumps(k, ensure_ascii=False)}:{json.dumps(v, ensure_ascii=False)}"
             for k, v in pidx.items()]
    lines = []
    for i in range(0, len(items), per_line):
        lines.append("    " + ",".join(items[i:i + per_line]) + ",")
    if lines:
        # 去掉最后一行的尾逗号
        lines[-1] = lines[-1].rstrip(",")
    return "\n".join(lines)


def build_ts(entries, pairs, phrase_count, source_sha, flat, pidx):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    nonbmp = sum(1 for w, _ in entries if ord(w[0]) > 0xFFFF)
    L = []
    A = L.append
    A("// 自动生成，勿手动编辑")
    A(f"// 源：dict/dictionary.txt（{len(entries)} 条）+ dict/ciyu.txt"
      f"（{phrase_count} 词 / {len(pairs)} 编码）")
    A(f"// 生成时间：{now}")
    A(f"// sourceSha：{source_sha}")
    A("// 生成脚本：mobile/tools/build_dataset.py")
    A("")
    A("export interface RawDataset {")
    A("  /** flat 串格式版本 */")
    A("  version: number;")
    A("  /** 汉字条目数 = dictionary.txt 行数 */")
    A("  entryCount: number;")
    A("  /** 词语数 = ciyu.txt 行数 */")
    A("  phraseCount: number;")
    A("  /** ciyu.txt 中编码总数（含多编码词条） */")
    A("  codeCount: number;")
    A("  /** 非 BMP 条目数（UTF-16 代理对，禁止用下标取首字） */")
    A("  nonBmpCount: number;")
    A("  /** 源码表内容 sha256 前 16 位，用于检测码表变更 */")
    A("  sourceSha: string;")
    A("  /** flat 串 \"字码,字码,...\"，严格按 dictionary.txt 行序。解析见 dataset.ts#parseEntries */")
    A("  entries: string;")
    A("  /** 编码 → 词语（ciyu.txt）。编码全唯一，故是 1:1 */")
    A("  phraseIndex: Record<string, string>;")
    A("}")
    A("")
    A("export const DATASET: RawDataset = {")
    A("  version: 1,")
    A(f"  entryCount: {len(entries)},")
    A(f"  phraseCount: {phrase_count},")
    A(f"  codeCount: {len(pairs)},")
    A(f"  nonBmpCount: {nonbmp},")
    A(f'  sourceSha: "{source_sha}",')
    A(f"  entries: {json.dumps(flat, ensure_ascii=False)},")
    A("  phraseIndex: {")
    A(fmt_phrase_index(pidx))
    A("  },")
    A("};")
    A("")
    return "\n".join(L)


def main():
    # stdout 重配放在这里而非模块顶层：被 import 时不产生副作用
    # （顶层重配会关闭调用方已有的 wrapper，导致后续 print 崩）
    if hasattr(sys.stdout, "buffer"):
        sys.stdout = io.TextIOWrapper(
            sys.stdout.buffer, encoding="utf-8", errors="replace"
        )

    print(f"读取 {DICT_FILE}")
    entries = read_dictionary()
    print(f"读取 {CIYU_FILE}")
    pairs, phrase_count = read_ciyu()

    print(f"\n条目：{len(entries)} | 词语：{phrase_count} | ciyu 编码：{len(pairs)}")

    print("自检中...")
    errs = validate(entries, pairs)
    if errs:
        print("【自检失败，未产出任何文件】")
        for e in errs[:20]:
            print(f"  - {e}")
        if len(errs) > 20:
            print(f"  ... 另有 {len(errs) - 20} 条")
        return 1

    flat = encode_flat(entries)
    back = decode_flat(flat)
    if back != entries:
        print("【round-trip 失败，未产出任何文件】")
        for i, (a, b) in enumerate(zip(entries, back)):
            if a != b:
                print(f"  第 {i} 条不一致: {a!r} != {b!r}")
                break
        return 1
    print("round-trip 通过")

    pidx = {c: p for p, c in pairs}
    if len(pidx) != len(pairs):
        print(f"【phraseIndex 容量不足】{len(pairs)} -> {len(pidx)}，未产出")
        return 1

    source_sha = compute_source_sha()
    ts = build_ts(entries, pairs, phrase_count, source_sha, flat, pidx)

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(ts)

    raw = len(ts.encode("utf-8"))
    gz = len(gzip.compress(ts.encode("utf-8"), 9))
    nonbmp = sum(1 for w, _ in entries if ord(w[0]) > 0xFFFF)
    print(f"\n已写出：{OUT_FILE}")
    print(f"  体积 raw {raw:,} B / gzip {gz:,} B（{gz / 1024:.1f} KB）")
    print(f"  非 BMP 条目：{nonbmp}")
    print(f"  sourceSha：{source_sha}")
    if gz > 50 * 1024:
        print(f"  【警告】gzip 超过 50KB 目标")
    return 0


if __name__ == "__main__":
    sys.exit(main())
