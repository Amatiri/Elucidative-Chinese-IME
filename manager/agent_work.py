import os
import sys
import importlib
import ast
from config import BASE_DIR


def import_py_files(directory_path):
    """
    扫描目录下的 .py 文件，静态检测是否定义了 main 函数，
    不执行模块的任何顶层代码。
    返回列表，元素为 (module_name, None, has_main)
    """
    modules_info = []

    for filename in os.listdir(directory_path):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            if not module_name.isidentifier():
                print(f"跳过非法模块名: {module_name}")
                continue

            file_path = os.path.join(directory_path, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    source = f.read()
                tree = ast.parse(source, filename=file_path)
                has_main = any(
                    isinstance(node, ast.FunctionDef) and node.name == 'main'
                    for node in tree.body
                )
                # 如果需要保留 module 对象以便后续调用，可返回 None 占位
                modules_info.append((module_name, None, has_main))
            except (SyntaxError, UnicodeDecodeError, OSError) as e:
                print(f"解析 {module_name} 失败: {e}")

    return modules_info


def list_available_modules(modules_info):
    available = [(name, mod) for name, mod, has in modules_info if has]
    if not available:
        print("未找到任何包含 main() 函数的模块。")
        return None

    print("解书音形 - agent_workspace工具表")
    for idx, (name, _) in enumerate(available, start=1):
        print(f"{idx}.{name}")
    return available


def run_selected_module(available):
    # 确保模块所在目录在 sys.path 中，以便 importlib 能导入
    dir_path = os.path.join(BASE_DIR, "agent_workspace")
    if dir_path not in sys.path:
        sys.path.insert(0, dir_path)

    while True:
        choice = input("选择: ").strip()
        if not choice:
            break

        if not choice.isdigit():
            print("请输入一个数字。")
            continue

        num = int(choice)
        if 1 <= num <= len(available):
            module_name, _ = available[num - 1]   # 原来的 module 占位为 None，忽略
            try:
                # 真正导入模块（此时会执行其顶层代码）
                module = importlib.import_module(module_name)
            except Exception as e:
                print(f"导入 {module_name} 失败: {e}\n")
                continue

            # 隔离 sys.argv，防止工具内部读取到主程序的参数
            saved_argv = sys.argv
            try:
                sys.argv = [saved_argv[0]]
                module.main()
                print()
            except SystemExit:
                # 工具内部调用 sys.exit() 时不让整个菜单退出
                pass
            except Exception as e:
                print(f"执行 {module_name}.main() 时出错: {e}\n")
            finally:
                sys.argv = saved_argv
        else:
            print(f"请输入 1 ~ {len(available)} 之间的数字。")


def main():
    dir_path = os.path.join(BASE_DIR, "agent_workspace")

    if not os.path.isdir(dir_path):
        print("错误：目录不存在或不是一个目录。")
        return
    modules_info = import_py_files(dir_path)
    available = list_available_modules(modules_info)
    if available:
        run_selected_module(available)


if __name__ == "__main__":
    main()
