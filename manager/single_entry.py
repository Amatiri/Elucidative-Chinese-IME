import os
from config import DATA_FILE
from manager.dictionary import load_dictionary
from manager.file_processor import process_file


def add_entry(char, code):
    """添加条目，递归处理重码冲突"""
    if len(code) < 3:
        print(f"编码 '{code}' 过短，至少需要3位")
        return None

    abc_code = code[:3]
    _, full_dict = load_dictionary()

    # 记录需要修改的条目：(汉字, 旧编码, 新编码)
    modified_entries = []

    # 递归解决重码的内部函数
    def resolve_conflict(hanzi, current_code, check_list, mod_entries):
        """返回 (最终编码, 更新后的mod_entries)"""
        # 检查 current_code 是否与 check_list 中其他汉字冲突
        conflict = None
        for h, c in check_list:
            if c == current_code and h != hanzi:
                conflict = (h, c)
                break
        if not conflict:
            return current_code, mod_entries

        conflict_hanzi, conflict_code = conflict
        print(f"编码 '{current_code}' 已分配给 '{conflict_hanzi}'")
        print("请处理重码冲突:")
        # 临时检查列表（排除当前冲突项）
        temp_list = [e for e in check_list if not (e[0] == conflict_hanzi and e[1] == conflict_code)]

        # 为冲突汉字重新生成编码
        new_conflict_code = abc_code + input(f"为 '{conflict_hanzi}' 输入新的形码: ")
        while any(e[1] == new_conflict_code for e in temp_list):
            print(f"新编码 '{new_conflict_code}' 仍与其他条目冲突")
            new_conflict_code = abc_code + input(f"为 '{conflict_hanzi}' 输入另一个新的形码: ")
        # 递归处理冲突汉字的冲突
        final_conflict_code, mod_entries = resolve_conflict(
            conflict_hanzi, new_conflict_code, temp_list, mod_entries
        )
        mod_entries.append((conflict_hanzi, conflict_code, final_conflict_code))
        # 更新临时列表，加入已修改的冲突汉字
        temp_list.append((conflict_hanzi, final_conflict_code))

        # 为当前汉字重新生成编码
        new_code = abc_code + input(f"为 '{hanzi}' 输入新的形码: ")
        while any(e[1] == new_code for e in temp_list):
            print(f"新编码 '{new_code}' 仍与其他条目冲突")
            new_code = abc_code + input(f"为 '{hanzi}' 输入另一个新的形码: ")
        # 递归处理当前汉字的新编码
        final_code, mod_entries = resolve_conflict(hanzi, new_code, temp_list, mod_entries)
        return final_code, mod_entries

    # 构建初始检查列表（同音区已有条目）
    check_list = []
    if abc_code in full_dict:
        check_list = full_dict[abc_code][:]  # 复制列表

    # 解决当前汉字的编码冲突
    final_code, modified_entries = resolve_conflict(char, code, check_list, [])

    # 读取现有文件
    entries = []
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            entries = f.readlines()

    # 构建最终行列表
    final_entries = []
    # 保留所有未被修改的行
    for line in entries:
        line = line.rstrip('\n')
        if not line:
            continue
        parts = line.split(' ', 1)
        if len(parts) != 2:
            final_entries.append(line + '\n')
            continue
        hanzi, old_code = parts
        replaced = False
        for (h, old_c, new_c) in modified_entries:
            if hanzi == h and old_code == old_c:
                replaced = True
                break
        if not replaced:
            final_entries.append(line + '\n')

    # 添加修改后的冲突条目新行
    for (h, old_c, new_c) in modified_entries:
        final_entries.append(f"{h} {new_c}\n")
    # 添加当前汉字的新条目
    final_entries.append(f"{char} {final_code}\n")

    # 写入文件
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        f.writelines(final_entries)

    process_file(DATA_FILE, DATA_FILE)
    return f"{char} {final_code}"


def update_or_delete_by_code(old_code, new_code):
    """通过编码更新或删除条目，递归处理重码冲突"""
    entries = []
    old_code_exists = False
    old_code_hanzis = []

    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            entries = f.readlines()
    for entry in entries:
        parts = entry.strip().split(' ', 1)
        if len(parts) == 2 and parts[1] == old_code:
            old_code_exists = True
            old_code_hanzis.append(parts[0])

    if not old_code_exists:
        print(f"编码 '{old_code}' 不存在")
        choice = input("是否要将此编码作为新条目添加？(y/n): ").strip().lower()
        if choice == 'y' or choice == 'yes':
            char = input("请输入要添加的汉字: ").strip()
            if not char:
                print("汉字不能为空，操作取消")
                return "操作取消"
            result = add_entry(char, old_code)
            if result:
                return f"添加成功: {result}"
            else:
                return "添加失败"
        else:
            return "操作取消"

    # 删除模式
    if new_code == 'x':
        new_entries = []
        for entry in entries:
            parts = entry.strip().split(' ', 1)
            if len(parts) == 2 and parts[1] == old_code:
                print(f"找到并删除: {entry.strip()}")
            else:
                new_entries.append(entry)
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            f.writelines(new_entries)
        process_file(DATA_FILE, DATA_FILE)
        return f"已删除编码 '{old_code}' 的所有条目"

    if len(new_code) < 3:
        print(f"新编码 '{new_code}' 过短，至少需要3位")
        return "操作失败：编码过短"

    abc_code = new_code[:3]
    _, full_dict = load_dictionary()

    # 递归解决重码的内部函数（与 add_entry 类似，但结合更新场景）
    def resolve_conflict(hanzi, target_code, check_list, mod_entries):
        conflict = None
        for h, c in check_list:
            if c == target_code and h != hanzi:
                conflict = (h, c)
                break
        if not conflict:
            return target_code, mod_entries

        conflict_hanzi, conflict_code = conflict
        print(f"新编码 '{target_code}' 已分配给 '{conflict_hanzi}'")
        print("请处理重码冲突:")
        temp_list = [e for e in check_list if not (e[0] == conflict_hanzi and e[1] == conflict_code)]

        new_conflict_code = abc_code + input(f"为 '{conflict_hanzi}' 输入新的形码: ")
        while any(e[1] == new_conflict_code for e in temp_list):
            print(f"新编码 '{new_conflict_code}' 仍与其他条目冲突")
            new_conflict_code = abc_code + input(f"为 '{conflict_hanzi}' 输入另一个新的形码: ")
        final_conflict_code, mod_entries = resolve_conflict(
            conflict_hanzi, new_conflict_code, temp_list, mod_entries
        )
        mod_entries.append((conflict_hanzi, conflict_code, final_conflict_code))
        temp_list.append((conflict_hanzi, final_conflict_code))

        new_target_code = abc_code + input(f"为 '{hanzi}' 输入新的形码: ")
        while any(e[1] == new_target_code for e in temp_list):
            print(f"新编码 '{new_target_code}' 仍与其他条目冲突")
            new_target_code = abc_code + input(f"为 '{hanzi}' 输入另一个新的形码: ")
        final_target_code, mod_entries = resolve_conflict(hanzi, new_target_code, temp_list, mod_entries)
        return final_target_code, mod_entries

    # 构建初始检查列表（同音区已有条目，排除旧编码自身）
    check_list = []
    if abc_code in full_dict:
        for h, c in full_dict[abc_code]:
            if c != old_code:
                check_list.append((h, c))

    # 收集所有使用 old_code 的汉字
    chars_to_update = []
    for entry in entries:
        parts = entry.strip().split(' ', 1)
        if len(parts) == 2 and parts[1] == old_code:
            chars_to_update.append(parts[0])

    if not chars_to_update:
        # 未找到旧编码，询问添加新汉字
        char = input(f"未找到编码 '{old_code}'，请输入要添加的汉字: ").strip()
        if not char:
            print("汉字不能为空")
            return "操作取消"
        # 直接将新汉字加入，需解决重码
        final_new_code, modified_entries = resolve_conflict(char, new_code, check_list, [])
        # 添加新条目
        new_entries = entries + [f"{char} {final_new_code}\n"]
        # 应用修改（冲突条目替换）
        for h, old_c, new_c in modified_entries:
            for i, line in enumerate(new_entries):
                parts = line.strip().split(' ', 1)
                if len(parts) == 2 and parts[0] == h and parts[1] == old_c:
                    new_entries[i] = f"{h} {new_c}\n"
                    break
        with open(DATA_FILE, 'w', encoding='utf-8') as f:
            f.writelines(new_entries)
        process_file(DATA_FILE, DATA_FILE)
        return f"添加成功: {char} {final_new_code}"

    # 更新所有使用 old_code 的汉字
    modified_entries = []  # (汉字, 旧编码, 新编码)
    final_entries = entries[:]  # 复制一份
    for hanzi in chars_to_update:
        # 为该汉字生成新编码，解决冲突
        final_code, mods = resolve_conflict(hanzi, new_code, check_list, [])
        modified_entries.extend(mods)
        # 替换该汉字的旧编码行
        for i, line in enumerate(final_entries):
            parts = line.strip().split(' ', 1)
            if len(parts) == 2 and parts[0] == hanzi and parts[1] == old_code:
                final_entries[i] = f"{hanzi} {final_code}\n"
                break
        # 将本次新编码加入检查列表，避免同一批次内重复
        check_list.append((hanzi, final_code))

    # 应用所有冲突条目修改（替换其他汉字的编码）
    for h, old_c, new_c in modified_entries:
        for i, line in enumerate(final_entries):
            parts = line.strip().split(' ', 1)
            if len(parts) == 2 and parts[0] == h and parts[1] == old_c:
                final_entries[i] = f"{h} {new_c}\n"
                break

    # 写入文件
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        f.writelines(final_entries)
    process_file(DATA_FILE, DATA_FILE)
    return f"操作成功，已更新 {len(chars_to_update)} 个条目"


def single_add_entry():
    """添加单字"""
    char = input("汉字: ").strip()
    if not char:
        print("汉字不能为空")
        return
    code = input("编码: ").strip()
    if not code:
        print("编码不能为空")
        return
    if len(code) < 3:
        print("编码至少需要3位")
        return
    result = add_entry(char, code)
    if result:
        print(f"添加成功: {result}")
    else:
        print("添加失败")


def modify_entry():
    """编辑修改条目"""
    old_code = input("要修改的编码: ").strip()
    if not old_code:
        print("编码不能为空")
        return
    if len(old_code) < 3:
        print("编码至少需要3位")
        return
    new_code = input("新编码（x删除）: ").strip()
    if not new_code:
        print("新编码不能为空")
        return
    if old_code == new_code:
        print("编码相同，无需修改")
        return
    result = update_or_delete_by_code(old_code, new_code)
    print(result)
