# -*- coding: utf-8 -*-
"""
一次性验证脚本：对比 git HEAD 旧版 dictionary_frontend 与优化新版的行为等价性。
- old_disk: git HEAD 原样旧模块（真盘读取），用于抽样对照
- old_ref : 旧源码仅把 query_by_prefix 的文件迭代源换为内存行缓存（匹配逻辑逐字节不变），
            用于全量前缀对照，消除 I/O 等待
- new     : 优化后的 manager.dictionary_frontend
用法：从项目根目录运行  python agent_workspace/verify_query_opt.py
"""
import os
import sys
import subprocess
import time
import types
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)
sys.path.insert(0, ROOT)

# ---------- 旧版源码（git HEAD，未经修改） ----------
src = subprocess.run(
    ['git', 'show', 'HEAD:manager/dictionary_frontend.py'],
    capture_output=True, text=True, encoding='utf-8', cwd=ROOT
).stdout
assert src, "无法从 git 读取旧版 dictionary_frontend.py"

old_disk = types.ModuleType('old_disk')
exec(compile(src, 'old_disk.py', 'exec'), old_disk.__dict__)

# old_ref：同一份源码，仅将 query_by_prefix 内的 `for line in f:`（文件中最后一次出现，
# query_phrase 里的那处在前）替换为内存行迭代，其余逐字节不变
pos = src.rindex('for line in f:')
src_ref = src[:pos] + 'for line in _LINES:' + src[pos + len('for line in f:'):]
with open('dictionary.txt', encoding='utf-8') as f:
    _lines = f.readlines()
old_ref = types.ModuleType('old_ref')
old_ref_ns = old_ref.__dict__
exec(compile(src_ref, 'old_ref.py', 'exec'), old_ref_ns)
old_ref_ns['_LINES'] = _lines

# ---------- 新版模块 ----------
from manager import dictionary_frontend as new

# ---------- 读取码表，构造前缀全集 ----------
codes = []
with open('dictionary.txt', encoding='utf-8') as f:
    for line in f:
        parts = line.strip().split(' ', 1)
        if len(parts) == 2 and parts[1]:
            codes.append(parts[1])

prefixes = set()
for code in codes:
    # 1) 每个编码的所有前缀（覆盖纯前缀分支、点补码分支、startswith 边界）
    for k in range(1, len(code) + 1):
        prefixes.add(code[:k])
    # 2) 副码a分支：四码 + 'a'
    if len(code) >= 4:
        prefixes.add(code[:4] + 'a')
        # 3) 四码+a+补码（点在第4位的编码，如 ba13. -> ba13a. / ba13a.w）
        if len(code) > 4 and code[4] == '.':
            for k in range(5, len(code) + 1):
                prefixes.add(code[:4] + 'a' + code[4:k])
        # 点在第5位的也加 a 变体（两侧都应无命中，验证不误报）
        if len(code) > 5 and code[5] == '.':
            prefixes.add(code[:4] + 'a.')

# 4) 垃圾前缀 / 边界前缀
prefixes.update([
    'z', 'zz', 'zzz', 'zzzz', 'zzzza', 'zzzzazz', 'q1', '1', ';', '.',
    'aaaa', 'aaaaa', 'aaaaaa', 'b.b', 'a1.', 'zz1.w', 'p;2', 'p;25',
])
prefixes.discard('')
prefixes = sorted(prefixes)
print(f"码条数: {len(codes)} | 前缀总数: {len(prefixes)}")

fail = 0
checked = 0

# ---------- 步骤0：old_disk ≡ old_ref 抽样（证明内存行替换不失真） ----------
random.seed(1)
sample = random.sample(prefixes, 400)
for p in sample:
    if old_disk.query_by_prefix(p, 0, 5) != old_ref.query_by_prefix(p, 0, 5):
        fail += 1
        print(f"[DIFF disk-vs-ref] {p!r}")
print(f"步骤0 磁盘版/内存版旧实现抽样 400 组, 差异 {fail}")

# ---------- 步骤1：全前缀 x 常用组合 ----------
t0 = time.perf_counter()
for p in prefixes:
    for start_idx, count in ((0, 5), (0, 1)):
        checked += 1
        r_old = old_ref.query_by_prefix(p, start_idx, count)
        r_new = new.query_by_prefix(p, start_idx, count)
        if r_old != r_new:
            fail += 1
            if fail <= 10:
                print(f"[DIFF] prefix={p!r} start={start_idx} count={count}\n  old={r_old}\n  new={r_new}")
print(f"步骤1 全前缀 x (0,5)/(0,1): {checked} 组, 累计差异 {fail}, {time.perf_counter() - t0:.1f}s")

# ---------- 步骤2：深分页/奇异切片组合（抽样子集） ----------
subset = prefixes[::6]
t0 = time.perf_counter()
for p in subset:
    for start_idx, count in ((5, 5), (7, 2), (100, 5)):
        checked += 1
        r_old = old_ref.query_by_prefix(p, start_idx, count)
        r_new = new.query_by_prefix(p, start_idx, count)
        if r_old != r_new:
            fail += 1
            if fail <= 10:
                print(f"[DIFF] prefix={p!r} start={start_idx} count={count}\n  old={r_old}\n  new={r_new}")
print(f"步骤2 子集 x 深分页组合: 累计 {checked} 组, 累计差异 {fail}, {time.perf_counter() - t0:.1f}s")

# ---------- 步骤3：get_entry_count ----------
old_count = len(_lines)
new_count = new.get_entry_count()
ok = old_count == new_count
print(f"步骤3 get_entry_count: 旧={old_count} 新={new_count} {'一致' if ok else '不一致!'}")
if not ok:
    fail += 1

# ---------- 步骤4：query_single_char / query_multi_chars ----------
fail2 = 0
for p in prefixes[::5]:
    o = old_ref.query_single_char(p, 0)
    n = new.query_single_char(p, 0)
    if o != n:
        fail2 += 1
        print(f"[DIFF single_char] {p!r}: old={o!r} new={n!r}")
    # 新用法 count=1：首候选必须与旧结果首选一致
    n1 = new.query_single_char(p, 0, 1)
    first_old = o.split('/')[0] if o else ''
    if bool(o) != bool(n1) or n1 != first_old:
        fail2 += 1
        print(f"[DIFF count=1] {p!r}: old首位={first_old!r} new={n1!r}")

# 多字预览：旧版内部 count=5 vs 新版内部 count=1，输出应一致
random.seed(42)
for _ in range(300):
    n_parts = random.randint(2, 4)
    parts = [random.choice(codes)[:random.choice([2, 3, 4])] for _ in range(n_parts)]
    s = "'".join(parts)
    o = old_ref.query_multi_chars(s)
    n = new.query_multi_chars(s)
    if o != n:
        fail2 += 1
        print(f"[DIFF multi] {s!r}: old={o!r} new={n!r}")
print(f"步骤4 single_char/multi_chars 对比: 差异 {fail2} 处")

# ---------- 步骤5：性能对比（新版含索引构建开销） ----------
perf_prefixes = [c[:4] for c in codes[::8]]
t0 = time.perf_counter()
for p in perf_prefixes:
    old_disk.query_by_prefix(p)
t_old = time.perf_counter() - t0
t0 = time.perf_counter()
for p in perf_prefixes:
    new.query_by_prefix(p)
t_new = time.perf_counter() - t0
t0 = time.perf_counter()
for i in range(5):
    old_disk.query_by_prefix('y', i * 5)
t_old_page = time.perf_counter() - t0
t0 = time.perf_counter()
for i in range(5):
    new.query_by_prefix('y', i * 5)
t_new_page = time.perf_counter() - t0

print(f"\n步骤5 性能: {len(perf_prefixes)} 次四码查询  旧 {t_old:.3f}s -> 新 {t_new:.3f}s "
      f"({t_old / max(t_new, 1e-9):.0f}x)")
print(f"步骤5 性能: 前缀'y'翻5页  旧 {t_old_page:.3f}s -> 新 {t_new_page:.3f}s "
      f"({t_old_page / max(t_new_page, 1e-9):.0f}x)")

total_fail = fail + fail2
print("\n总结:", "全部等价，验证通过" if total_fail == 0 else f"存在差异 {total_fail} 处")
