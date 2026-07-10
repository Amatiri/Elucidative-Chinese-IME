import os
import sys
import subprocess

from manager.dictionary import ensure_data_file, query_chars
from manager.batch_entry import batch_add_entries
from manager.single_entry import single_add_entry, modify_entry
from manager.abc_analyzer import interactive_mode
from manager.file_processor import main_menu, sort_file_by_second_part
from manager.ciyu_ops import ciyumain
from manager.guess_game import bmmamain
from config import CIYU_FILE


def run_input_method():
    """启动输入法"""
    print("启动解书音形...")
    try:
        ime_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ime.py")
        subprocess.run([sys.executable, ime_path], check=True)
    except subprocess.CalledProcessError as e:
        print(f"启动输入法失败: {e}")
    except FileNotFoundError:
        print("错误：未找到 ime.py 文件")
    except Exception as e:
        print(f"启动输入法时发生未知错误: {e}")


def show_menu():
    print("解书音形 - 管理程序")
    print("1.批量录入 ", end="")
    print("2.添加单字 ", end="")
    print("3.编辑修改 ")
    print("4.分析音区 ", end="")
    print("5.整理码表 ", end="")
    print("6.启动输入 ")
    print("7.查询字码 ", end="")
    print("8.添加词语 ", end="")
    print("9.猜测编码")


def main():
    ensure_data_file()
    while True:
        show_menu()
        try:
            choice = input("选项: ").strip()
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
                run_input_method()
            elif choice == '7':
                while True:
                    a = input("连续汉字：")
                    if a == "":
                        break
                    b, missing = query_chars(a)
                    print(b)
                    if missing:
                        print(f"未录入汉字：{''.join(missing)}")
            elif choice == '8':
                ciyumain()
                a = sort_file_by_second_part(CIYU_FILE, CIYU_FILE)
                print(f"完成！词语条目：{a}")
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
