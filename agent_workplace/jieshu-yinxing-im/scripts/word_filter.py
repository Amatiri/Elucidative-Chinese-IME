"""
word_filter.py - jieba 词表 → 待审清单

scripts 内部工具,不写码表。
"""

import argparse
import os
import sys
from datetime import datetime

# ── CJK 范围 ────────────────────────────────────────────────────────────────
CJK_RANGES = [
    (0x3400, 0x9FFF),
    (0xF900, 0xFAD9),
    (0x20000, 0x33479),
]


def is_cjk_char(ch: str) -> bool:
    cp = ord(ch)
    return any(start <= cp <= end for start, end in CJK_RANGES)


def is_pure_chinese(s: str) -> bool:
    return bool(s) and all(is_cjk_char(c) for c in s)


# ── 路径处理 ────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_JIEBA_PATHS = [
    os.path.join(SCRIPT_DIR, "..", "assets", "dict.txt"),
]


def resolve_jieba_path(arg_path):
    if arg_path and os.path.isfile(arg_path):
        return arg_path
    env = os.environ.get("JIESHU_IME_JIEBA")
    if env and os.path.isfile(env):
        return env
    for p in DEFAULT_JIEBA_PATHS:
        if os.path.isfile(p):
            return os.path.abspath(p)
    raise FileNotFoundError("未找到 jieba dict.txt")


def resolve_home_path() -> str:
    home = os.environ.get("JIESHU_IME_HOME")
    return home if home else r"D:\USB\Py\输入法"


def resolve_ciyu_path() -> str:
    return os.path.join(resolve_home_path(), "ciyu.txt")


def resolve_dictionary_path() -> str:
    return os.path.join(resolve_home_path(), "dictionary.txt")


def resolve_output_path(arg_path):
    if arg_path:
        return os.path.abspath(arg_path)
    return os.path.join(SCRIPT_DIR, "ciyu_review.txt")


def resolve_ignore_path() -> str:
    return os.path.join(SCRIPT_DIR, "ciyu_review.ignore.txt")


# ── jieba 解析 ───────────────────────────────────────────────────────────────
def parse_jieba(path, include_monograms=False):
    counter = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            word = parts[0]
            if not is_pure_chinese(word):
                continue
            n = len(word)
            if include_monograms:
                if n < 1 or n > 4:
                    continue
            else:
                if n < 2 or n > 4:
                    continue
            try:
                freq = int(parts[1])
            except ValueError:
                freq = 0
            if word in counter:
                if freq > counter[word]:
                    counter[word] = freq
            else:
                counter[word] = freq
    return list(counter.items())


# ── 码表读取 ────────────────────────────────────────────────────────────────
def load_ciyu_words(path):
    if not os.path.isfile(path):
        return set()
    words = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split()
            if parts and is_pure_chinese(parts[0]):
                words.add(parts[0])
    return words


def load_ignore_words(path):
    """读 ignore 文件:每行一个词,# 开头为注释。"""
    if not os.path.isfile(path):
        return set()
    words = set()
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if is_pure_chinese(line):
                words.add(line)
    return words


def load_char_codes(char, dictionary_path):
    """从 dictionary.txt 读 char 的所有编码。"""
    codes = []
    if not os.path.isfile(dictionary_path):
        return codes
    prefix = char + " "
    with open(dictionary_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.startswith(prefix):
                parts = line.rstrip("\n").split(" ", 1)
                if len(parts) == 2:
                    codes.append(parts[1])
    return codes


# ── 规则算法化 ──────────────────────────────────────────────────────

def _first_char_of(candidates):
    if not candidates:
        return None
    if isinstance(candidates, list):
        first = candidates[0]
        return first[0] if first else None
    if isinstance(candidates, str):
        first = candidates.split("/")[0] if "/" in candidates else candidates
        return first[0] if first else None
    return None


def probe_word(word, dictionary_path, query_by_prefix_fn):
    """
    返回 True 表示可前缀覆盖,False 表示需人工。
    词长度必须为 2。
    """
    c1, c2 = word[0], word[1]
    codes1 = load_char_codes(c1, dictionary_path)
    codes2 = load_char_codes(c2, dictionary_path)

    def char_coverable(char, codes):
        for code in codes:
            if len(code) < 2:
                continue
            prefix = code[:2]
            try:
                candidates = query_by_prefix_fn(prefix)
            except Exception:
                continue
            if _first_char_of(candidates) == char:
                return True
        return False

    return char_coverable(c1, codes1) and char_coverable(c2, codes2)


# ── 输出格式化 ───────────────────────────────────────────────────────────────
def format_review(
    items,
    existing,
    ignored,
    coverable_count,
    need_human_count,
    jieba_path,
    ciyu_path,
    ignore_path,
    dictionary_path,
    total_candidates,
):
    """仅输出「系统判需人工」的词。"""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = []
    lines.append("# 解书音形 · 待审词表")
    lines.append(f"# 生成时间:{timestamp}")
    lines.append(f"# 候选总数:{total_candidates}")
    lines.append(f"# 已收录(ciyu.txt):{len(existing)}")
    lines.append(f"# 忽略(ignore 文件):{len(ignored)}")
    lines.append(f"# 系统判可覆盖(规则 3 命中):{coverable_count}")
    lines.append(f"# 待人工录入(本清单):{need_human_count}")
    lines.append("#")
    lines.append(f"{'序号':<6}|{'词':<6}|{'字数':<5}|{'词频':<10}")
    lines.append("-" * 30)
    seq = 0
    for word, freq, n in items:
        seq += 1
        lines.append(f"{seq:<6}|{word:<6}|{n:<5}|{freq:<10}")
    return "\n".join(lines) + "\n"


def format_pure(items):
    """纯净输出:每行 10 个词,空格分隔,无任何附加信息。"""
    words = [w for w, _, _ in items]
    lines = []
    for i in range(0, len(words), 10):
        chunk = words[i:i + 10]
        lines.append(" ".join(chunk))
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


# ── 主流程 ──────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(
        description="jieba 词表 → 待审清单(纯工具,不写码表)。",
    )
    parser.add_argument("--jieba", type=str, default=None)
    parser.add_argument("--output", type=str, default=None)
    parser.add_argument("--limit", type=int, default=200)
    parser.add_argument("--min-freq", type=int, default=0)
    parser.add_argument("--include-monograms", action="store_true")
    parser.add_argument(
        "--no-probe", action="store_true",
        help="关闭 probe 规则 3(退回纯机械过滤)",
    )
    parser.add_argument(
        "--pure", action="store_true",
        help="纯净输出:每行 10 词,空格分隔,无序号/词频/字数(便于直接对接录入场景)",
    )
    parser.add_argument(
        "--probe-limit", type=int, default=5000,
        help="probe 只对词频最高的前 N 个候选运行(默认 5000,避免长时间扫描)",
    )
    args = parser.parse_args()

    # 路径
    try:
        jieba_path = resolve_jieba_path(args.jieba)
    except FileNotFoundError as e:
        print(f"[错误] {e}", file=sys.stderr)
        return 2

    ciyu_path = resolve_ciyu_path()
    dictionary_path = resolve_dictionary_path()
    output_path = resolve_output_path(args.output)
    ignore_path = resolve_ignore_path()


    # 1. 解析 jieba
    print("[step] 解析 jieba...")
    raw = parse_jieba(jieba_path, include_monograms=args.include_monograms)
    print(f"[info] 机械过滤后剩余:{len(raw)}")

    # 2. 加载 ciyu 已有词
    print("[step] 比对 ciyu.txt...")
    existing = load_ciyu_words(ciyu_path)
    print(f"[info] 已收录:{len(existing)}")

    # 3. 加载 ignore 文件
    print("[step] 加载 ignore 文件...")
    ignored = load_ignore_words(ignore_path)
    print(f"[info] 忽略词:{len(ignored)}")

    # 4. 装配三元组,应用 freq 下限
    enriched = [(w, f, len(w)) for w, f in raw]
    if args.min_freq > 0:
        enriched = [(w, f, n) for w, f, n in enriched if f >= args.min_freq]

    # 5. 剔除已有 + 忽略
    filtered = [(w, f, n) for w, f, n in enriched if w not in existing and w not in ignored]
    print(f"[info] 去已有+忽略后剩余:{len(filtered)}")

    # 6. 排序:词频降序 → 字数升序 → 词升序
    filtered.sort(key=lambda x: (-x[1], x[2], x[0]))

    # 7. probe(只对二字词;三字及以上直接判需人工)
    coverable_count = 0
    need_human: list[tuple[str, int, int]] = []

    if args.no_probe:
        print("[step] probe 关闭,全部保留为待审...")
        need_human = filtered[:args.limit]
        coverable_count = 0
    else:
        # 延迟导入
        sys.path.insert(0, resolve_home_path())
        from manager.dictionary_frontend import query_by_prefix

        probe_target = filtered[:args.probe_limit]
        print(f"[step] probe 运行:{len(probe_target)} 个二字词(上限 {args.probe_limit})...")

        for word, freq, n in probe_target:
            if n != 2:
                # 三字、四字词:probe 不适用,直接判需人工
                need_human.append((word, freq, n))
                continue
            try:
                if probe_word(word, dictionary_path, query_by_prefix):
                    coverable_count += 1
                else:
                    need_human.append((word, freq, n))
            except Exception as e:
                # probe 出错时降级:判需人工
                need_human.append((word, freq, n))

        # probe 之外的(超 probe_limit)直接判需人工
        for word, freq, n in filtered[args.probe_limit:]:
            need_human.append((word, freq, n))

    # 8. 应用 limit(对最终清单)
    need_human = need_human[:args.limit]
    need_human_count = len(need_human)

    # 9. 输出
    print("[step] 写入待审清单...")
    try:
        if args.pure:
            text = format_pure(need_human)
        else:
            text = format_review(
                need_human, existing, ignored,
                coverable_count, need_human_count,
                jieba_path, ciyu_path, ignore_path, dictionary_path,
                total_candidates=len(enriched),
            )
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(text)
    except OSError as e:
        print(f"[错误] 输出失败:{e}", file=sys.stderr)
        return 3

    print(f"[done] 待人工录入 {need_human_count} 条 → {output_path}")
    print(f"[hint] 录入流程:打开清单 → 走 main.py #8 添加词语")
    print(f"[hint] 录入后无需录入的词可追加到 {ignore_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
