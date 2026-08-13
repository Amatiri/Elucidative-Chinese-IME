# -*- coding: utf-8 -*-
"""
解书音形 · 简打分析器 (jd_analyze.py)

用于分析多字编码串的简打机制——逐段拆解、验证最短性、演示空格必要性。
依赖项目目录下的 dictionary_frontend.py + dictionary.txt + ciyu.txt。

用法:
    python jd_analyze.py "th3r row xnvsd ujuv3"
    python jd_analyze.py --all           # 跑副歌六句全套
    python jd_analyze.py -q --all        # 静默（纯数据显示）

输出:
    (1) 逐段拆分表 — 每个子段对应哪个字、编码级、省码数
    (2) 最短性验证 — 逐字缩短一级看首选是否还是目标字
    (3) 空格必要性 — 去掉空格后的拆分结果对比 + 粘连点
    (4) 词组命中 — 是否通过 query_phrase 走词库捷径

设计笔记:
    - query_by_prefix 返回的候选格式: "<汉字><剩余编码>" (如 "若4c"、"我o3g")
    - 首字符即汉字，后面是前缀命中的剩余编码
    - 全码需从 dictionary.txt 独立查询（find_full_code）
"""

import sys, io, os, argparse, pathlib
if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
elif hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
DEP_DIR = os.environ.get("JIESHU_IME_HOME", r"D:\USB\Py\输入法")
sys.path.insert(0, DEP_DIR)

from config import CODE_CHARS
from manager.dictionary_frontend import (
    query_by_prefix, query_phrase, split_sequence, query_multi_chars, process_input
)

DEMO_SENTENCES = [
    ("倘若我心中的山水", "th3r row xnvsd ujuv3"),
    ("你眼中都看到",     "nyj3m vsdbkj4dk4"),
    ("我便一步一莲花祈祷", "wbm4r yibu4v yilmhw qidk3"),
    ("怎知那浮生一片草",   "zfvi1u nafu2uvugyipmck3"),
    ("岁月催人老",       "sv4uyt4jcv1r rlk3l"),
    ("风月花鸟一笑尘缘了", "fg1pyt4j hwncyixc4zif2tyr2s l"),
]

# ── 工具函数 ────────────────────────────────────────────

def split_segs(s):
    return [x for x in split_sequence(s).split("'") if x]


def top_char_from_candidate(cand):
    """从候选字符串提取首字符（汉字）"""
    return cand[0] if cand else "?"


def find_full_code(char):
    """在 dictionary.txt 中查汉字的全码"""
    dict_path = pathlib.Path(DEP_DIR) / "dictionary.txt"
    with open(dict_path, encoding='utf-8') as f:
        for line in f:
            if line.startswith(char + ' '):
                return line.strip().split()[1]
    return "?"


def level_name(n):
    """编码长度 → 简打级名"""
    return {1: "一级", 2: "AB二码", 3: "ABC三码", 4: "四码全码", 5: "五码全码"}.get(n, f"{n}码")


def try_shorter(seg, char):
    """逐位缩短查询前缀，找该字的最短编码。
    
    返回 (最短前缀, 级名)。
    从 seg 开始逐位缩短，直到缩短一位后首选不再是 char 为止。
    """
    # 确认 seg 下首选是不是 char
    cands = query_by_prefix(seg)
    if not cands or top_char_from_candidate(cands[0]) != char:
        return seg, level_name(len(seg))
    
    shortest = seg
    for cut in range(1, len(seg)):
        shorter = seg[:-cut]
        cands = query_by_prefix(shorter)
        if cands and top_char_from_candidate(cands[0]) == char:
            shortest = shorter  # 还能更短
        else:
            break  # 不能再短了
    return shortest, level_name(len(shortest))


def verify_best(shortest, char):
    """验证 shortest 是否已是该字的最短编码"""
    if len(shortest) <= 1:
        return True, None
    one_less = shortest[:-1]
    cands = query_by_prefix(one_less)
    if not cands:
        return True, f"少一位 {one_less} → 无匹配"
    top = top_char_from_candidate(cands[0])
    return (top != char), f"少一位 {one_less} → {top}"


# ── 自动上字模拟 ──────────────────────────────────────────

def simulate_typing(code_str):
    """逐字符模拟输入过程，追踪自动上字事件。
    
    模拟前端 _on_input_change 中 auto_commit 的行为：
    - 对当前 processed（process_input 过滤后）调用 split_sequence
    - 若未拆分（单段）且 len > 3 且唯一非点候选 → 自动上字
    - 上字后 processed 清空，后续字符从头开始
    
    Returns:
        events: [(触发码, 上屏字), ...]
        residual: 最终残留码（可能为空，或需要空格手动上屏）
    """
    accumulated = ""
    events = []
    
    for ch in code_str:
        if ch not in CODE_CHARS:
            continue
        accumulated += ch
        
        processed = process_input(accumulated)
        if len(processed) <= 3:
            continue
        
        spl = split_sequence(processed)
        if "'" in spl:
            # 已被 split_sequence 拆分为多段 → 不触发自动上字
            continue
        
        cands = query_by_prefix(spl)
        if not cands:
            continue
        
        non_dot = [c for c in cands
                    if '.' not in (c[1:] if len(c) > 1 else '')]
        if len(non_dot) == 1:
            events.append((processed, non_dot[0][0]))
            accumulated = ""
    
    return events, process_input(accumulated)


def _auto_commit_analysis(code_str, results):
    """按空格段独立模拟自动上字。
    
    前端实际场景：用户带空格分段输入，空格触发
    _on_input_change → 上屏 + 清空缓冲区 → 下一段重新开始。
    因此自动上字也应逐段独立模拟，而非去空格整体模拟。
    """
    segments = code_str.split()
    result_idx = 0
    segment_results = []
    total_correct = 0
    total_triggered = 0
    problems = []

    for seg_raw in segments:
        segs = split_segs(seg_raw)
        expected = []
        for _ in segs:
            if result_idx < len(results):
                expected.append(results[result_idx])
                result_idx += 1

        events, residual = simulate_typing(seg_raw)

        comparisons = []
        seg_triggered = 0
        seg_correct = 0

        for i in range(len(events)):
            exp_info = expected[i] if i < len(expected) else {'char': '?', 'phrase': False}
            exp = exp_info['char']
            is_phrase = exp_info.get('phrase', False)
            act = events[i][1]
            trigger = events[i][0]

            if is_phrase:
                ok = None
            else:
                seg_triggered += 1
                total_triggered += 1
                ok = (act == exp)
                if ok:
                    seg_correct += 1
                    total_correct += 1
                else:
                    problems.append((exp, act, trigger, seg_raw))

            comparisons.append((exp, act, trigger, ok))

        # 处理残留码
        residual_info = []
        if residual:
            for seg in split_segs(residual):
                cands = query_by_prefix(seg)
                top = top_char_from_candidate(cands[0]) if cands else '?'
                full = find_full_code(top) if top != '?' else '?'
                residual_info.append({'seg': seg, 'char': top, 'full': full, 'len': len(seg)})

        # 未被自动上字覆盖的预期字（需手动空格/打全上屏）
        pending = []
        for i in range(len(events), len(expected)):
            pending.append(expected[i])

        segment_results.append({
            'seg_raw': seg_raw,
            'expected': expected,
            'events': events,
            'comparisons': comparisons,
            'residual': residual,
            'residual_info': residual_info,
            'pending': pending,
            'triggered': seg_triggered,
            'correct': seg_correct,
        })

    return {
        'segment_results': segment_results,
        'problems': problems,
        'total_triggered': total_triggered,
        'total_correct': total_correct,
    }


# ── 核心分析 ────────────────────────────────────────────

def analyze_sentence(text, code_str, verbose=True):
    """分析一句编码串。返回 results 列表。"""
    segments = code_str.split()
    results = []

    for seg_raw in segments:
        segs = split_segs(seg_raw)
        phrase = query_phrase(seg_raw)
        
        if phrase:
            # 词组命中 → 段内不再逐字拆分
            results.append({"seg": seg_raw, "char": phrase, "full": "(词组)",
                           "shortest": seg_raw, "level": "词语匹配", "phrase": True})
        else:
            for seg in segs:
                cands = query_by_prefix(seg)
                if not cands:
                    results.append({"seg": seg, "char": "?", "full": "?",
                                   "shortest": seg, "level": "无效码", "phrase": False})
                    continue
                char = top_char_from_candidate(cands[0])
                full = find_full_code(char)
                shortest, level = try_shorter(seg, char)
                results.append({"seg": seg, "char": char, "full": full,
                               "shortest": shortest, "level": level, "phrase": False})

    if verbose:
        auto = _auto_commit_analysis(code_str, results)
        _print_analysis(text, code_str, results, segments, auto)
    
    return results


def _print_analysis(text, code_str, results, segments, auto=None):
    W = 70
    print("=" * W)
    print(f"  原文: {text}")
    print(f"  编码: {code_str}")
    print("=" * W)

    # ── 表1: 逐字分解 ──
    print(f"\n  {'字':<6} {'段位':<10} {'全码':<8} {'输入':<10} {'级':<10} {'省'}")
    print("  " + "-" * 58)
    total_in, total_full = 0, 0
    for r in results:
        ch = r["char"]; seg = r["seg"]; full = r["full"]
        shortest = r["shortest"]; level = r["level"]
        if r["phrase"]:
            saved = "-"
            total_in += len(seg)
        else:
            saved = len(full) - len(shortest) if full != "?" else "?"
            total_in += len(shortest) if isinstance(shortest, str) else 0
            total_full += len(full) if full != "?" else 0
        print(f"  {ch:<6} {seg:<10} {full:<8} {shortest:<10} {level:<10} {saved}")
    
    print("  " + "-" * 58)
    pct = (1 - total_in / total_full) * 100 if total_full else 0
    print(f"  计: {total_in} 字符 vs 全码 {total_full} → 省 {pct:.0f}%")

    # ── 表2: 最短性验证 ──
    print(f"\n  {'字':<6} {'输入':<10} {'判定':<14} {'说明'}")
    print("  " + "-" * 52)
    for r in results:
        if r["phrase"]:
            print(f"  {'['+r['char']+']':<6} {r['seg']:<10} {'(词语匹配)':<14}")
            continue
        ch, seg, shortest = r["char"], r["seg"], r["shortest"]
        if len(shortest) < len(seg):
            print(f"  {ch:<6} {seg:<10} {'⚠ 可缩为:':<14} {shortest}（多打了 {len(seg)-len(shortest)} 码）")
        else:
            is_best, detail = verify_best(shortest, ch)
            status = "✓ 已最短" if is_best else "✗ 还能更短"
            print(f"  {ch:<6} {seg:<10} {status:<14} {detail}")

    # ── 表3: 空格必要性 ──
    if len(segments) > 1:
        print(f"\n  ▸ 空格必要性测试")
        no_space = code_str.replace(" ", "")
        ns_segs = split_segs(no_space)
        print(f"  无空格拆分: {split_sequence(no_space)} -> {ns_segs}")
        print(f"  {'子段':<10} {'首选字':<10} {'状态':<10}")
        print("  " + "-" * 34)
        errors = 0
        for ns in ns_segs:
            cands = query_by_prefix(ns)
            if cands:
                top = top_char_from_candidate(cands[0])
                status = "正常"
            else:
                top = "—"
                status = "✗ 无效码"
                errors += 1
            print(f"  {ns:<10} {top:<10} {status}")
        
        # 粘连点分析
        print(f"\n  粘连点:")
        for i, s in enumerate(segments):
            if i < len(segments) - 1:
                last = s[-1] if s else "?"
                nxt = segments[i+1][0] if segments[i+1] else "?"
                print(f"    {s} 末'{last}' + '{nxt}'头 {segments[i+1]}")
        print(f"  共 {errors} 段无效，正确 {len(ns_segs)-errors}/{len(ns_segs)}")
    else:
        print(f"\n  ▸ 单段，无空格风险")

    # ── 表4: 词组 ──
    phr = [(r["seg"], r["char"]) for r in results if r["phrase"]]
    if phr:
        print(f"\n  ▸ 词组匹配: {len(phr)} 处")
        for seg, w in phr:
            print(f"    {seg} → {w}")
    else:
        print(f"\n  ▸ 无词组匹配（纯逐字序列）")
    
    # ── 表5: 自动上字模拟 ──
    if auto:
        _print_auto_commit(auto, code_str)
    
    print()


def _print_auto_commit(auto, code_str):
    """输出自动上字模拟结果（逐空格段独立分析）"""
    print(f"\n  {'▸':>2} 自动上字模拟（含空格，逐段独立输入）")

    for sr in auto['segment_results']:
        seg_raw = sr['seg_raw']
        expected_str = ''.join(
            f'[{e["char"]}]' if e.get('phrase') else e['char']
            for e in sr['expected']
        )
        n_pending = len(sr['pending'])
        pending_note = f"（{n_pending}字不触发）" if n_pending else ''
        print(f"\n  段 \033[1m{seg_raw}\033[0m → {expected_str} {pending_note}")

        if sr['comparisons']:
            print(f"  {'触发码':<12} {'上屏':<8} {'预期':<8} {'判定':<6}")
            print("  " + "-" * 38)
            for exp, act, trigger, ok in sr['comparisons']:
                if ok is True:
                    flag = '✓'
                elif ok is False:
                    flag = '✗'
                else:
                    flag = '—'
                print(f"  {trigger:<12} {act:<8} {exp:<8} {flag}")

        # 未被自动上字覆盖的预期字
        if sr['pending']:
            for pe in sr['pending']:
                pchar = pe['char']
                if pe.get('phrase'):
                    continue
                full = pe.get('full', '?')
                fc = full if full not in ('?', '(词组)') else ''
                reason = _auto_skip_reason(pe, sr['residual_info'])
                print(f"  {'(未触发)':<12} {'—':<8} {pchar:<8} —   {reason}")

        # 残留码详情（仅在无自动上字事件且有待上屏字时展开）
        if not sr['comparisons'] and not sr['pending'] and sr['residual_info']:
            # 纯残留段（如词组后的剩余码）
            print(f"  (非自动上字场景)")

    # 汇总
    if auto['total_triggered'] > 0:
        n = auto['total_triggered']
        c = auto['total_correct']
        if auto['problems']:
            print(f"\n  触发 {n} 次，正确 {c}/{n}，{len(auto['problems'])} 次错误:")
            for exp, act, trigger, seg_raw in auto['problems']:
                print(f"    ✗ 段「{seg_raw}」→ {trigger} 上屏 {act}，期望 {exp}")
                # 分析原因
                full = find_full_code(exp)
                if full != '?':
                    print(f"      原因: 期望字「{exp}」全码={full} 与触发码 {trigger} 不是同一前缀/候选")
                print(f"      修复: 在「{exp}」码后加空格或打全码 {full} 锁定")
        else:
            print(f"\n  触发 {n} 次，全部正确 ✓")
    elif auto['total_triggered'] == 0:
        # 检查是否有任何段触发了自动上字
        any_events = any(sr['events'] for sr in auto['segment_results'])
        if not any_events:
            print(f"\n  无任何段触发自动上字（全部需空格或手动上屏）")


def _auto_skip_reason(pending_entry, residual_info):
    """分析某字未能自动上字的原因。

    自动上字条件：单段 + len>3 + 唯一非点候选。
    四种不触发情况：
      (A) len < 4 — 未达阈值
      (B) 实时缓冲区已被 split_sequence 拆为多段 — 前置有效段抢占缓冲区，
          该段从未以"唯一段"出现，即使其在隔离状态下满足触发条件
      (C) 候选不唯一 — 前四码有多个非点候选字（隔离状态下也不满足）
      (D) 编码过长自身可拆 — 该段经 split_sequence 自身被进一步拆分

    注意：(B) 与 (C) 的核心区别：
      (B) 是「缓冲区上下文」问题——该段单独查满足自动上字条件，
          但在实时输入中，前面的有效前缀（如 uj、go 等短编码）
          先被 split_sequence 识别为独立段，该段被划入后续段，
          从未以唯一段身份出现在缓冲区中。
      (C) 是「该段自身」问题——即使隔离查询，候选也不唯一。
    """
    full = pending_entry.get('full', '?')
    seg = pending_entry.get('seg', '')
    char = pending_entry.get('char', '?')

    # 尝试从残留信息中匹配到该字的编码段
    matched_ri = None
    for ri in residual_info:
        if ri['char'] == char:
            matched_ri = ri
            break

    if matched_ri:
        seg = matched_ri['seg']
        if matched_ri['len'] < 4:
            return f"len={matched_ri['len']}，未达4码不触发；空格或打全码 {full} 手动上屏"
        # len >= 4 → 先判断该段在隔离状态下是否会触发
        return _diagnose_non_trigger(seg, full)

    if seg and len(seg) < 4:
        return f"len={len(seg)}，未达4码不触发；空格或打全码 {full} 手动上屏"
    elif seg:
        return _diagnose_non_trigger(seg, full)
    else:
        return f"残留码未对应此字；空格或打全码 {full} 手动上屏"


def _diagnose_non_trigger(seg, full):
    """对 len>=4 但未触发自动上字的编码段给出精确原因。

    返回两种可能（该函数在隔离状态下查询段，无法知晓实时缓冲上下文）：
      - 该段在隔离状态下本可触发 → 说明不触发原因是 (B) 缓冲区抢占
      - 该段在隔离状态下也不满足条件 → 返回具体内部原因
    """
    spl = split_sequence(seg)
    if "'" in spl:
        return f"入 {seg} 后 split_sequence 自身拆为多段，不触发；空格或打全码 {full} 上屏"
    # 单段 → 检查候选唯一性
    cands = query_by_prefix(seg)
    non_dot = [c for c in cands if '.' not in (c[1:] if len(c) > 1 else '')]
    if len(non_dot) == 1:
        # 该段在隔离状态下满足自动上字条件。
        # 不触发的真实原因：缓冲区处于多字模式，split_sequence
        # 已将其拆为多段，自动上字只在单段时生效。
        return f"{seg} 缓冲区多字，不触发自动上字；空格或打全码 {full} 手动上屏"
    # 候选不唯一
    others = [c[0] for c in non_dot[1:]][:3]
    if others:
        other_str = ''.join(others)
        return f"{seg} 候选{len(non_dot)}字({other_str}…)，不唯一不触发；空格或打全码 {full} 手动上屏"
    else:
        return f"{seg} 候选{len(non_dot)}字，不唯一不触发；空格或打全码 {full} 手动上屏"


# ── 入口 ──────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="解书音形简打分析器")
    parser.add_argument("input", nargs="*", help="空格分隔的编码段")
    parser.add_argument("--all", "-a", action="store_true", help="跑副歌六句全套")
    parser.add_argument("--quiet", "-q", action="store_true", help="纯数据输出")
    args = parser.parse_args()

    if args.all:
        for text, code in DEMO_SENTENCES:
            analyze_sentence(text, code, verbose=not args.quiet)
        return
    if args.input:
        analyze_sentence("(用户输入)", " ".join(args.input), verbose=not args.quiet)
        return
    parser.print_help()
    print("\n  示例:")
    print('    python jd_analyze.py th3r row xnvsd ujuv3')
    print('    python jd_analyze.py "nyj3m vsdbkj4dk4"')
    print('    python jd_analyze.py --all')


if __name__ == "__main__":
    main()
