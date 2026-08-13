# -*- coding: utf-8 -*-
"""
解书音形 · 简打编码生成器 (generate_jd_codes.py)

输入一串汉字，输出其简打编码（含合理空格分配）。

逻辑:
  1. 识别汉字串中的词语，查询其最短编码
  2. 逐字查到其匹配前缀的最短编码
  3. 尝试将相邻编码拼接，若 split_sequence 无法正确拆分则插入空格
  4. 通过 CLI_emulation.py 管道验证是否正确

用法:
    python generate_jd_codes.py "滚滚长江东逝水"
    python generate_jd_codes.py "倘若我心中的山水"   # 与高阶版对比
    python generate_jd_codes.py "我便一步一莲花祈祷"
    python generate_jd_codes.py -f input.txt        # 从文件读

依赖: dictionary_frontend.py / dictionary.txt / ciyu.txt
"""

import sys, os, argparse

DEP_DIR = os.environ.get("JIESHU_IME_HOME", r"D:\USB\Py\输入法")
sys.path.insert(0, DEP_DIR)

from manager.dictionary_frontend import (
    query_by_prefix, query_phrase, split_sequence
)
from config import DATA_FILE, CIYU_FILE

# Windows 中文输出修复
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = __import__('io').TextIOWrapper(
        sys.stdout.buffer, encoding='utf-8', errors='replace')


# ═══════════════════════════════════════════
#  步骤1: 词语识别
# ═══════════════════════════════════════════

def load_word_dict():
    """加载词库，返回 {词: [编码1, 编码2, ...]}。
    只取 ≥2 个汉字且以汉字开头的实际词语条目。
    """
    words = {}
    with open(CIYU_FILE, encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split(' ')
            if len(parts) < 2:
                continue
            word = parts[0]
            codes = parts[1:]
            # 开头非汉字 → 部首/符号条目,跳过
            if not ('\u4e00' <= word[0] <= '\u9fff'):
                continue
            if len(word) < 2:
                continue
            if word not in words:
                words[word] = []
            words[word].extend(codes)
    return words


def shortest_word_code(word, words_dict):
    """返回词的最短注册编码。"""
    if word not in words_dict:
        return None
    return min(words_dict[word], key=len)


def segment_words(text, words_dict):
    """最长词优先分词。"""
    result = []
    i = 0
    n = len(text)
    while i < n:
        best_word, best_len = None, 0
        max_j = min(n, i + 8)
        for j in range(max_j, i + 1, -1):
            cand = text[i:j]
            if cand in words_dict:
                best_word, best_len = cand, j - i
                break
        if best_word:
            result.append((best_word, True))
            i += best_len
        else:
            result.append((text[i], False))
            i += 1
    return result


# ═══════════════════════════════════════════
#  步骤2: 逐字最短编码
# ═══════════════════════════════════════════

def find_full_codes(char):
    """在 dictionary.txt 中查汉字所有全码（可能有多个变体）。"""
    codes = []
    with open(DATA_FILE, encoding='utf-8') as f:
        for line in f:
            if line.startswith(char + ' '):
                codes.append(line.strip().split()[1])
    return codes if codes else None


def find_full_code(char):
    """返回汉字的最优全码——即能产生最短前缀编码的那个变体。
    
    若多个变体最短前缀长度相同，取第一个。
    兼容旧接口，新代码建议直接用 find_shortest_code() 获取编码+全码。
    """
    codes = find_full_codes(char)
    if not codes:
        return None
    if len(codes) == 1:
        return codes[0]
    # 有多个变体：取能缩短到最短的那个
    _short, best_full = find_shortest_code(char)
    return best_full


def find_shortest_code(char):
    """找某个汉字的最短可用编码前缀。
    
    一个汉字在字典中可能有多个全码变体（如「看」同时有 kj1m 和 kj4m）。
    对每个全码分别逐位缩短，取全局最短者。
    
    Returns: (shortest_code, best_full_code)
      - shortest_code: 全局最短前缀编码
      - best_full_code: 产生该最短编码的对应全码变体
    """
    codes = find_full_codes(char)
    if not codes:
        return None, None

    global_best = codes[0]  # 初始取第一个全码
    global_best_full = codes[0]
    for full in codes:
        best = full
        for cut in range(len(full) - 1, 0, -1):
            shorter = full[:cut]
            cands = query_by_prefix(shorter)
            if cands and cands[0][0] == char:
                best = shorter
            else:
                break
        if len(best) < len(global_best):
            global_best = best
            global_best_full = full
    return global_best, global_best_full


# ═══════════════════════════════════════════
#  步骤3: 空格分配 (核心)
# ═══════════════════════════════════════════

def _can_chain(coded_segs, next_seg):
    """
    验证把 next_seg 追加到当前段组后，能否在实时输入中正确上屏。
    
    分两步：
      (A) split_sequence 能否正确拆分拼接码
      (B) 逐字符模拟输入，自动上字是否会在错误位置截断
    
    返回 (can_chain, result_chars)。
    """
    existing_codes = [s['code'] for s in coded_segs]
    combined = ''.join(existing_codes) + next_seg['code']
    parts = split_sequence(combined).split("'")

    expected_segs = coded_segs + [next_seg]
    if len(parts) != len(expected_segs):
        return False, None

    result_chars = []
    for seg, part in zip(expected_segs, parts):
        cands = query_by_prefix(part)
        if not cands:
            return False, None
        top_char = cands[0][0]
        result_chars.append(top_char)
        if len(seg['text']) == 1 and top_char != seg['text']:
            return False, None
        if seg.get('is_word') and top_char != seg['text'][0]:
            return False, None

    # (B) 自动上字模拟：逐字符输入 combined，检查自交是否触发错误
    expected_text = ''.join(s['text'] for s in expected_segs)
    ok, got = _simulate_auto_commit(combined, expected_text)
    return ok, ''.join(result_chars)


def _simulate_auto_commit(code_str, expected_text):
    """
    逐字符模拟输入，追踪自动上字事件，检查是否在正确位置触发。
    
    前端 _on_input_change 中的 auto_commit 逻辑:
      若单段 + len>3 + 唯一非点候选 → 自动上字(首字)
      → 上屏后 buffer 清空，后续字符重新开始
    
    返回 (all_correct, committed_text):
      - all_correct: 所有自交都正确
      - committed_text: 实际自交得到的内容
    """
    from config import CODE_CHARS
    from manager.dictionary_frontend import process_input
    
    buffer = ""
    committed = ""
    exp_idx = 0
    
    for ch in code_str:
        if ch not in CODE_CHARS:
            continue
        buffer += ch
        
        processed = process_input(buffer)
        if len(processed) <= 3:
            continue
        
        spl = split_sequence(processed)
        if "'" in spl:
            continue  # 多段 → 不触发自交
        
        cands = query_by_prefix(spl)
        if not cands:
            continue
        
        non_dot = [c for c in cands
                    if '.' not in (c[1:] if len(c) > 1 else '')]
        if len(non_dot) == 1:
            # 自交触发
            committed_char = non_dot[0][0]
            if exp_idx >= len(expected_text):
                return False, committed
            if committed_char != expected_text[exp_idx]:
                return False, committed + committed_char
            committed += committed_char
            exp_idx += 1
            buffer = ""
    
    # After all typing, check that committed + residual buffer = expected
    residual_text = ""
    if buffer:
        parts = split_sequence(buffer).split("'")
        for part in parts:
            cands = query_by_prefix(part)
            if cands:
                residual_text += cands[0][0]

    if committed + residual_text != expected_text:
        return False, committed
    return True, committed


def assign_spaces(coded_segs, words_dict):
    """
    贪心拼接：尝试最大程度连接相邻编码段，连接失败则插入空格。

    Returns: [(codes_str, segs_list), ...]
    """
    if not coded_segs:
        return []

    groups = []
    current = [coded_segs[0]]

    for i in range(1, len(coded_segs)):
        curr = coded_segs[i]

        # 词语前后必须空格
        if current[-1].get('is_word') or curr.get('is_word'):
            groups.append(current)
            current = [curr]
            continue

        ok, _ = _can_chain(current, curr)
        if ok:
            current.append(curr)
        else:
            groups.append(current)
            current = [curr]

    groups.append(current)

    result = []
    for g in groups:
        codes_str = ''.join(s['code'] for s in g)
        result.append((codes_str, g))
    return result


# ═══════════════════════════════════════════
#  步骤3.5: 首选字避让词语
# ═══════════════════════════════════════════

def resolve_word_conflicts(groups, words_dict):
    """
    处理"首选字避让词语"冲突（2(4)）。

    逐字编码拼接后，拼接码可能意外命中另一个词语的注册编码。
    此时用贪心回退方式逐步分隔，直到无冲突。

    示例:
      "之十" → vi + ui2 = viui2 → query_phrase("viui2") = "知识" ≠ "之十"
      → 分隔为 vi ui2

    Returns: adjusted_groups [(codes_str, segs_list), ...]
    """
    adjusted = []
    for codes_str, segs in groups:
        # 单字段或已标记词语不检查
        if len(segs) <= 1 or any(s.get('is_word') for s in segs):
            adjusted.append((codes_str, segs))
            continue

        intended_text = ''.join(s['text'] for s in segs)
        phrase = query_phrase(codes_str)
        if phrase and phrase != intended_text:
            # 有冲突 → 贪心回退分隔
            resolved = _split_until_no_conflict(segs, intended_text)
            adjusted.extend(resolved)
        else:
            adjusted.append((codes_str, segs))

    return adjusted


def _split_until_no_conflict(segs, intended_text):
    """
    从右向左逐步分隔，直到每段拼接码都不命中其他词语。
    最终兜底：每字全部分隔（一定成功）。

    前置检查：整段无冲突则立即返回合并（递归终止条件）。
    否则按贪心回退逐位尝试分裂。

    示例 (之十 vi+ui2→viui2 冲突知识):
      1. 合并码 viui2 冲突 → 末字独立: vi + ui2 → vi 无冲突, ui2 单字 → OK

    示例 (书茹发 uu+ru+f→uuruf 冲突"输入法"):
      1. 合并码冲突 → 末字独立: uuru + f → uuru 仍有冲突
      2. 前移: uu + ruf → ruf 经前置检查，无冲突 → 保持合并
      3. 结果: uu + ruf
    """
    n = len(segs)
    combined_code = ''.join(s['code'] for s in segs)

    # 前置：无冲突则保持合并（递归终止条件）
    phrase = query_phrase(combined_code)
    if not phrase or phrase == intended_text:
        return [(combined_code, segs)]

    # 有冲突 → 尝试分裂
    for split_idx in range(n - 1, 0, -1):
        prefix_segs = segs[:split_idx]
        suffix_segs = segs[split_idx:]
        prefix_code = ''.join(s['code'] for s in prefix_segs)
        prefix_text = ''.join(s['text'] for s in prefix_segs)

        # 检查前缀（多字时）
        prefix_ok = True
        if len(prefix_segs) > 1:
            prefix_phrase = query_phrase(prefix_code)
            prefix_ok = (not prefix_phrase or prefix_phrase == prefix_text)
        # 检查后缀（多字时）
        suffix_ok = True
        if len(suffix_segs) > 1:
            suffix_code = ''.join(s['code'] for s in suffix_segs)
            suffix_text = ''.join(s['text'] for s in suffix_segs)
            suffix_phrase = query_phrase(suffix_code)
            suffix_ok = (not suffix_phrase or suffix_phrase == suffix_text)

        if prefix_ok and suffix_ok:
            # 两部分当前均无冲突 → 递归仅用于有潜在内部冲突的情况
            result = [(prefix_code, prefix_segs)]
            if len(suffix_segs) > 1:
                result.extend(_split_until_no_conflict(
                    suffix_segs,
                    ''.join(s['text'] for s in suffix_segs)
                ))
            else:
                result.append((suffix_segs[0]['code'], suffix_segs))
            return result

    # 所有位置都冲突 → 每字独立成段（兜底，一定成功）
    return [(s['code'], [s]) for s in segs]


# ═══════════════════════════════════════════
#  步骤4: CLI 验证
# ═══════════════════════════════════════════

def verify_with_cli(code_str, expected_text):
    """
    逐段验证: 每个空格段独立送 CLI，最后拼接对比。
    
    不能把完整编码串直接喂 CLI:
      - gp3ugp3u... 逐字符输入时 gp3u(4码唯一)会被 auto-commit 抢断
      - 必须模拟用户行为: 每段后加空格提交 -> 再输入下一段
    """
    import subprocess
    script_path = os.path.join(os.path.dirname(__file__), 'CLI_emulation.py')
    segments = code_str.split()

    total_output = ''
    for seg in segments:
        # CLI 逐个字符处理，末尾空格触发上屏 + 重置
        test_input = seg + ' '
        try:
            proc = subprocess.run(
                [sys.executable, script_path],
                input=test_input,
                capture_output=True,
                text=True,
                timeout=10,
                cwd=DEP_DIR
            )
            output = proc.stdout.strip()
            total_output += output
        except Exception as e:
            return False, str(e), ''

    return total_output == expected_text, total_output, ''


# ═══════════════════════════════════════════
#  主流程
# ═══════════════════════════════════════════

def generate(text, words_dict=None, verbose=True, verify=True):
    """
    核心管道: 输入汉字串 -> 输出简打编码。

    Returns: (code_str, stats_dict)
    """
    if words_dict is None:
        words_dict = load_word_dict()

    # ── 步骤 1: 分词 ──
    segs = segment_words(text, words_dict)

    # ── 步骤 2: 逐段编码 ──
    coded = []
    total_full = 0
    total_short = 0
    for seg_text, is_word in segs:
        if is_word:
            code = shortest_word_code(seg_text, words_dict)
            # 词语的"全码"=逐字全码拼接
            char_fulls = []
            for ch in seg_text:
                fc = find_full_code(ch)
                char_fulls.append(fc if fc else '??')
            word_full = ''.join(char_fulls)
            word_full_len = sum(len(f) for f in char_fulls if f != '??')
            coded.append({
                'text': seg_text,
                'is_word': True,
                'code': code or '??',
                'full': ' '.join(char_fulls),
                'len': len(code) if code else 0,
                'full_len': word_full_len,
            })
            if code:
                total_short += len(code)
                total_full += word_full_len
        else:
            short, full = find_shortest_code(seg_text)
            if short is None:
                coded.append({
                    'text': seg_text,
                    'is_word': False,
                    'code': '??',
                    'full': '??',
                    'len': 0,
                })
            else:
                coded.append({
                    'text': seg_text,
                    'is_word': False,
                    'code': short,
                    'full': full,
                    'len': len(short),
                })
                total_short += len(short)
                total_full += len(full)

    # ── 步骤 3: 分配空格 ──
    groups = assign_spaces(coded, words_dict)
    # ── 步骤 3.5: 首选字避让词语 (2(4)) ──
    groups = resolve_word_conflicts(groups, words_dict)
    code_str = ' '.join(g[0] for g in groups)

    # ── 步骤 4: 验证 ──
    verified, cli_output, cli_err = False, '', ''
    if verify and code_str:
        verified, cli_output, cli_err = verify_with_cli(code_str, text)

    # ── 打印 ──
    if verbose:
        W = 72
        print("=" * W)
        print(f"  原文: {text}")
        print(f"  简打: {code_str}")
        if verify:
            mark = '[OK] 通过' if verified else '[FAIL] 失败'
            print(f"  验证: {mark}")
            if not verified and cli_output:
                print(f"    CLI输出: {cli_output}")
                if cli_err:
                    print(f"    CLI错误: {cli_err}")
        print("=" * W)

        # 表1: 逐字/词分析
        print(f"\n  {'字/词':<8} {'编码':<10} {'全码':<16} {'省':<6} {'类型'}")
        print("  " + "-" * 58)
        for c in coded:
            saved = ''
            if c['is_word']:
                full_len = c.get('full_len', 0)
                saved = full_len - len(c['code']) if c['code'] != '??' else ''
            elif c['full'] not in ('??',):
                saved = len(c['full']) - len(c['code'])
            print(f"  {c['text']:<8} {c['code']:<10} {c['full']:<16} {str(saved):<6}"
                  f" {'[词语]' if c['is_word'] else ''}")

        # 表2: 段内组合
        print(f"\n  >>  编码段 ({len(groups)}段):")
        for codes, segs in groups:
            chars = ''.join(s['text'] for s in segs)
            print(f"      [{chars}] -> {codes}")

        # 表3: 空格必要性 (仅多段时)
        if len(groups) > 1:
            print(f"\n  >>  空格必要性:")
            no_spaces = code_str.replace(' ', '')
            ns_parts = split_sequence(no_spaces).split("'")
            errors = 0
            for p in ns_parts:
                cands = query_by_prefix(p)
                top = cands[0][0] if cands else '-'
                ok = 'OK' if cands else 'INVALID'
                if not cands:
                    errors += 1
                print(f"      {p:<14} -> {top:<6} {ok}")
            if errors:
                print(f"      无空格时 {errors} 段无效 -> 空格必要")

        # 统计
        saved_total = total_full - total_short
        code_chars = len(code_str) - sum(1 for c in code_str if c == ' ')
        print(f"\n  >>  统计: {len(text)}字 -> {code_chars}码"
              f" (省{saved_total}码)")
        if verify:
            print(f"  >>  CLI验证: {'[OK] 一致' if verified else '[FAIL] 不一致'}")
        print()

    stats = {
        'text': text,
        'code': code_str,
        'verified': verified,
        'cli_output': cli_output,
        'total_short': total_short,
        'total_full': total_full,
        'groups': groups,
        'coded': coded,
    }
    return code_str, stats


# ═══════════════════════════════════════════
#  CLI 入口
# ═══════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description='解书音形 · 简打编码生成器',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python generate_jd_codes.py "滚滚长江东逝水"
  python generate_jd_codes.py "倘若我心中的山水"
  python generate_jd_codes.py -f input.txt
  python generate_jd_codes.py -q "你好世界"     # 静默模式
  python generate_jd_codes.py --no-verify "测试"  # 跳过CLI验证
        """
    )
    parser.add_argument('text', nargs='*', help='要生成简打编码的汉字串')
    parser.add_argument('-f', '--file', help='从文件读取（每行一句）')
    parser.add_argument('-q', '--quiet', action='store_true',
                        help='静默模式，仅输出编码')
    parser.add_argument('--no-verify', action='store_true',
                        help='跳过 CLI 验证')
    args = parser.parse_args()

    words_dict = load_word_dict()

    inputs = []
    if args.file:
        with open(args.file, encoding='utf-8') as f:
            inputs = [line.strip() for line in f if line.strip()]
    elif args.text:
        inputs = args.text  # 多参数逐个独立处理
    else:
        print("解书音形 · 简打编码生成器")
        print("输入汉字串，回车生成简打编码。输入 exit 退出。\n")
        while True:
            try:
                line = input("汉字> ")
            except (EOFError, KeyboardInterrupt):
                break
            if line.lower() in ('exit', 'quit', ''):
                break
            generate(line.strip(), words_dict, verbose=not args.quiet,
                     verify=not args.no_verify)
        return

    for text in inputs:
        if not text:
            continue
        code_str, _stats = generate(text, words_dict,
                                    verbose=not args.quiet,
                                    verify=not args.no_verify)
        if args.quiet:
            print(code_str)


if __name__ == '__main__':
    main()
