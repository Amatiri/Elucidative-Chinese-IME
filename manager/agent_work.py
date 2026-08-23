import os
import sys
import importlib
from config import BASE_DIR

def import_py_files(directory_path):

    abs_path = os.path.abspath(directory_path)
    if abs_path not in sys.path:
        sys.path.insert(0, abs_path)

    modules_info = []

    for filename in os.listdir(directory_path):
        if filename.endswith('.py') and filename != '__init__.py':
            module_name = filename[:-3]
            if not module_name.isidentifier():
                print(f"跳过非法模块名: {module_name}")
                continue

            try:
                module = importlib.import_module(module_name)
                has_main = hasattr(module, 'main') and callable(module.main)
                modules_info.append((module_name, module, has_main))
            except Exception as e:
                print(f"导入 {module_name} 失败: {e}")

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
    while True:
        choice = input("选择: ").strip()
        if not choice:
            break

        if not choice.isdigit():
            print("请输入一个数字。")
            continue

        num = int(choice)
        if 1 <= num <= len(available):
            module_name, module = available[num - 1]
            try:
                module.main()
                print()
            except Exception as e:
                print(f"执行 {module_name}.main() 时出错: {e}\n")
            # 运行后不退出循环，可继续选择其他模块
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
