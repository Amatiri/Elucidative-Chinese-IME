import os
import sys
import subprocess
import argparse
import webbrowser
from manager.dictionary import ensure_data_file, query_chars
from manager.batch_entry import batch_add_entries
from manager.single_entry import single_add_entry, modify_entry
from manager.abc_analyzer import interactive_mode, analyze_abc_zone
from manager.file_processor import main_menu, sort_file_by_second_part
from manager.ciyu_ops import ciyumain
from manager.guess_game import bmmamain
from manager.rationale_add import main as rationale_main
from config import CIYU_FILE

# ------------------- 辅助函数 -------------------
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
    # 以下子命令暂不支持非交互，保留占位
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
    return parser.parse_args()

def main():
    args = parse_args()
    if args.keymap or args.query_web:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        web_dir = os.path.join(base_dir, 'help', 'webpage')
        
        if args.keymap:
            path = os.path.join(web_dir, '键位图.html')
            if os.path.exists(path):
                webbrowser.open('file://' + os.path.abspath(path))
                print(f"正在打开键位图：{path}")
            else:
                print(f"警告：文件不存在 - {path}")
        
        if args.query_web:
            path = os.path.join(web_dir, 'index.html')
            if os.path.exists(path):
                webbrowser.open('file://' + os.path.abspath(path))
                print(f"正在打开查询网页：{path}")
            else:
                print(f"警告：文件不存在 - {path}")
        return  
    ensure_data_file()
    # ---------- 子命令处理 ----------
    if args.query:
        chars = "".join(args.query)
        result, missing = query_chars(chars)
        print(result)
        if missing:
            print(f"未录入汉字：{''.join(missing)}")
        return

    if args.sort:
        try:
            single, phrase, web_chars, web_phrases = main_menu()
            print(f"整理完成！码表条目：{single}+{phrase}")
        except EOFError:
            print("整理码表功能需要终端交互，无法在非终端（如管道）环境下执行。")
            sys.exit(1)
        return

    if args.analyze is not None:
        if args.analyze == "__interactive__":
            interactive_mode()
        else:
            abc = args.analyze.lower()
            if len(abc) < 2 or not (abc[0].isalpha() and abc[-1].isdigit()):
                print(f"音码格式错误：{args.analyze}（应为如 bc1 的格式）")
                sys.exit(1)
            analyze_abc_zone(abc)
        return

    if args.rationale:
        if not args.char or not args.text:
            print("--rationale 需要配合 --char 和 --text 使用，无参数运行进入交互模式。")
            sys.exit(1)
        from manager.rationale_add import load_entries, load_rationale, save_rationale
        from manager.file_processor import build_web_data
        entries = load_entries()
        rationale = load_rationale()
        char_map = {}
        for ch, code in entries:
            char_map.setdefault(ch, []).append(code)
        if args.char not in char_map:
            print(f"码表中未找到「{args.char}」")
            sys.exit(1)
        val = args.text.replace('\\n', '\n')
        rationale[args.char] = val
        if save_rationale(rationale):
            print(f"[OK] {args.char} → {val.replace(chr(10), ' / ')}")
        build_web_data()
        return

    if args.add:
        if not args.char or not args.code:
            print("--add 需要配合 --char 和 --code 使用，无参数运行进入交互模式。")
            sys.exit(1)
        if len(args.char) != 1:
            print("--char 只接受单个汉字")
            sys.exit(1)
        code = args.code
        if len(code) < 4:
            print("编码过短，至少4位")
            sys.exit(1)
        from manager.dictionary import load_dictionary
        from manager.file_processor import process_file
        from config import DATA_FILE
        # 重码检测：同音区已有其他汉字使用同一完整编码
        _, full_dict = load_dictionary()
        abc_code = code[:3]
        if abc_code in full_dict:
            for h, c in full_dict[abc_code]:
                if c == code and h != args.char:
                    print("重码，添加失败")
                    return
        # 无冲突 → 追加写入
        with open(DATA_FILE, 'a', encoding='utf-8') as f:
            f.write(f"{args.char} {code}\n")
        process_file(DATA_FILE, DATA_FILE)
        print(f"[OK] {args.char} {code}")
        return

    if args.modify:
        if not args.code or not args.new_code:
            print("--modify 需要配合 --code 和 --new-code 使用，无参数运行进入交互模式。")
            sys.exit(1)
        old_code = args.code
        if len(old_code) < 4:
            print("旧编码过短，至少4位")
            sys.exit(1)
        from manager.dictionary import load_dictionary
        from manager.file_processor import process_file
        from config import DATA_FILE
        # 查找旧编码
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
            print("旧编码不存在")
            return
        new_code = args.new_code
        # 删除
        if new_code == 'x':
            lines = []
            with open(DATA_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            with open(DATA_FILE, 'w', encoding='utf-8') as f:
                for line in lines:
                    parts = line.strip().split(' ', 1)
                    if not (len(parts) == 2 and parts[0] == found_char and parts[1] == old_code):
                        f.write(line)
            process_file(DATA_FILE, DATA_FILE)
            print(f"[OK] 已删除 {found_char} {old_code}")
            return
        # 修改
        if len(new_code) < 4:
            print("新编码过短，至少4位")
            sys.exit(1)
        # 重码检测：同音区已有其他汉字使用同一完整编码
        abc_code = new_code[:3]
        if abc_code in full_dict:
            for h, c in full_dict[abc_code]:
                if c == new_code and h != found_char:
                    print("重码，修改失败")
                    return
        # 无冲突 → 替换
        lines = []
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            for line in lines:
                parts = line.strip().split(' ', 1)
                if len(parts) == 2 and parts[0] == found_char and parts[1] == old_code:
                    f.write(f"{found_char} {new_code}\n")
                else:
                    f.write(line)
        process_file(DATA_FILE, DATA_FILE)
        print(f"[OK] {found_char} {old_code} → {new_code}")
        return

    if args.ciyu:
        if not args.char:
            print("--ciyu 需要配合 --char 提供词语")
            sys.exit(1)
        word = args.char
        if len(word) == 1:
            if not args.code:
                print("单字词语（通用符号）需要配合 --code 指定编码")
                sys.exit(1)
            codes = [args.code]
        else:
            code_str, missing = query_chars(word)
            if missing:
                print(f"组成字未录入：{''.join(missing)}")
                sys.exit(1)
            codes_per_char = code_str.split()
            selected_codes = []
            for cs in codes_per_char:
                cl = cs.split('/')
                if cl[0] == '--':
                    print(f"组成字编码缺失")
                    sys.exit(1)
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
                print("词语重码，添加失败")
                return
        # 写入（覆盖同名词语旧记录）
        add_to_ciyu(word, codes, overwrite=True)
        sort_file_by_second_part(CIYU_FILE, CIYU_FILE)
        print(f"[OK] {word} {' '.join(codes)}")
        return
    if not args.no_ime:
        run_input_method()
    # 其他暂不支持的子命令
    unsupported = [args.batch, args.guess]
    if any(unsupported):
        print("该子命令目前仅支持交互模式，请无参数运行后从菜单中选择。")
        return

    # ---------- 交互菜单（原有逻辑） ----------
    if not sys.stdin.isatty():
        print("错误：交互模式需要终端（TTY），请使用子命令或重定向输入。")
        sys.exit(1)

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

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"程序启动出错: {str(e)}")
