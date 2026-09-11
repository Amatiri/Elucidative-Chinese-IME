"""
rime_export.py —— 把解书码表真源导出为 RIME 方案文件（实现与部署见 README.md）

码表真源路径直接取自仓库根 config.py（DATA_FILE / CIYU_FILE），无需手动指定。
导出目标为 RIME 用户资料夹，按以下优先级确定：
  --target 参数 > config.py 的 RIME_USER_DIR > 交互式询问（首次输入后写回 config.py）。

用法：
  python migrate_to_rime\\rime_export.py                  # 首次会询问 RIME 用户资料夹路径
  python migrate_to_rime\\rime_export.py --single         # 只导出单字表
  python migrate_to_rime\\rime_export.py --target <路径>  # 临时指定 RIME 用户资料夹（不写回）
  python migrate_to_rime\\rime_export.py --skip-config     # 只动码表与 Lua，不碰方案/皮肤配置
"""

import argparse
import io
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

# ===== 路径基准 =====
# 本脚本位于 <仓库根>\migrate_to_rime\ 下；码表真源、编码字符集一律从仓库根
# config.py 获取，与 Python 前端同源，不存在第二套常量。
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CONFIG_PATH = os.path.join(REPO_ROOT, "config.py")

if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)
try:
    import config
except ImportError as e:  # 脱离仓库单独拷贝本脚本时会触发
    sys.stderr.write(
        f"[FAIL] 无法导入仓库根 config.py（{e}）。\n"
        "本脚本必须配合解书音形仓库使用，放在 <仓库根>\\migrate_to_rime\\ 下运行。\n")
    raise SystemExit(1)

SOURCE_SINGLE = config.DATA_FILE   # <仓库根>\dict\dictionary.txt
SOURCE_CIYU = config.CIYU_FILE     # <仓库根>\dict\ciyu.txt

# 编码字符集（config.CODE_CHARS，与前端严格同源）
CODE_CHARS = config.CODE_CHARS

# Lua 运行期文件：源在 migrate_to_rime\ 本目录（与脚本同住），目标在 <user_data>\lua\
LUA_MODULE_SRC = os.path.join(SCRIPT_DIR, "jieshu_query.lua")
LUA_FILTER_SRC = os.path.join(SCRIPT_DIR, "jieshu_drop_native.lua")
LUA_GATE_SRC = os.path.join(SCRIPT_DIR, "jieshu_gate.lua")
LUA_NAV_SRC = os.path.join(SCRIPT_DIR, "jieshu_nav.lua")
LUA_TARGET_MODULE = os.path.join("lua", "jieshu_query.lua")
LUA_TARGET_FILTER = os.path.join("lua", "jieshu_drop_native.lua")
LUA_TARGET_GATE = os.path.join("lua", "jieshu_gate.lua")
LUA_TARGET_NAV = os.path.join("lua", "jieshu_nav.lua")
LUA_TARGET_SINGLE = os.path.join("lua", "data", "jieshu_single.txt")
LUA_TARGET_CIYU = os.path.join("lua", "data", "jieshu_ciyu.txt")

# 配置文件：真源在 migrate_to_rime\ 本目录，同步到 <user_data> 根（与 Lua 同源同策）。
# (源绝对路径, 目标相对 <user_data> 的相对路径)
#   jieshu.schema.yaml   输入方案（engine/speller/translator/filters/recognizer）
#   weasel.custom.yaml   小狼毫皮肤：布局 + 字体 + 两套「宣纸」配色
CONFIG_SYNC_FILES = [
    (os.path.join(SCRIPT_DIR, "jieshu.schema.yaml"), "jieshu.schema.yaml"),
    (os.path.join(SCRIPT_DIR, "weasel.custom.yaml"), "weasel.custom.yaml"),
]

SINGLE_DICT_NAME = "jieshu.dict.yaml"
CIYU_TABLE_NAME = "jieshu_ciyu"

_VALID_CODE = set(CODE_CHARS)


class OperationError(Exception):
    """业务操作失败时抛出，携带用户可读的错误信息。"""
    pass


def atomic_write(filepath, content, backup=False, newline=None):
    """原子写入文件，支持备份和临时文件安全替换。

    newline: 传给文本模式的换行处理；RIME 词典等要求 UNIX 换行(LF)的
    产物传 ''（内容按字面写入，不随平台转换）。
    """
    target = Path(filepath)
    dir_ = target.parent
    if backup and target.exists():
        bak = target.with_suffix(target.suffix + ".bak")
        shutil.copy2(str(target), str(bak))

    fd, tmp_path = tempfile.mkstemp(
        dir=str(dir_),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
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


def resolve_source_dir():
    """码表真源目录：直接取仓库根 config.py 的 DATA_FILE / CIYU_FILE 所在目录。

    与前端共用同一份路径配置，改 config.py 即改真源位置，本脚本不再单独维护
    路径候选表。文件缺失或不在同一目录即报错拒绝导出。
    """
    single, ciyu = os.path.abspath(SOURCE_SINGLE), os.path.abspath(SOURCE_CIYU)
    if os.path.dirname(single) != os.path.dirname(ciyu):
        raise OperationError(
            "config.py 的 DATA_FILE 与 CIYU_FILE 不在同一 dict 目录，"
            f"请检查配置：\n  {single}\n  {ciyu}")
    missing = [p for p in (single, ciyu) if not os.path.isfile(p)]
    if missing:
        raise OperationError(
            "config.py 指向的码表真源不存在：\n  " + "\n  ".join(missing)
            + "\n请修正 config.py 的 DATA_FILE / CIYU_FILE 后重试。")
    return os.path.dirname(single)


def _persist_rime_dir_in_config(rime_dir):
    """把用户输入的 RIME 用户资料夹路径写回 config.py 的 RIME_USER_DIR 行。

    仅替换 `RIME_USER_DIR = ...` 这一行的右值，其余内容原样保留（原子写）。
    """
    with io.open(CONFIG_PATH, "r", encoding="utf-8", newline="") as f:
        text = f.read()
    literal = "RIME_USER_DIR = {!r}".format(rime_dir)
    new_text, n = re.subn(
        r"(?m)^RIME_USER_DIR[ \t]*=[^\r\n]*(\r?\n?)",
        lambda m: literal + m.group(1), text, count=1)
    if n != 1:
        raise OperationError(
            "config.py 中未找到 RIME_USER_DIR 配置行，无法写回。"
            f"请手动在 config.py 中添加一行：{literal}")
    atomic_write(CONFIG_PATH, new_text, newline="")


def _clean_path_input(text):
    """清洗用户输入/缓存的路径字符串：去 BOM、首尾空白与包裹引号。"""
    s = (text or "").strip().lstrip("\ufeff").strip()
    while len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    return s


def _validate_dir_path(path, source_hint):
    """Windows 目录路径合法性检查：含非法字符/控制字符即报可读错误。

    只挡语法问题，不检查存在性（资料夹可能尚待创建，run() 会 makedirs）。
    冒号仅允许出现在盘符位（第 2 字符且首字符为字母）。
    """
    bad = sorted({c for c in path if c in '<>"|?*' or ord(c) < 32})
    for i, c in enumerate(path):
        if c == ":" and not (i == 1 and path[0].isalpha()):
            bad.append(":")
            break
    bad = sorted(set(bad))
    if bad:
        raise OperationError(
            f"{source_hint}的路径含非法字符 {bad}：{path!r}\n"
            "（多半是复制粘贴时混入了乱码。请重新输入，或修正 config.py 的 "
            "RIME_USER_DIR。）")
    return path


def resolve_target_dir(cli_target=None):
    """确定导出目标（RIME 用户资料夹）。

    优先级：--target > config.RIME_USER_DIR > 交互式询问。
    - --target：本次使用，不写回 config.py；
    - config.RIME_USER_DIR 非空：直接使用；
    - 否则交互式询问：输入为空即放弃迁移（报错退出，不做任何写操作）；
      输入成功后写回 config.py，并提醒更换资料夹时需同步修改。
    """
    if cli_target:
        cleaned = _clean_path_input(cli_target)
        if not cleaned:
            raise OperationError("--target 传了空值。留空请改用交互模式（去掉 --target）。")
        return os.path.abspath(_validate_dir_path(cleaned, "--target 参数"))
    cached = _clean_path_input(getattr(config, "RIME_USER_DIR", ""))
    if cached:
        _validate_dir_path(cached, "config.py RIME_USER_DIR")
        print(f"[TARGET] RIME 用户资料夹：{cached}（来自 config.py 的 RIME_USER_DIR）")
        return os.path.abspath(cached)
    print("首次运行：请粘贴你的 RIME 用户资料夹绝对路径。")
    print("（小狼毫：托盘菜单「用户资料夹」打开的目录；其他发行版见其文档。）")
    try:
        answer = _clean_path_input(input("RIME 用户资料夹路径（留空则放弃迁移）："))
    except EOFError:
        answer = ""
    if not answer:
        raise OperationError("未输入路径，已放弃迁移。")
    _validate_dir_path(answer, "输入的")
    target = os.path.abspath(os.path.expanduser(answer))
    _persist_rime_dir_in_config(target)
    print("[SAVE] 路径已写入 config.py 的 RIME_USER_DIR，下次运行无需再输。")
    print(f"[HINT] 若以后更换了 RIME 用户资料夹，请同步修改 config.py 中 "
          f"RIME_USER_DIR 一行，否则导出仍会写入旧路径：{target}")
    return target


def _read_entries(path, kind):
    """读取真源，返回 [(词条, 编码), ...]（一词多码逐码展开）；格式异常直接抛。"""
    if not os.path.isfile(path):
        raise OperationError(f"真源文件不存在：{path}")
    entries = []
    with io.open(path, "r", encoding="utf-8-sig") as f:
        for lineno, raw in enumerate(f, 1):
            line = raw.strip()
            if not line:
                continue
            parts = line.split(" ")
            word, codes = parts[0], parts[1:]
            if "\t" in word:
                raise OperationError(
                    f"{kind} 第 {lineno} 行词条含制表符，破坏列格式：{line!r}")
            if not codes or any(not c for c in codes):
                raise OperationError(
                    f"{kind} 第 {lineno} 行缺少编码列：{line!r}")
            for code in codes:
                bad = sorted({c for c in code if c not in _VALID_CODE})
                if bad:
                    raise OperationError(
                        f"{kind} 第 {lineno} 行编码含 CODE_CHARS 之外的字符 "
                        f"{bad}：{line!r}")
                if code[0] == "'":
                    raise OperationError(
                        f"{kind} 第 {lineno} 行编码以分段符 ' 开头，与 "
                        f"speller/delimiter 冲突：{line!r}")
                entries.append((word, code))
    return entries


def _dedup_keep_order(entries):
    """(词条,码) 去重，保持首现顺序（真源理论无重复，校验兜底）。"""
    seen, uniq = set(), []
    for entry in entries:
        if entry not in seen:
            seen.add(entry)
            uniq.append(entry)
    return uniq


def _header(name, version):
    lines = [
        "# Rime dictionary",
        "# encoding: utf-8",
        "# 本文件由 migrate_to_rime/rime_export.py 从解书码表真源生成，请勿手改；",
        "# 修改真源后重新导出。源：仓库 dict/ 目录，实现说明见 migrate_to_rime/README.md。",
        "---",
        f"name: {name}",
        f'version: "{version}"',
        "sort: by_weight",
        "use_preset_vocabulary: false",
        "columns: [ text, code, weight, comment ]",
        "...",
        "",
    ]
    return "\n".join(lines)


def _render(singles, ciyu_entries, name, version):
    """第七轮定案：前缀匹配转精确查表（补全通道关闭）。

    条目构成：
      1) 单字全码：不⇥bu44⇥w⇥（注释空）
      2) 单字可见真前缀：不⇥bu4⇥w⇥4、不⇥b⇥w⇥u44 …… 注释=余码，
         前缀集复刻 query_by_prefix 的补码隐藏规则（含点码短前缀不可见）；
         (字,前缀)去重保行序最小；与全码重复的键跳过。
      3) 词全码：测试⇥ceu⇥w⇥ —— 补全已关，词只可能被自身全码精确命中，
         天然满足「优先上词=完全匹配优先、不被前缀捕获」。
    权重 = q × 10^len × (0.01 if len==1 else 1)，q ∈ (0,1] 为"概率位"：
      - 字段 q = (base-i)/(2·base) ≤ 0.5，词字段 q = (2·base-j)/(2·base) > 0.5
        → 同码页/同输入下词恒压字；类内 q 随逆源行序 → 页内候选序 == 真源行序；
      - q ≤ 1 是关键：librime 句构 DP 对链按权重连乘打分，任何"更细切分"
        都多乘一个 ≤1 的因子 → 恒不赢粗切分（否则 rank>1 时永远切碎，
        yi+ge 被 yi+g+e 压过）；
      - len==1 页罚 10⁻²：把完整音节拆成两个 1 字节页（如 ce→c+e 类）再降一档。
    """
    N, M = len(singles), len(ciyu_entries)
    base = max(N + M, 2)
    full_keys = set(singles)
    lines = []
    for i, (word, code) in enumerate(singles):
        w = (base - i) / (2 * base) * 10 ** len(code)
        lines.append(f"{word}\t{code}\t{w:.8f}\t")

    def _visible_prefixes(code):
        """复刻 query_by_prefix 的补码隐藏规则：
        点在前 6 字符内的码，短前缀不可见（须输入含点、或恰好打完点前词干
        且词干满足 [len==4 且第4位数字] / [len>5 且点在第6位] 之一）。"""
        dot = code.find(".")
        out = []
        for L in range(1, len(code)):
            if dot != -1 and dot < 6 and L <= dot:
                stem_ok = ((dot == 4 and code[3].isdigit())
                           or (dot == 5 and len(code) > 5))
                if not (L == dot and stem_ok):
                    continue
            out.append(code[:L])
        return out

    best = {}   # (字,前缀) -> 最小行号 i
    for i, (word, code) in enumerate(singles):
        for prefix in _visible_prefixes(code):
            key = (word, prefix)
            if key in full_keys:
                continue
            if key not in best or i < best[key]:
                best[key] = i
    for (word, prefix), i in sorted(best.items(), key=lambda kv: (kv[0][1], kv[1])):
        rest = singles[i][1][len(prefix):]
        w = (base - i) / (2 * base) * 10 ** len(prefix)
        if len(prefix) == 1:
            w *= 0.01
        lines.append(f"{word}\t{prefix}\t{w:.8f}\t{rest}")
    for j, (word, code) in enumerate(ciyu_entries):
        w = (2 * base - j) / (2 * base) * 10 ** len(code)
        lines.append(f"{word}\t{code}\t{w:.8f}\t")
    body = _header(name, version) + "\n".join(lines) + "\n"
    counts = (len(singles), len(lines) - len(singles) - len(ciyu_entries),
              len(ciyu_entries))
    return body, counts


def _strip_header(text):
    idx = text.find("\n...\n")
    if idx < 0:
        return []
    return [ln for ln in text[idx + 5:].splitlines() if ln.strip()]


def _diff_summary(old_text, new_text):
    """与已存在产物对比，打印新增/删除/变更摘要。"""
    if old_text is None:
        return "（首次导出，无旧版可比）"
    def key_set(text):
        # 键 = 词条+编码（忽略权重列，权重随条数全局重排属正常波动）
        return {
            "\t".join(ln.split("\t")[:2])
            for ln in _strip_header(text) if "\t" in ln
        }
    old_set, new_set = key_set(old_text), key_set(new_text)
    added = len(new_set - old_set)
    removed = len(old_set - new_set)
    same = len(new_set & old_set)
    return f"条目对比(不计权重)：保持不变 {same}，新增 {added}，删除 {removed}"


def _write_if_changed(out_path, content, count):
    old = None
    if os.path.isfile(out_path):
        with io.open(out_path, "r", encoding="utf-8") as f:
            old = f.read()
        if old == content:
            print(f"[SKIP] {os.path.basename(out_path)} 无变化（{count} 条）")
            return
    atomic_write(out_path, content, backup=True, newline="")
    print(f"[OK] {os.path.basename(out_path)} 写出 {count} 条 -> {out_path}")
    print(f"     {_diff_summary(old, content)}")


def _sync_lua_runtime(target_dir):
    """真源与 Lua 查询模块逐字节同步到 <user_data>/lua/，
    供 jieshu_query.lua 运行期读取。字节级拷贝 = 与 Python 前端共用同一份数据，
    不存在第二真源；内容无变化则跳过（atomic_write 自带备份轮转）。"""
    import filecmp
    pairs = [
        (LUA_MODULE_SRC, os.path.join(target_dir, LUA_TARGET_MODULE)),
        (LUA_FILTER_SRC, os.path.join(target_dir, LUA_TARGET_FILTER)),
        (LUA_GATE_SRC, os.path.join(target_dir, LUA_TARGET_GATE)),
        (LUA_NAV_SRC, os.path.join(target_dir, LUA_TARGET_NAV)),
        (SOURCE_SINGLE, os.path.join(target_dir, LUA_TARGET_SINGLE)),
        (SOURCE_CIYU, os.path.join(target_dir, LUA_TARGET_CIYU)),
    ]
    for src, dst in pairs:
        if not os.path.isfile(src):
            raise OperationError(f"lua 运行期源缺失: {src}")
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.isfile(dst) and filecmp.cmp(src, dst, shallow=False):
            print(f"[SKIP] {os.path.basename(dst)} 无变化")
            continue
        atomic_write(dst, io.open(src, encoding="utf-8", newline="").read(),
                     backup=True, newline="")
        print(f"[SYNC] {src} -> {dst}")


def _sync_config_files(target_dir):
    """把 migrate_to_rime\\ 下的方案与皮肤配置同步到 <user_data> 根。

    与 Lua 同一条纪律：migrate_to_rime\\ 是唯一真源，改那里再跑导出，不要直接改
    <user_data> 根的文件。内容无变化则跳过；有变化先备份 .bak 再替换。

    注意 weasel.custom.yaml 会被小狼毫「输入法设定」回写（补 customization: 头、
    重排缩进），回写后与真源逐字节不同 —— 下次导出会以真源为准覆盖回去，
    这是有意为之：GUI 里改的样式不进版本管理，一律回灌真源。
    """
    import filecmp
    for src, rel in CONFIG_SYNC_FILES:
        if not os.path.isfile(src):
            raise OperationError(f"配置文件真源缺失: {src}")
        dst = os.path.join(target_dir, rel)
        os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
        if os.path.isfile(dst) and filecmp.cmp(src, dst, shallow=False):
            print(f"[SKIP] {rel} 无变化")
            continue
        atomic_write(dst, io.open(src, encoding="utf-8", newline="").read(),
                     backup=True, newline="")
        print(f"[SYNC] {src} -> {dst}")


def run(target_dir, with_ciyu=True, version=None, with_config=True):
    """导出入口。target_dir 为 RIME 用户资料夹；version 缺省用当天日期。"""
    if version is None:
        import datetime
        version = datetime.date.today().strftime("%Y.%m%d")
    os.makedirs(target_dir, exist_ok=True)

    source_dir = resolve_source_dir()
    print(f"[SRC] 码表真源目录：{source_dir}")
    print(f"[TGT] RIME 用户资料夹：{target_dir}")

    singles = _dedup_keep_order(_read_entries(SOURCE_SINGLE, "单字表"))
    ciyu = (_dedup_keep_order(_read_entries(SOURCE_CIYU, "词表"))
            if with_ciyu else [])
    content, (full_n, prefix_n, ciyu_n) = _render(singles, ciyu, "jieshu", version)
    _write_if_changed(
        os.path.join(target_dir, SINGLE_DICT_NAME),
        content,
        f"字全码{full_n}+前缀{prefix_n}+词{ciyu_n}")
    _sync_lua_runtime(target_dir)
    if with_config:
        _sync_config_files(target_dir)
        print("[HINT] 配置已更新，请在小狼毫托盘执行「重新部署」后生效。")


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="导出解书码表为 RIME 词典与方案文件（见 migrate_to_rime/README.md）")
    parser.add_argument("--target", default=None,
                        help="RIME 用户资料夹绝对路径；缺省用 config.py 的 RIME_USER_DIR，"
                             "该值为空时交互式询问并写回 config.py")
    parser.add_argument("--single", action="store_true",
                        help="只导出单字词典（调试用）")
    parser.add_argument("--skip-config", action="store_true",
                        help="跳过 jieshu.schema.yaml / weasel.custom.yaml 同步"
                             "（只动码表与 Lua）")
    parser.add_argument("--version", default=None,
                        help="词典 version 字段（默认当天日期）")
    args = parser.parse_args(argv)
    try:
        run(target_dir=resolve_target_dir(args.target),
            with_ciyu=not args.single,
            version=args.version,
            with_config=not args.skip_config)
    except OperationError as e:
        print(f"[FAIL] {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
