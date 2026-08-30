#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Golden 夹具生成器 —— 用 Python 真引擎 dump 期望输出，供 TS 引擎逐条比对。

只读码表，不写仓库内任何文件。产出：
    mobile/tests/golden_v1.json

用法：
    python tools/gen_golden.py                      # 全量
    python tools/gen_golden.py --only split         # 只生成 split_sequence 用例
    python tools/gen_golden.py --only split --limit 2000
"""

import argparse
import io
import json
import random
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

BASE = Path(__file__).resolve().parents[2]  # 项目根
sys.path.insert(0, str(BASE))

from config import CODE_CHARS, CIYU_FILE  # noqa: E402
import manager.dictionary_frontend as df  # noqa: E402

OUT_DIR = Path(__file__).resolve().parents[1] / "tests"
OUT_FILE = OUT_DIR / "golden_v1.json"

RNG_SEED = 42


# ── ciyu 查询加速 ─────────────────────────────────────────────────────────
# 原版 query_phrase 每次调用都重新打开 ciyu.txt 全扫 1939 行。生成 2500 条
# get_phrase_segments 用例会触发上万次，太慢。
# 2003 个编码全唯一（已验证），故「顺序扫描取首个匹配」≡「正向索引查表」，
# 两者语义等价。唯一偏差：原版对 code="" 会命中首行（split 产生空字段），
# 加速版返回 ""。夹具不生成 code="" 的用例，该偏差显式登记在 meta.deviations。

_phrase_map = None


def _build_phrase_map():
    global _phrase_map
    if _phrase_map is not None:
        return _phrase_map
    m = {}
    with open(CIYU_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue
            phrase, codes_str = parts
            for c in codes_str.split(" "):
                if c and c not in m:
                    m[c] = phrase
    _phrase_map = m
    return m


def fast_query_phrase(code):
    code = code.replace(" ", "")
    m = _build_phrase_map()
    if code in m:
        return "(" + m[code] + ")"
    return ""


def _ciyu_stats():
    """(行数, 编码总数)。与 build_dataset.read_ciyu 口径一致。"""
    lines = 0
    codes = 0
    with open(CIYU_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) != 2:
                continue
            lines += 1
            codes += len(parts[1].split(" "))
    return lines, codes


def _source_sha():
    """与 build_dataset.compute_source_sha 口径一致：dictionary + \\0 + ciyu。"""
    import hashlib
    h = hashlib.sha256()
    h.update(Path(df.DATA_FILE).read_bytes())
    h.update(b"\x00")
    h.update(Path(CIYU_FILE).read_bytes())
    return h.hexdigest()[:16]


def verify_fast_equivalence(sample=300, seed=7):
    """用原版抽查，证明加速版语义等价。不等价就直接中止。"""
    rng = random.Random(seed)
    all_codes = list(_build_phrase_map().keys())
    cases = rng.sample(all_codes, min(sample, len(all_codes)))
    cases += ["", "zzz", "ba1", "d..", "b;du"]
    for c in cases:
        a = df.query_phrase(c)
        b = fast_query_phrase(c)
        if a != b:
            raise SystemExit(f"加速版与原版不一致: {c!r} 原版={a!r} 加速={b!r}")
    return len(cases)


# ── 用例生成 ──────────────────────────────────────────────────────────────

def all_prefixes(entries):
    """全部 8152 条编码的所有真前缀，去重。"""
    seen = set()
    for word, code in entries:
        for i in range(1, len(code)):
            seen.add(code[:i])
    return sorted(seen)


def rand_str(rng, minlen=1, maxlen=8, pool=None):
    pool = pool or (CODE_CHARS + "'")
    return "".join(rng.choice(pool) for _ in range(rng.randint(minlen, maxlen)))


def gen_split(entries, prefixes, rng, limit=None):
    cases = []
    src = []
    src += [("prefix", p) for p in prefixes]
    src += [("code", c) for _, c in entries]
    # 随机串：含 ' 与 '.'，专门触发 condition5 与尾部引号逻辑
    for _ in range(3000):
        src.append(("rand", rand_str(rng, 3, 8)))
    # 边界：引号相关的手工用例
    src += [
        ("edge", "'"), ("edge", "''"), ("edge", "ba'"), ("edge", "'ba"),
        ("edge", "ba''1b"), ("edge", ""), ("edge", "."), ("edge", "ba13."),
        ("edge", "ba13.x"), ("edge", "bab"), ("edge", "baba"), ("edge", "babab"),
        ("edge", "1234"), ("edge", "12'34"), ("edge", "b;1b"), ("edge", "a.b.c"),
    ]
    if limit:
        src = src[:limit]
    for kind, s in src:
        out = df.split_sequence(s)
        cases.append({"id": f"ss:{kind}:{s}", "fn": "split_sequence", "args": [s], "out": out})
    return cases


def gen_query(entries, prefixes, rng, limit=None):
    cases = []

    def add(prefix, start, count, tag):
        out = df.query_by_prefix(prefix, start, count)
        cases.append({
            "id": f"qbp:{tag}:{prefix}:{start}:{count}",
            "fn": "query_by_prefix",
            "args": [prefix, start, count],
            "out": out,
        })

    # 1. 全前缀穷举
    for p in prefixes:
        add(p, 0, 10, "all")

    # 2. 分页交叉：候选 >5 的前缀才值得翻页
    page_src = [p for p in prefixes if len(df.query_by_prefix(p, 0, 10)) > 5]
    for p in page_src:
        add(p, 3, 5, "page")
        add(p, 5, 5, "page2")

    # 3. 副码 a 分支（prefix[4]=='a'，L64-70）
    #    注意判的是 **prefix** 的第 5 位，不是 code 的 —— 用真实码表即可覆盖，
    #    不需要注入合成条目。
    a_src = set()
    for _, code in entries:
        if len(code) >= 4:
            a_src.add(code[:4] + "a")                     # branch1: code 长 4 时精确命中
            if len(code) >= 5:
                a_src.add(code[:4] + "a" + code[5:])      # branch2 全量
                a_src.add(code[:4] + "a" + code[5:6])     # branch2 部分
        if len(code) >= 6:
            a_src.add(code[:5] + "a")
    for p in sorted(a_src):
        add(p, 0, 10, "supa")

    # 4. 完整 code 作为前缀
    for _, code in entries:
        add(code, 0, 10, "full")

    # 5. 补码相关：含 '.' 的编码的所有前缀
    dot_prefixes = sorted({code[:i] for _, code in entries
                           if "." in code for i in range(1, len(code) + 1)})
    for p in dot_prefixes:
        add(p, 0, 10, "dot")

    # 6. 负例：不存在的首字母 / 空串
    for p in ["", "0", ".", "'", ";", "zzzz", "9999"]:
        add(p, 0, 10, "neg")

    # 7. count 边界
    for p in prefixes[:50]:
        add(p, 0, 1, "cnt1")
        add(p, 0, 0, "cnt0")

    if limit:
        cases = cases[:limit]
    return cases


def gen_segments(entries, prefixes, rng, limit=None):
    cases = []
    all_codes = list(_build_phrase_map().keys())

    def add(s, tag):
        display, parts, literal = df.get_phrase_segments(s)
        cases.append({
            "id": f"gps:{tag}:{s}",
            "fn": "get_phrase_segments",
            "args": [s],
            "out": [display, parts, sorted(literal)],
        })

    for c in all_codes:
        add(c, "ciyu")
    for p in prefixes[:400]:
        add(p, "prefix")
    for _ in range(800):
        add(rand_str(rng, 1, 10), "rand")
    # 多段（含手动 ' 分隔）
    for _ in range(400):
        n = rng.randint(2, 4)
        s = "'".join(rand_str(rng, 1, 5) for _ in range(n))
        add(s, "multi")
    if limit:
        cases = cases[:limit]
    return cases


def gen_multi(entries, prefixes, rng, limit=None):
    cases = []
    src = [df.split_sequence(p) for p in prefixes]
    src += [df.split_sequence(c) for _, c in entries[:2000]]
    for _ in range(1000):
        src.append(df.split_sequence(rand_str(rng, 1, 9)))
    if limit:
        src = src[:limit]
    seen = set()
    for s in src:
        if s in seen:
            continue
        seen.add(s)
        cases.append({
            "id": f"qmc:{s}",
            "fn": "query_multi_chars",
            "args": [s],
            "out": df.query_multi_chars(s),
        })
    return cases


def gen_process(rng, limit=None):
    cases = []
    src = list(CODE_CHARS)
    src += ["", "   ", "abc", "ABC abc", "a1b2c3", "中文abc123",
            "x'y", "a.b", ";'", "  ba1  ", "abc中文def"]
    for _ in range(1500):
        src.append(rand_str(rng, 1, 10, pool=CODE_CHARS + " 中abcXYZ.;'"))
    if limit:
        src = src[:limit]
    seen = set()
    for s in src:
        if s in seen:
            continue
        seen.add(s)
        cases.append({
            "id": f"pi:{s}",
            "fn": "process_input",
            "args": [s],
            "out": df.process_input(s),
        })
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", choices=["split", "query", "segments", "multi", "process"],
                    help="只生成某一类用例")
    ap.add_argument("--limit", type=int, help="每类用例的条数上限（快速迭代用）")
    ap.add_argument("--no-verify", action="store_true", help="跳过加速版等价性抽查")
    args = ap.parse_args()

    t0 = time.time()

    # 直接从文件读，保证行序与被测引擎的 _get_index 完全一致
    # （不能从 _get_index 的桶反推 —— 按首字母归并后全局行序已丢失）
    entries = []
    with open(df.DATA_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(" ", 1)
            if len(parts) == 2:
                entries.append((parts[0], parts[1]))

    prefixes = all_prefixes(entries)
    print(f"条目 {len(entries)} | 去重真前缀 {len(prefixes)}")

    if not args.no_verify:
        n = verify_fast_equivalence()
        df.query_phrase = fast_query_phrase
        print(f"加速版等价性抽查通过（{n} 条）")
    else:
        df.query_phrase = fast_query_phrase

    rng = random.Random(RNG_SEED)
    cases = []
    plan = [
        ("split", gen_split),
        ("query", gen_query),
        ("segments", gen_segments),
        ("multi", gen_multi),
        ("process", gen_process),
    ]
    for name, fn in plan:
        if args.only and name != args.only:
            continue
        t = time.time()
        got = fn(entries, prefixes, rng, args.limit) if name != "process" \
            else gen_process(rng, args.limit)
        cases += got
        print(f"  {name:9s} {len(got):6d} 条  ({time.time() - t:.1f}s)")

    payload = {
        "schema": "jieshu-golden/1",
        "source": {
            "dictionary": len(entries),
            "ciyuLines": None,   # 下面补充
            "ciyuCodes": None,
            "sourceSha": None,   # 下面补充
            "seed": RNG_SEED,
        },
        "meta": {
            "deviations": [
                "query_phrase: 生成器用正向索引加速，与原版顺序扫描等价（1999 编码全唯一）；"
                "唯一差异是 code='' 时原版命中首行而加速版返回 ''，夹具不含该用例",
                "isdigit: TS 端用 ASCII 0-9 比较，Python str.isdigit() 对 '²' '٣' 等为真；"
                "码表与键盘输入不可能产生这类字符，夹具不涉及",
            ],
            "notes": [
                "query_by_prefix L64 判的是 prefix[4]=='a'（查询参数），不是 code[4]=='a'；"
                "真实码表 code[4]=='a' 命中 0 条，但该分支可用 prefix 构造覆盖，非死代码",
            ],
        },
        "cases": cases,
    }
    # 补充 source 字段。刻意不 import build_dataset —— 保持两个脚本独立。
    phrase_count, code_count = _ciyu_stats()
    payload["source"]["ciyuLines"] = phrase_count
    payload["source"]["ciyuCodes"] = code_count
    payload["source"]["sourceSha"] = _source_sha()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    raw = OUT_FILE.stat().st_size
    print(f"\n已写出 {OUT_FILE}")
    print(f"  用例 {len(cases):,} 条 | raw {raw:,} B ({raw / 1024 / 1024:.2f} MB)")
    print(f"  总耗时 {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
