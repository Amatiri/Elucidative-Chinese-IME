# -*- coding: utf-8 -*-
"""解书音形码表 → 水杉辅助码（helpcode）方案文件导出。

数据流：
    dict/dictionary.txt（真源，路径取 config.DATA_FILE）
      → 本脚本（主码+副码字母粗映射为两位辅助码）
      → <水杉自定义辅助码目录>\\<方案名>.txt（每行「字=两位小写字母」）

转换规则见 help/水杉辅助码转换.md。
目标目录解析与 migrate_to_rime/rime_export.py 同一套纪律：
    --target 参数 > config.MSIME_DIR > 交互式询问（首次输入后写回 config.py）；
    产物原子写入（可回滚 .bak）、内容无变化则跳过。

用法：
    python agent_workspace\\msime_export.py                  # 首次询问目录并写回 config.py
    python agent_workspace\\msime_export.py --target <目录>  # 临时指定，不写回
    python agent_workspace\\msime_export.py --out dictionary_out.txt
"""

import argparse
import io
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

# ===== 路径基准 =====
# 本脚本位于 <仓库根>\agent_workspace\ 下；码表真源、合法编码字符集一律取仓库根
# config.py，与 Python 前端同源，不在本脚本另立常量。
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

try:
    import config
except ImportError as e:  # 脱离仓库单独拷贝本脚本时会触发
    sys.stderr.write(
        f"[FAIL] 无法导入仓库根 config.py（{e}）。\n"
        "本脚本必须放在 <仓库根>\\agent_workspace\\ 下运行。\n")
    raise SystemExit(1)

CONFIG_PATH = os.path.join(PROJECT_ROOT, "config.py")
SOURCE_SINGLE = config.DATA_FILE
VALID_CODE_CHARS = set(config.CODE_CHARS)

# 产物命名与方案显示名（水杉 README：`# name:` 注释须在首个非注释行之前）
DEFAULT_OUT_NAME = "jieshu.txt"
SCHEME_NAME = "解书音形"
SCHEME_NAME_EN = "Elucidative Chinese IME"

# 独体字主码（0-9）→ 两位占位辅助码：水杉侧的十个固定槽位，统一以 a 为前缀。
# 解书独体字没有副码，主码数字对应的构形类别（开/大/闭/称/竖/横/错/偏/复/奇）
# 在两位字母体系里没有可对齐的形码，故按固定表映射。
DIGIT_MAP = {
    "0": "ap",
    "1": "aq",
    "2": "aw",
    "3": "ae",
    "4": "ar",
    "5": "at",
    "6": "ay",
    "7": "au",
    "8": "ai",
    "9": "ao",
}

# 全部候选码都带点补（.F）时仍取末位候选的字。目前仅「屮」：
# 其两条编码 ck3c.i / ie45.c 都带点补，取末位得主码 5（独体构形），与人工判断一致。
# 保留理由：丢弃点补是仗着水杉自带繁体输出（打简体得上屏繁体），可「屮」不是繁体、
# 是罕见部首字，没有简体可借，一旦按「全点补即舍弃」处理就彻底打不出来。
ALL_DOT_KEEP_LAST = frozenset({"屮"})

_TWO_LETTER = re.compile(r"[a-z]{2}\Z")


class OperationError(Exception):
    """业务操作失败时抛出，携带用户可读的错误信息。"""


# ===== 源数据读取 =====

def read_source(path=SOURCE_SINGLE):
    """读单字真源，返回 [(字, [码, ...]), ...]，按字首现顺序合并多音/多码。

    格式校验与 rime_export._read_entries 同口径：缺编码列、词条含制表符、
    编码含 CODE_CHARS 之外字符、编码短于四码（音码 3 + 主码 1），一律报可读错误。
    """
    if not os.path.isfile(path):
        raise OperationError(f"码表真源不存在：{path}（检查 config.py 的 DATA_FILE）")

    order = []
    codes_of = {}
    with io.open(path, "r", encoding="utf-8-sig") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            parts = line.split(" ")
            word, codes = parts[0], parts[1:]
            if "\t" in word:
                raise OperationError(
                    f"单字表第 {lineno} 行词条含制表符，破坏列格式：{line!r}")
            if not codes or any(not c for c in codes):
                raise OperationError(f"单字表第 {lineno} 行缺少编码列：{line!r}")
            for code in codes:
                if len(code) < 4:
                    raise OperationError(
                        f"单字表第 {lineno} 行编码短于四码（音码3+主码1）：{line!r}")
                bad = sorted({c for c in code if c not in VALID_CODE_CHARS})
                if bad:
                    raise OperationError(
                        f"单字表第 {lineno} 行编码含 CODE_CHARS 之外的字符 "
                        f"{bad}：{line!r}")
            if word not in codes_of:
                codes_of[word] = []
                order.append(word)
            codes_of[word].extend(codes)
    if not order:
        raise OperationError(f"码表真源为空：{path}")
    return [(word, codes_of[word]) for word in order]


# ===== 转换核心 =====

def pick_remainder(word, codes):
    """从同一字的多条编码中选出用于辅助码的形码部分（编码第 4 位起）。

    选择顺序：唯一候选即取；否则在「不含点补」的候选里取最长，
    等长时优先不含 e，仍并列取首现。全部候选都带点补时返回 None
    （ALL_DOT_KEEP_LAST 中的字取末位候选）。
    """
    rems = []
    for code in codes:
        rem = code[3:]                       # 舍弃音码 ABC
        if rem not in rems:
            rems.append(rem)
    if len(rems) == 1:
        return rems[0]

    plain = [r for r in rems if "." not in r]
    if plain:
        longest = max(len(r) for r in plain)
        tied = [r for r in plain if len(r) == longest]
        # e 是副码兜底位（「空 > 别码 > 余字解析码 > e > ;」，部首表 e 行留空），
        # 带 e 的码不携带可推导的形信息；同长时优先取别码 / 余字解析码那条。
        no_e = [r for r in tied if "e" not in r]
        return (no_e or tied)[0]

    if word in ALL_DOT_KEEP_LAST:
        return rems[-1]
    return None


def to_helpcode(rem):
    """把形码部分折成两位小写辅助码；无法折算返回 None。

    步骤：舍弃点补（.F）及其后字符 → 首位为数字则查 DIGIT_MAP →
    分号（未简字副码）改写为 e → 单字符补 a 至两位。
    """
    if rem is None:
        return None
    if "." in rem:
        rem = rem.split(".", 1)[0]
    if rem and rem[0].isdigit():
        return DIGIT_MAP.get(rem[0])
    rem = rem.replace(";", "e")
    if len(rem) == 1:
        rem += "a"
    return rem if _TWO_LETTER.match(rem) else None


def convert(pairs):
    """返回 (entries, dropped)。entries=[(字, 两位码)] 保持真源行序；
    dropped=全部候选带点补而被舍弃的字（繁体/异体为主）。"""
    entries, dropped, invalid = [], [], []
    for word, codes in pairs:
        rem = pick_remainder(word, codes)
        if rem is None:
            dropped.append(word)
            continue
        helpcode = to_helpcode(rem)
        if helpcode is None:
            invalid.append((word, codes))
            continue
        entries.append((word, helpcode))
    if invalid:
        detail = "\n  ".join(f"{w} {cs}" for w, cs in invalid[:10])
        raise OperationError(
            "以下字的编码无法折算为两位小写辅助码（源数据超出当前规则）：\n  "
            + detail)
    return entries, dropped


def render(entries):
    """生成方案文件正文（UTF-8 + LF；注释头供水杉读取方案显示名）。"""
    lines = [
        f"# name: {SCHEME_NAME}",
        f"# name_en: {SCHEME_NAME_EN}",
        "# 由 agent_workspace/msime_export.py 自解书码表真源生成，请勿手改；"
        "规则见 help/水杉辅助码转换.md",
    ]
    lines.extend(f"{word}={code}" for word, code in entries)
    return "\n".join(lines) + "\n"


def parse_output(text):
    """解析已存在的方案文件为 {字: 两位码}（跳过注释与空行，只取前两位）。"""
    table = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        word, _, code = line.partition("=")
        table[word] = code[:2]
    return table


def diff_summary(old_text, new_text):
    """与已存在产物对比：新增/删除/变更（按字比对，忽略顺序）。"""
    if old_text is None:
        return "（首次导出，无旧版可比）"
    old, new = parse_output(old_text), parse_output(new_text)
    added = [w for w in new if w not in old]
    removed = [w for w in old if w not in new]
    changed = [w for w in new if w in old and old[w] != new[w]]

    def head(words, fmt):
        text = " ".join(fmt(w) for w in words[:8])
        return text + (" …" if len(words) > 8 else "")

    parts = [f"保持不变 {len(new) - len(added) - len(changed)}，新增 {len(added)}，"
             f"删除 {len(removed)}，改码 {len(changed)}"]
    if added:
        parts.append("新增例：" + head(added, lambda w: w))
    if removed:
        parts.append("删除例：" + head(removed, lambda w: f"{w}(原{old[w]})"))
    if changed:
        parts.append("改码例：" + " ".join(
            f"{w} {old[w]}→{new[w]}" for w in changed[:8])
            + (" …" if len(changed) > 8 else ""))
    return "；".join(parts)


# ===== 导出（与 rime_export.py 同纪律）=====

def atomic_write(filepath, content, backup=False, newline=""):
    """原子写入：先写同目录临时文件再 os.replace；backup=True 时轮转 .bak。"""
    target = Path(filepath)
    if backup and target.exists():
        shutil.copy2(str(target), str(target) + ".bak")

    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent), prefix=f".{target.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline=newline) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_path, str(target))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _clean_path_input(text):
    """清洗路径输入：去 BOM、首尾空白与包裹引号。"""
    s = (text or "").strip().lstrip("\ufeff").strip()
    while len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    return s


def _validate_dir_path(path, source_hint):
    """Windows 目录路径合法性检查：非法字符/控制字符即报可读错误（不查存在性）。"""
    bad = {c for c in path if c in '<>"|?*' or ord(c) < 32}
    for i, c in enumerate(path):
        if c == ":" and not (i == 1 and path[0].isalpha()):
            bad.add(":")
            break
    if bad:
        raise OperationError(
            f"{source_hint}的路径含非法字符 {sorted(bad)}：{path!r}\n"
            "（多半是复制粘贴时混入了乱码，请重新输入或修正 config.py 的 MSIME_DIR。）")
    return path


def _persist_dir_in_config(target_dir):
    """把目标目录写回 config.py 的 MSIME_DIR 行（只改右值，原子写）。"""
    with io.open(CONFIG_PATH, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    literal = "MSIME_DIR = {!r}".format(target_dir)
    new_text, n = re.subn(
        r"(?m)^MSIME_DIR[ \t]*=[^\r\n]*(\r?\n?)",
        lambda m: literal + m.group(1), text, count=1)
    if n != 1:
        raise OperationError(
            "config.py 中未找到 MSIME_DIR 配置行，无法写回。"
            f"请手动添加一行：{literal}")
    atomic_write(CONFIG_PATH, new_text, newline="")


def resolve_target_dir(cli_target=None):
    """确定水杉自定义辅助码目录：--target > config.MSIME_DIR > 交互式询问。"""
    if cli_target:
        cleaned = _clean_path_input(cli_target)
        if not cleaned:
            raise OperationError("--target 传了空值；留空请改用交互模式（去掉 --target）。")
        return os.path.abspath(_validate_dir_path(cleaned, "--target 参数"))

    cached = _clean_path_input(getattr(config, "MSIME_DIR", ""))
    if cached:
        _validate_dir_path(cached, "config.py MSIME_DIR")
        print(f"[TARGET] 水杉辅助码目录：{cached}（来自 config.py 的 MSIME_DIR）")
        return os.path.abspath(cached)

    print("首次运行：请粘贴水杉「自定义辅助码」目录的绝对路径。")
    print("（水杉设置窗口「辅助码」页所用的自定义方案目录，通常为 <水杉安装目录>\\helpcodes\\custom。）")
    try:
        answer = _clean_path_input(input("目录路径（留空则放弃导出）："))
    except EOFError:
        answer = ""
    if not answer:
        raise OperationError("未输入路径，已放弃导出。")
    _validate_dir_path(answer, "输入的")
    target = os.path.abspath(os.path.expanduser(answer))
    _persist_dir_in_config(target)
    print("[SAVE] 路径已写入 config.py 的 MSIME_DIR，下次运行无需再输。")
    return target


def _write_if_changed(out_path, content, count):
    old = None
    if os.path.isfile(out_path):
        with io.open(out_path, "r", encoding="utf-8-sig") as f:
            old = f.read()
        if old == content:
            print(f"[SKIP] {os.path.basename(out_path)} 无变化（{count} 条）")
            return
    atomic_write(out_path, content, backup=True)
    print(f"[OK] {os.path.basename(out_path)} 写出 {count} 条 -> {out_path}")
    print(f"     {diff_summary(old, content)}")


def run(target_dir, out_name=DEFAULT_OUT_NAME):
    pairs = read_source(SOURCE_SINGLE)
    entries, dropped = convert(pairs)
    content = render(entries)

    print(f"[SRC] 码表真源：{SOURCE_SINGLE}")
    print(f"[TGT] 辅助码目录：{target_dir}")
    print(f"[CHECK] 真源 {len(pairs)} 字 / {sum(len(c) for _, c in pairs)} 码"
          f" → 输出 {len(entries)} 字，舍弃 {len(dropped)} 字")
    if dropped:
        head = " ".join(dropped[:20]) + (" …" if len(dropped) > 20 else "")
        print(f"[WARN] 舍弃（候选码全部带点补，按规则不参与辅助码）：{head}")

    os.makedirs(target_dir, exist_ok=True)
    out_path = os.path.join(target_dir, out_name)
    _write_if_changed(out_path, content, len(entries))

    legacy = os.path.join(target_dir, "dictionary_out.txt")
    if out_name != "dictionary_out.txt" and os.path.isfile(legacy):
        print("[HINT] 目录内还有旧产物 dictionary_out.txt（粗方案输出，无名称注释）。"
              "若要沿用旧文件名，加 --out dictionary_out.txt 重跑。")
    print("[HINT] 水杉设置窗口「辅助码」页点「刷新方案」后即可选中该方案；"
          "改的是正在使用的方案时，需切换一次方案或重启输入法。")
    return out_path


def main():
    parser = argparse.ArgumentParser(
        description="导出解书音形码表为水杉自定义辅助码方案（每行「字=两位小写字母」；"
                    "规则见 help/水杉辅助码转换.md）")
    parser.add_argument("--target", default=None,
                        help="水杉自定义辅助码目录（*.txt 所在目录）；缺省用 config.py 的 "
                             "MSIME_DIR，为空时交互式询问并写回")
    parser.add_argument("--out", default=DEFAULT_OUT_NAME,
                        help=f"产物文件名（默认 {DEFAULT_OUT_NAME}；改名等于换方案）")
    args = parser.parse_args()
    try:
        run(target_dir=resolve_target_dir(args.target), out_name=args.out)
    except OperationError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1
    try:
        if sys.stdin.isatty():
            input("回车以退出...")
    except EOFError:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
#（注：内容由AI生成）
