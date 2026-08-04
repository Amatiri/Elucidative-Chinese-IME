import os
import sys
import subprocess
import argparse
import webbrowser
import tempfile
import shutil
from pathlib import Path

from manager.dictionary import ensure_data_file, query_chars
from manager.batch_entry import batch_add_entries
from manager.single_entry import single_add_entry, modify_entry
from manager.abc_analyzer import interactive_mode, analyze_abc_zone
from manager.file_processor import main_menu, sort_file_by_second_part
from manager.ciyu_ops import ciyumain
from manager.guess_game import bmmamain
from manager.rationale_add import main as rationale_main
from config import CIYU_FILE


# ==================== 异常定义 ====================

class OperationError(Exception):
    """业务操作失败时抛出，携带用户可读的错误信息。"""
    pass


# ==================== 原子写入工具 ====================

def atomic_write(filepath: str, content: str, backup: bool = True) -> None:
    """
    原子化写入文件：
    1. 可选：写入前保留 .bak 备份
    2. 写入同目录临时文件（确保同一文件系统）
    3. fsync 刷盘
    4. os.replace 原子替换
    """
    target = Path(filepath)
    dir_ = target.parent

    # 写入前保留一份 .bak（仅保留最近一份，避免膨胀）
    if backup and target.exists():
        bak = target.with_suffix(target.suffix + '.bak')
        shutil.copy2(str(target), str(bak))

    # 临时文件必须与目标在同一目录，否则 rename 可能跨文件系统失败
    fd, tmp_path = tempfile.mkstemp(
        dir=str(dir_),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())  # 确保数据落盘
        os.replace(tmp_path, str(target))  # 原子替换
    except BaseException:
        # 写入失败时清理临时文件
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ==================== 辅助函数 ====================

def safe_input(prompt=""):
    try:
        return input(prompt)
    except EOFError:
        print("\n检测到输入结束（EOF），程序退出。")
        sys.exit(0)


def run_input_method():
    try:
        ime_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ime.py")
        subprocess.Popen([sys.executable, ime_path])
    except Exception as e:
        print(f"启动输入法失败: {e}")


def show_menu():
    print("解书音形 - 管理程序")
    print("1.批量录入 ", end="")
    print("2.添加单字 ", end="")
    print("3.编辑修改 ")
    print("4.分析音区 ", end="")
    print("5.整理码表 ", end="")
    print("6.添加理据 ")
    print("7.查询字码 ", end="")
    print("8.添加词语 ", end="")
    print("9.猜测编码")


def open_web_page(page_name: str):
    """统一打开网页的辅助函数"""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    web_dir = os.path.join(base_dir, 'help', 'webpage')
    path = os.path.join(web_dir, page_name)
    if os.path.exists(path):
        webbrowser.open('file://' + os.path.abspath(path))
        print(f"正在打开：{path}")
    else:
        raise OperationError(f"网页文件不存在：{path}")


# ==================== 参数解析 ====================

def parse_args():
    parser = argparse.ArgumentParser(
        description="解书音形管理程序（支持交互与非交互模式）",
        epilog="无参数时进入交互菜单。"
    )
    parser.add_argument("--no-ime", action="store_true",
                        help="不启动输入法前端（默认启动）")
    parser.add_argument("--query", nargs="+", metavar="汉字",
                        help="查询一个或多个汉字的编码")
    parser.add_argument("--sort", action="store_true",
                        help="整理码表（排序、去重，自动处理所有码表文件）")
    parser.add_argument("--analyze", nargs="?", const="__interactive__", metavar="音码",
                        help="分析指定音区（如 bc1），不传参数则进入交互模式")
    parser.add_argument("--batch", action="store_true",
                        help="批量录入（暂不支持非交互）")
    parser.add_argument("--add", action="store_true",
                        help="添加单字（配合 --char 和 --code 使用）")
    parser.add_argument("--code", help="编码（配合 --add、--modify、--ciyu）")
    parser.add_argument("--new-code", help="新编码，或 x 表示删除（配合 --modify）")
    parser.add_argument("--modify", action="store_true",
                        help="编辑修改（配合 --code 和 --new-code 使用）")
    parser.add_argument("--rationale", action="store_true",
                        help="添加理据（配合 --char 和 --text 使用）")
    parser.add_argument("--char", help="汉字或词语（配合 --rationale、--add、--ciyu）")
    parser.add_argument("--text", help="理据文本，多音字换行用\\n（配合 --rationale）")
    parser.add_argument("--ciyu", action="store_true",
                        help="添加词语（配合 --char，可选 --code）")
    parser.add_argument("--guess", action="store_true",
                        help="猜测编码（暂不支持非交互）")
    parser.add_argument('--keymap', action='store_true',
                        help='打开键位图网页（help/webpage/键位图.html）')
    parser.add_argument('--query-web', action='store_true',
                        help='打开查询编码网页（help/webpage/index.html）')
    parser.add_argument("--show", "--display", action="store_true",
                        help="只查不写：配合 --ciyu 查词语码表、--rationale 查理据")
    parser.add_argument("target", nargs="*", metavar="词/字",
                        help="show 模式下要查询的词语/汉字（位置参数）")
    return parser.parse_args()


# ==================== 各子命令处理 ====================

def handle_show(args):
    """--show 只查不写模式"""
    from manager.ciyu_ops import get_existing_word_info
    from manager.rationale_add import load_rationale

    if not args.target:
        raise OperationError("--show 模式下请提供要查询的词语/汉字（作为位置参数）。")

    # rationale 数据只需加载一次，避免循环内重复 IO
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

    from manager.rationale_add import load_entries, load_rationale, save_rationale
    from manager.file_processor import build_web_data

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

    from manager.dictionary import load_dictionary
    from manager.file_processor import process_file
    from config import DATA_FILE

    # 重码检测：同音区已有其他汉字使用同一完整编码
    _, full_dict = load_dictionary()
    abc_code = code[:3]
    if abc_code in full_dict:
        for h, c in full_dict[abc_code]:
            if c == code and h != args.char:
                raise OperationError(f"重码冲突：编码 '{code}' 已被 '{h}' 占用")

    # 无冲突 → 读取现有内容 + 追加 → 原子写入
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

    from manager.dictionary import load_dictionary
    from manager.file_processor import process_file
    from config import DATA_FILE

    # 查找旧编码对应的汉字
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

    # 删除操作
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

    # 修改操作
    if len(new_code) < 4:
        raise OperationError("新编码过短，至少4位")

    # 重码检测：同音区已有其他汉字使用同一完整编码
    abc_code = new_code[:3]
    if abc_code in full_dict:
        for h, c in full_dict[abc_code]:
            if c == new_code and h != found_char:
                raise OperationError(f"重码冲突：编码 '{new_code}' 已被 '{h}' 占用")

    # 无冲突 → 替换 → 原子写入
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
                from manager.code_parser import generate_default_codes_for_word
                default_str = generate_default_codes_for_word(word, selected_codes)
                codes = default_str.split()

    # 重码检测
    from manager.code_parser import check_code_exists
    from manager.ciyu_ops import get_existing_word_info, add_to_ciyu
    from manager.file_processor import sort_file_by_second_part

    for code in codes:
        conflict_line = check_code_exists(code)
        if conflict_line:
            raise OperationError(f"词语重码冲突：编码 '{code}' 已被 '{conflict_line}' 占用")

    # 写入（覆盖同名词语旧记录）
    add_to_ciyu(word, codes, overwrite=True)
    sort_file_by_second_part(CIYU_FILE, CIYU_FILE)
    print(f"[OK] {word} {' '.join(codes)}")


# ==================== 交互菜单 ====================

def run_interactive_menu():
    """交互模式主循环"""
    if not sys.stdin.isatty():
        raise OperationError("交互模式需要终端（TTY），请使用子命令或重定向输入。")

    while True:
        show_menu()
        try:
            choice = safe_input("选项: ").strip()
            if choice == '1':
                batch_add_entries()
            elif choice == '2':
                single_add_entry()
            elif choice == '3':
                modify_entry()
            elif choice == '4':
                interactive_mode()
            elif choice == '5':
                single, phrase, web_chars, web_phrases = main_menu()
                print(f"整理完成！码表条目：{single}+{phrase}")
            elif choice == '6':
                rationale_main()
            elif choice == '7':
                while True:
                    a = safe_input("连续汉字：")
                    if a == "":
                        break
                    b, missing = query_chars(a)
                    print(b)
                    if missing:
                        print(f"未录入汉字：{''.join(missing)}")
            elif choice == '8':
                ciyumain()
            elif choice == '9':
                bmmamain()
            elif choice == '':
                print("感谢使用，再见！")
                break
            else:
                print("无效选项，请重新选择")
            print()
        except KeyboardInterrupt:
            print("\n\n程序被用户中断")
            break
        except Exception as e:
            print(f"程序运行出错: {str(e)}")


# ==================== 主入口 ====================

def main():
    args = parse_args()

    # ---------- show 模式守卫 ----------
    if args.target and not args.show:
        raise OperationError(
            "位置参数 'target' 是 --show 模式的查询目标，不能单独使用。\n"
            "  正确写法：python main.py --ciyu --show <词语>\n"
            "  正确写法：python main.py --rationale --show <字>"
        )

    if args.show:
        conflicts = []
        if args.ciyu and args.code:
            conflicts.append('--code')
        if args.rationale and args.text:
            conflicts.append('--text')
        if conflicts:
            raise OperationError(f"--show 只查不写，与 {', '.join(conflicts)} 互斥。")

    if args.show and args.char:
        raise OperationError(
            "show 模式下无需 --char，直接将词语/汉字作为位置参数即可。\n"
            "  示例：python main.py --ciyu --show 测试"
        )

    if args.show and not (args.ciyu or args.rationale):
        raise OperationError("--show 必须配合 --ciyu 或 --rationale 使用。")

    # ---------- 网页打开 ----------
    WEB_PAGES = {
        'keymap': '键位图.html',
        'query_web': 'index.html',
    }
    for flag, filename in WEB_PAGES.items():
        if getattr(args, flag):
            open_web_page(filename)
    if args.keymap or args.query_web:
        return

    ensure_data_file()

    # ---------- 子命令分发 ----------
    if args.show:
        handle_show(args)
    elif args.query:
        handle_query(args)
    elif args.sort:
        handle_sort(args)
    elif args.analyze is not None:
        handle_analyze(args)
    elif args.rationale:
        handle_rationale(args)
    elif args.add:
        handle_add(args)
    elif args.modify:
        handle_modify(args)
    elif args.ciyu:
        handle_ciyu(args)
    else:
        # 暂不支持非交互的子命令检查
        unsupported = [args.batch, args.guess]
        if any(unsupported):
            raise OperationError("该子命令目前仅支持交互模式，请无参数运行后从菜单中选择。")

        # 启动输入法 & 交互菜单
        if not args.no_ime:
            run_input_method()
        run_interactive_menu()


if __name__ == "__main__":
    try:
        main()
    except OperationError as e:
        print(f"操作失败：{e}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError as e:
        print(f"文件未找到：{e}", file=sys.stderr)
        sys.exit(2)
    except KeyboardInterrupt:
        print("\n\n程序被用户中断", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"未预期错误：{e}", file=sys.stderr)
        sys.exit(99)
