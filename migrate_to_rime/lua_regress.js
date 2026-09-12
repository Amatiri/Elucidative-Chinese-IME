/**
 * lua_regress.js —— jieshu_query.lua 离线回归（改动 lua 查询层后必跑）
 *
 * 用 fengari（纯 JS 的 Lua 5.3 虚拟机）真实加载本目录的 jieshu_query.lua，
 * 数据直接喂仓库真源 dict/dictionary.txt 与 dict/ciyu.txt（导出时是逐字节拷贝，
 * 与部署副本等价），把 build_candidates 的产物与 lua_regress.expected.tsv 快照逐字节比对。
 *
 * 快照来源：manager/dictionary_frontend.py 的真值（Python 前端即真源语义），
 * 首次生成时经 python 侧逐例对拍确认零差异。
 *
 * 用法：
 *   npm install fengari          # 装到任意 node 工作区
 *   node migrate_to_rime\lua_regress.js            # 比对，有差异 exit 1
 *   node migrate_to_rime\lua_regress.js --update   # 用当前 lua 产出刷新快照
 *   若 require("fengari") 解析不到，可设环境变量 FENGARI_PATH 指向 fengari 模块目录，
 *   或按 node 惯例设置 NODE_PATH。
 *
 * 说明：fengari 的 io.open 未实现，脚本内用内存桩喂数据；真源是 CRLF，
 *       RIME 的 io.open(f,"r") 走 Windows 文本模式会吃掉 \r，桩里做了同等处理。
 */
"use strict";
const fs = require("fs");
const path = require("path");

const BASE = __dirname;
const REPO_ROOT = path.dirname(BASE);
const CASES = path.join(BASE, "lua_regress.cases.txt");
const EXPECTED = path.join(BASE, "lua_regress.expected.tsv");
// 模块与数据都用仓库内真源：本目录 jieshu_query.lua + dict/ 码表
const MODULE = path.join(BASE, "jieshu_query.lua").replace(/\\/g, "/");
const NAV_MODULE = path.join(BASE, "jieshu_nav.lua").replace(/\\/g, "/");
const DATA_SINGLE = path.join(REPO_ROOT, "dict", "dictionary.txt").replace(/\\/g, "/");
const DATA_CIYU = path.join(REPO_ROOT, "dict", "ciyu.txt").replace(/\\/g, "/");
// 部署形态的虚拟资料夹：lua 内部拼 <user_data>/lua/data/jieshu_*.txt，桩按同一路径拦截
const STUB_USER_DATA = "RIME_USER_DATA_STUB";
const STUB_SINGLE = STUB_USER_DATA + "/lua/data/jieshu_single.txt";
const STUB_CIYU = STUB_USER_DATA + "/lua/data/jieshu_ciyu.txt";

function requireFengari() {
  const candidates = ["fengari"];
  if (process.env.FENGARI_PATH) candidates.push(process.env.FENGARI_PATH);
  for (const c of candidates) {
    try {
      return require(c);
    } catch (e) {
      /* try next */
    }
  }
  console.error(
    "[lua_regress] 找不到 fengari。先执行：npm install fengari\n" +
      "（或设环境变量 FENGARI_PATH / NODE_PATH 指向含 fengari 的 node_modules。）"
  );
  process.exit(2);
}

const { lua, lauxlib, lualib, to_luastring, to_jsstring } = requireFengari();

const DRIVER = `
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
          local nl = content:find("\\n", pos, true)
          local line
          if nl then
            line = content:sub(pos, nl - 1)
            pos = nl + 1
          else
            line = content:sub(pos)
            pos = #content + 1
          end
          line = line:gsub("\\r$", "")
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
__cases_raw = __cases_raw:gsub("^" .. string.char(239, 187, 191), ""):gsub("\\r", "")
for c in __cases_raw:gmatch("[^\\n]+") do cases[#cases + 1] = c end

local out = {}
for _, c in ipairs(cases) do
  -- P4-E 开关态前缀（可叠加在任意用例前，供开关矩阵用例使用）：
  --   op<位图> <原用例>   位图个位 = 自动上字，十位 = 优先上词；1=开 0=关
  --   例：op10 bu44ba13 → 自动上字关、优先上词开
  -- 无前缀 = 全开（与既有 107 例语义完全一致，快照不受影响）
  local rest = c
  local ac_on, pp_on = true, true
  local bits, tail = rest:match("^op(%d%d?)%s+(.*)$")
  if bits then
    ac_on = bits:sub(-1) == "1"
    -- 判 bit 长度要写成嵌套 if，不能写 "len>=2 and (..) or true" —— Lua 的 and/or
    -- 链在 and 段为 false 时会落到 or true，把「关」吃成「开」（十位读不出 0）。
    pp_on = true
    if #bits >= 2 then pp_on = (bits:sub(-2, -2) == "1") end
    rest = tail
  end
  local ac_input = rest:match("^ac%s+(.*)$")
  local nav_conf, nav_input = rest:match("^nav%s+(%d+)%s+(.*)$")
  if ac_input then
    -- 按键级判定：开关关闭时 jieshu_autocommit 整段不动作
    local idx, txt = __jieshu_test.auto_commit_target(ac_input)
    local fired = ac_on and (idx ~= nil)
    out[#out + 1] = c .. "\\t" .. (fired and idx or -1) .. "\\t" .. (fired and (txt or "") or "")
  elseif nav_conf then
    local gate, target, has, head = __jieshu_nav_test.nav_scan(nav_input, tonumber(nav_conf))
    out[#out + 1] = c .. "\\t" .. (gate and 1 or 0) .. "\\t" .. (has and 1 or 0) .. "\\t"
      .. tostring(target ~= nil and target or -1) .. "\\t"
      .. tostring(head ~= nil and head or -1)
  else
    local start, input = rest:match("^#(%d+)%s+(.*)$")
    if start then start = tonumber(start) else start = 0 input = rest end
    -- 第四参 = 优先上词；第五参 = 自动上字（同时门控「预」提示，见 build_candidates 头注）
    local cands = __jieshu_test.build_candidates(input, start,
      (start == 0) and input or nil, pp_on, ac_on)
    local t = {}
    for _, x in ipairs(cands) do
      t[#t + 1] = x[1] .. "|" .. (x[2] or "")
    end
    out[#out + 1] = c .. "\\t" .. #cands .. "\\t" .. table.concat(t, "\\t")
  end
end
__result = table.concat(out, "\\n")
`;

function runLua() {
  const L = lauxlib.luaL_newstate();
  lualib.luaL_openlibs(L);
  const setStr = (name, s) => {
    lua.lua_pushstring(L, to_luastring(s));
    lua.lua_setglobal(L, to_luastring(name));
  };
  const fail = (where) => {
    console.error("[lua_regress] " + where + ": " + to_jsstring(lua.lua_tostring(L, -1)));
    process.exit(1);
  };
  setStr("__dir", STUB_USER_DATA);
  setStr("__src", fs.readFileSync(MODULE, "utf8"));
  setStr("__nav_src", fs.readFileSync(NAV_MODULE, "utf8"));
  setStr("__cases_raw", fs.readFileSync(CASES, "utf8"));
  setStr("__p1", STUB_SINGLE);
  setStr("__d1", fs.readFileSync(DATA_SINGLE, "utf8"));
  setStr("__p2", STUB_CIYU);
  setStr("__d2", fs.readFileSync(DATA_CIYU, "utf8"));
  let r = lauxlib.luaL_dostring(
    L,
    to_luastring("_G.__files = {}; _G.__files[__p1] = __d1; _G.__files[__p2] = __d2;")
  );
  if (r !== lua.LUA_OK) fail("prelude");
  r = lauxlib.luaL_dostring(L, to_luastring(DRIVER));
  if (r !== lua.LUA_OK) fail("lua");
  lua.lua_getglobal(L, to_luastring("__result"));
  return to_jsstring(lua.lua_tostring(L, -1));
}

// 读快照/用例时统一去 BOM、CRLF→LF：core.autocrlf=true 的检出会把它们写成 CRLF+BOM，
// 而 Lua 侧按 "\n" 切行、逐字节比对，混进来就会整片对不上（表现为「缺少产出」）。
function readNormalized(p) {
  return fs.readFileSync(p, "utf8").replace(/^\uFEFF/, "").replace(/\r\n/g, "\n");
}

function parse(text) {
  const map = {};
  for (const line of text.split("\n")) {
    if (!line.trim()) continue;
    const p = line.split("\t");
    map[p[0]] = { count: parseInt(p[1], 10), cands: p.slice(2).filter((s) => s !== "") };
  }
  return map;
}

const update = process.argv.includes("--update");
const actualText = runLua();

if (update) {
  fs.writeFileSync(EXPECTED, actualText + "\n", "utf8");
  console.log("[lua_regress] 快照已更新：" + EXPECTED);
  process.exit(0);
}

if (!fs.existsSync(EXPECTED)) {
  console.error("[lua_regress] 缺少快照，先跑一次 --update");
  process.exit(2);
}

const exp = parse(readNormalized(EXPECTED));
const act = parse(actualText);
const cases = fs
  .readFileSync(CASES, "utf8")
  .replace(/^\uFEFF/, "")
  .split("\n")
  .map((s) => s.trim())
  .filter((s) => s !== "");

let diff = 0;
for (const c of cases) {
  const e = exp[c];
  const a = act[c];
  if (!a) {
    console.log("!! " + c + " 缺少产出");
    diff++;
    continue;
  }
  if (!e) {
    console.log("!! " + c + " 不在快照里（--update 刷新）");
    diff++;
    continue;
  }
  if (e.count !== a.count || e.cands.join("") !== a.cands.join("")) {
    console.log("!! " + c + "\n   期望 " + e.count + " 条 " + e.cands.slice(0, 3).join(" / ") +
      "\n   实际 " + a.count + " 条 " + a.cands.slice(0, 3).join(" / "));
    diff++;
  }
}
console.log("[lua_regress] 用例 " + cases.length + "，差异 " + diff);
process.exit(diff === 0 ? 0 : 1);
