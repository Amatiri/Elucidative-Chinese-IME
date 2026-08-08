import os
import sys
import argparse
import subprocess
from manager.cli_handlers import OperationError, safe_input, open_web_page
from manager.cli_handlers import (
    handle_show,
    handle_query,
    handle_sort,
    handle_analyze,
    handle_rationale,
    handle_add,
    handle_modify,
    handle_ciyu,
)
from manager.dictionary import ensure_data_file
from manager.batch_entry import batch_add_entries
from manager.single_entry import single_add_entry, modify_entry
from manager.abc_analyzer import interactive_mode
from manager.file_processor import main_menu
from manager.ciyu_ops import ciyumain
from manager.guess_game import bmmamain
from manager.rationale_add import main as rationale_main


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

def run_input_method():
    """启动输入法前端（ime.py）。"""
    try:
        ime_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ime.py")
        subprocess.Popen([sys.executable, ime_path])
    except Exception as e:
        print(f"启动输入法失败: {e}")
        
def run_interactive_menu():
    """交互模式主循环（保留在 main.py，因为它与 show_menu 紧密耦合）"""
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
        unsupported = [args.batch, args.guess]
        if any(unsupported):
            raise OperationError("该子命令目前仅支持交互模式，请无参数运行后从菜单中选择。")

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
