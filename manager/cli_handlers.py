import os
import sys
import shutil
import tempfile
import webbrowser
from pathlib import Path
from .dictionary import ensure_data_file, query_chars, load_dictionary
from .batch_entry import batch_add_entries
from .single_entry import single_add_entry, modify_entry
from .abc_analyzer import interactive_mode, analyze_abc_zone
from .file_processor import main_menu, sort_file_by_second_part, process_file, build_web_data
from .ciyu_ops import ciyumain, get_existing_word_info, add_to_ciyu, has_dot_in_codes
from .ciyu_ops import append_dot_to_code, generate_default_codes_for_word, check_code_exists
from .guess_game import bmmamain
from .rationale_add import main as rationale_main, load_rationale, load_entries, save_rationale
from config import CIYU_FILE, DATA_FILE

class OperationError(Exception):
    """业务操作失败时抛出，携带用户可读的错误信息。"""
    pass


def atomic_write(filepath, content, backup=False):
    """原子写入文件，支持备份和临时文件安全替换。"""
    target = Path(filepath)
    dir_ = target.parent
    if backup and target.exists():
        bak = target.with_suffix(target.suffix + '.bak')
        shutil.copy2(str(target), str(bak))

    fd, tmp_path = tempfile.mkstemp(
        dir=str(dir_),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
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


def safe_input(prompt=""):
    """安全的输入函数，处理 EOFError。"""
    try:
        return input(prompt)
    except EOFError:
        print("\n检测到输入结束（EOF），程序退出。")
        sys.exit(0)

def open_web_page(page_name: str):
    """打开帮助目录下的指定网页。"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 从 manager/ 回到项目根
    web_dir = os.path.join(base_dir, 'help', 'webpage')
    path = os.path.join(web_dir, page_name)
    if os.path.exists(path):
        webbrowser.open('file://' + os.path.abspath(path))
        print(f"正在打开：{path}")
    else:
        raise OperationError(f"网页文件不存在：{path}")
def handle_show(args):
    """--show 只查不写模式"""
    if not args.target:
        raise OperationError("--show 模式下请提供要查询的词语/汉字（作为位置参数）。")

    rationale = None
    if args.rationale:
        rationale = load_rationale()

    for word in args.target:
        if args.ciyu:
            exists, codes = get_existing_word_info(word)
            if exists:
                print(f"{word} {codes}")
            else:
                print(f"{word} 暂未录入")
        elif args.rationale:
            if word in rationale:
                print(f"{word} {rationale[word]}")
            else:
                print(f"{word} 暂无理据")


def handle_query(args):
    """--query 查询字码"""
    chars = "".join(args.query)
    result, missing = query_chars(chars)
    print(result)
    if missing:
        print(f"未录入汉字：{''.join(missing)}")


def handle_sort(args):
    """--sort 整理码表"""
    try:
        single, phrase, web_chars, web_phrases = main_menu()
        print(f"整理完成！码表条目：{single}+{phrase}")
    except EOFError:
        raise OperationError("整理码表功能需要终端交互，无法在非终端（如管道）环境下执行。")


def handle_analyze(args):
    """--analyze 分析音区"""
    if args.analyze == "__interactive__":
        interactive_mode()
    else:
        abc = args.analyze.lower()
        if len(abc) < 2 or not (abc[0].isalpha() and abc[-1].isdigit()):
            raise OperationError(f"音码格式错误：{args.analyze}（应为如 bc1 的格式）")
        analyze_abc_zone(abc)


def handle_rationale(args):
    """--rationale 添加理据"""
    if not args.char or not args.text:
        raise OperationError("--rationale 需要配合 --char 和 --text 使用，无参数运行进入交互模式。")

    entries = load_entries()
    rationale = load_rationale()
    char_map = {}
    for ch, code in entries:
        char_map.setdefault(ch, []).append(code)

    if args.char not in char_map:
        raise OperationError(f"码表中未找到「{args.char}」")

    val = args.text.replace('\\n', '\n')
    rationale[args.char] = val
    if save_rationale(rationale):
        print(f"[OK] {args.char} → {val.replace(chr(10), ' / ')}")
    build_web_data()


def handle_add(args):
    """--add 添加单字"""
    if not args.char or not args.code:
        raise OperationError("--add 需要配合 --char 和 --code 使用，无参数运行进入交互模式。")
    if len(args.char) != 1:
        raise OperationError("--char 只接受单个汉字")

    code = args.code
    if len(code) < 4:
        raise OperationError("编码过短，至少4位")

    _, full_dict = load_dictionary()
    abc_code = code[:3]
    if abc_code in full_dict:
        for h, c in full_dict[abc_code]:
            if c == code and h != args.char:
                raise OperationError(f"重码冲突：编码 '{code}' 已被 '{h}' 占用")

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    lines.append(f"{args.char} {code}\n")

    atomic_write(DATA_FILE, ''.join(lines))
    process_file(DATA_FILE, DATA_FILE)
    print(f"[OK] {args.char} {code}")


def handle_modify(args):
    """--modify 编辑修改"""
    if not args.code or not args.new_code:
        raise OperationError("--modify 需要配合 --code 和 --new-code 使用，无参数运行进入交互模式。")

    old_code = args.code
    if len(old_code) < 4:
        raise OperationError("旧编码过短，至少4位")

    _, full_dict = load_dictionary()
    found_char = None
    for entries in full_dict.values():
        for h, c in entries:
            if c == old_code:
                found_char = h
                break
        if found_char:
            break

    if not found_char:
        raise OperationError(f"旧编码 '{old_code}' 不存在于码表中")

    new_code = args.new_code

    if new_code == 'x':
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        new_lines = [
            line for line in lines
            if not (line.strip().split(' ', 1) == [found_char, old_code])
        ]
        atomic_write(DATA_FILE, ''.join(new_lines))
        process_file(DATA_FILE, DATA_FILE)
        print(f"[OK] 已删除 {found_char} {old_code}")
        return

    if len(new_code) < 4:
        raise OperationError("新编码过短，至少4位")

    abc_code = new_code[:3]
    if abc_code in full_dict:
        for h, c in full_dict[abc_code]:
            if c == new_code and h != found_char:
                raise OperationError(f"重码冲突：编码 '{new_code}' 已被 '{h}' 占用")

    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    new_lines = []
    for line in lines:
        parts = line.strip().split(' ', 1)
        if len(parts) == 2 and parts[0] == found_char and parts[1] == old_code:
            new_lines.append(f"{found_char} {new_code}\n")
        else:
            new_lines.append(line)

    atomic_write(DATA_FILE, ''.join(new_lines))
    process_file(DATA_FILE, DATA_FILE)
    print(f"[OK] {found_char} {old_code} → {new_code}")


def handle_ciyu(args):
    """--ciyu 添加词语"""
    if not args.char:
        raise OperationError("--ciyu 需要配合 --char 提供词语")

    word = args.char

    if len(word) == 1:
        if not args.code:
            raise OperationError("单字词语（通用符号）需要配合 --code 指定编码")
        codes = [args.code]
    else:
        code_str, missing = query_chars(word)
        if missing:
            raise OperationError(f"组成字未录入：{''.join(missing)}")
        codes_per_char = code_str.split()

        if len(codes_per_char) != len(word):
            if not args.code:
                raise OperationError(
                    f"词语 '{word}' 含非汉字字符，无法自动生成编码，"
                    f"请配合 --code 指定自定义编码")
            codes = args.code.split()
        else:
            selected_codes = []
            for cs in codes_per_char:
                cl = cs.split('/')
                if cl[0] == '--':
                    raise OperationError("组成字编码缺失")
                selected_codes.append(cl[0])

            if args.code:
                codes = args.code.split()
            else:
                if len(word) == 2:
                    codes = [selected_codes[0][:2] + selected_codes[1][:2]]
                else:
                    default_str = generate_default_codes_for_word(word, selected_codes)
                    codes = default_str.split()
                if has_dot_in_codes(*selected_codes):
                    codes = [append_dot_to_code(c) for c in codes]

    for code in codes:
        conflict_line = check_code_exists(code)
        if conflict_line:
            conflict_word = conflict_line.split()[0] if conflict_line.strip() else ""
            if conflict_word == word:
                continue
            raise OperationError(f"词语重码冲突：编码 '{code}' 已被 '{conflict_line}' 占用")

    add_to_ciyu(word, codes, overwrite=True)
    sort_file_by_second_part(CIYU_FILE, CIYU_FILE)
    print(f"[OK] {word} {' '.join(codes)}")
