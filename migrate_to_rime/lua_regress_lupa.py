"""
lua_regress_lupa.py —— jieshu_query.lua 离线回归的 Python 通道（lupa 真加载）

与 lua_regress.js 同一份 DRIVER 逻辑、同一份用例与快照，只是宿主换成 lupa
（本机装有 lupa，fengari 未必存在）。改 jieshu_query.lua 后跑哪个都行，
推荐两个都过；两者对拍互证（fengari=Lua5.3 语义，lupa=C 真 Lua）。

用法：
  python migrate_to_rime\\lua_regress_lupa.py            # 比对快照，有差异 exit 1
  python migrate_to_rime\\lua_regress_lupa.py --update   # 刷新快照
"""
import io
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CASES = os.path.join(SCRIPT_DIR, "lua_regress.cases.txt")
EXPECTED = os.path.join(SCRIPT_DIR, "lua_regress.expected.tsv")
MODULE = os.path.join(SCRIPT_DIR, "jieshu_query.lua")
NAV_MODULE = os.path.join(SCRIPT_DIR, "jieshu_nav.lua")
DATA_SINGLE = os.path.join(REPO_ROOT, "dict", "dictionary.txt")
DATA_CIYU = os.path.join(REPO_ROOT, "dict", "ciyu.txt")
STUB_USER_DATA = "RIME_USER_DATA_STUB"
STUB_SINGLE = STUB_USER_DATA + "/lua/data/jieshu_single.txt"
STUB_CIYU = STUB_USER_DATA + "/lua/data/jieshu_ciyu.txt"

# 与 lua_regress.js 的 DRIVER 保持逐字一致（改一处必须同步另一处）
DRIVER = r"""
__jieshu_test_mode = true
__jieshu_nav_test_mode = true
rime_api = { get_user_data_dir = function() return __dir end }
log = { info = function() end, error = function() end, warning = function() end }

io = {
  open = function(p, mode)
    local content = __files[p]
    if not content then return nil end
    local pos = 1
    return {
      lines = function()
        return function()
          if pos > #content then return nil end
          local nl = content:find("\n", pos, true)
          local line
          if nl then
            line = content:sub(pos, nl - 1)
            pos = nl + 1
          else
            line = content:sub(pos)
            pos = #content + 1
          end
          line = line:gsub("\r$", "")
          return line
        end
      end,
      close = function() end,
    }
  end,
}

local query_chunk = assert(load(__src, "@jieshu_query.lua"))
query_chunk()
__jieshu_test.load()

local real_require = require
require = function(name)
  if name == "jieshu_query" then return query_chunk end
  return real_require(name)
end
assert(load(__nav_src, "@jieshu_nav.lua"))()

local cases = {}
for c in __cases_raw:gmatch("[^\n]+") do cases[#cases + 1] = c end

local out = {}
for _, c in ipairs(cases) do
  local nav_conf, nav_input = c:match("^nav%s+(%d+)%s+(.*)$")
  if nav_conf then
    local t = __jieshu_nav_test.next_target(
      __jieshu_test.part_boundaries(nav_input), tonumber(nav_conf))
    out[#out + 1] = c .. "\t" .. tostring(t ~= nil and t or -1) .. "\t"
  else
    local start, input = c:match("^#(%d+)%s+(.*)$")
    if start then start = tonumber(start) else start = 0 input = c end
    local cands = __jieshu_test.build_candidates(input, start)
    local t = {}
    for _, x in ipairs(cands) do
      t[#t + 1] = x[1] .. "|" .. (x[2] or "")
    end
    out[#out + 1] = c .. "\t" .. #cands .. "\t" .. table.concat(t, "\t")
  end
end
__result = table.concat(out, "\n")
"""


def run_lua():
    import lupa

    lua = lupa.LuaRuntime()
    g = lua.globals()

    def read(path):
        with io.open(path, "r", encoding="utf-8") as f:
            return f.read()

    g.__dir = STUB_USER_DATA
    g.__src = read(MODULE)
    g.__nav_src = read(NAV_MODULE)
    g.__cases_raw = read(CASES)
    g.__p1 = STUB_SINGLE
    g.__d1 = read(DATA_SINGLE)
    g.__p2 = STUB_CIYU
    g.__d2 = read(DATA_CIYU)
    lua.execute("_G.__files = {}; _G.__files[__p1] = __d1; _G.__files[__p2] = __d2;")
    lua.execute(DRIVER)
    return str(lua.globals().__result)


def parse(text):
    out = {}
    for line in text.split("\n"):
        if not line.strip():
            continue
        parts = line.split("\t")
        out[parts[0]] = (int(parts[1]), [p for p in parts[2:] if p != ""])
    return out


def main():
    update = "--update" in sys.argv
    actual = run_lua()
    if update:
        with io.open(EXPECTED, "w", encoding="utf-8", newline="\n") as f:
            f.write(actual + "\n")
        print("[lua_regress] 快照已更新：", EXPECTED)
        return 0
    if not os.path.isfile(EXPECTED):
        print("[lua_regress] 缺少快照，先跑一次 --update", file=sys.stderr)
        return 2
    exp = parse(io.open(EXPECTED, encoding="utf-8").read())
    act = parse(actual)
    cases = [s.strip() for s in
             io.open(CASES, encoding="utf-8").read().split("\n") if s.strip()]
    diff = 0
    for c in cases:
        e, a = exp.get(c), act.get(c)
        if a is None:
            print("!!", c, "缺少产出")
            diff += 1
            continue
        if e is None:
            print("!!", c, "不在快照里（--update 刷新）")
            diff += 1
            continue
        if e[0] != a[0] or e[1] != a[1]:
            print("!!", c, "\n   期望", e[0], "条", " / ".join(e[1][:3]),
                  "\n   实际", a[0], "条", " / ".join(a[1][:3]))
            diff += 1
    print("[lua_regress/lupa] 用例", len(cases), "，差异", diff)
    return 0 if diff == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
