# -*- coding: utf-8 -*-
"""类型符分配 → 通用符号对照。

输入形如 r(oa oo oi)：
- 第一行输出括号分配结果（如 roa roo roi）；
- 第二行按空格分隔各编码，在词语码表 ciyu.txt 中查找对应通用符号，
  直接连接输出（无空格），未找到的编码以 "--" 占位。

码表定位与 sync_pending_pinyin.py 一致：先定位项目根，再导入 config。
"""
import os
import sys

try:                                    # PrintRedirector 等重定向对象没有 reconfigure
    sys.stdout.reconfigure(encoding="utf-8")
except (AttributeError, ValueError, OSError):
    pass

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import config


_code_to_symbol_cache = None


def _load_code_to_symbol():
    """延迟加载词语码表 ciyu.txt，返回 {编码: 通用符号} 映射。

    行格式「符号 空格 编码[ 空格 编码...]」：一个符号可带多个编码，须全部登记
    （语义与 dictionary_frontend.query_phrase 的 code in parts[1:] 一致）。
    同一编码多行出现时保留文件中首次出现（query_phrase 顺序扫描、命中即返回）。
    """
    global _code_to_symbol_cache
    if _code_to_symbol_cache is not None:
        return _code_to_symbol_cache
    mapping = {}
    with open(config.CIYU_FILE, encoding="utf-8") as f:
        for line in f:
            parts = line.split()
            if len(parts) >= 2:
                symbol = parts[0]
                for code in parts[1:]:
                    mapping.setdefault(code, symbol)
    _code_to_symbol_cache = mapping
    return mapping


def distribute(line):
    left = line.find("(")
    right = line.rfind(")")
    if line.strip() == "":
        return "已退出"
    if left == -1 or right == -1 or right < left:
        return "格式错误"
    prefix = line[:left]
    inside = line[left + 1:right]
    suffix = line[right + 1:]   
    items = inside.split()
    result = " ".join(prefix + item + suffix for item in items)
    return result


def lookup_symbols(codes_str):
    """按空格分隔编码串，在词语码表中查找对应通用符号，直接连接（无空格）；
    未找到的编码以 "--" 占位。"""
    mapping = _load_code_to_symbol()
    return "".join(mapping.get(code, "--") for code in codes_str.split())


def main():
    print("通过括号将类型符分配给各通用符号的其余编码，r(oa oo oi)→roa roo roi")
    while True:
        line = input("输入：")
        result = distribute(line)
        if result == "格式错误":
            print(result)
            continue
        elif result == "已退出":
            print(result)
            break
        print(result)
        print(lookup_symbols(result))
if __name__ == "__main__":
    main()
