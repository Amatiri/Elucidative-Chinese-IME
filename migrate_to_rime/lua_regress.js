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

local f = assert(load(__src, "@jieshu_query.lua"))
f()
__jieshu_test.load()

local cases = {}
for c in __cases_raw:gmatch("[^\\n]+") do cases[#cases + 1] = c end

local out = {}
for _, c in ipairs(cases) do
  local cands = __jieshu_test.build_candidates(c)
  local t = {}
  for _, x in ipairs(cands) do
    t[#t + 1] = x[1] .. "|" .. (x[2] or "")
  end
  out[#out + 1] = c .. "\\t" .. #cands .. "\\t" .. table.concat(t, "\\t")
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

const exp = parse(fs.readFileSync(EXPECTED, "utf8"));
const act = parse(actualText);
const cases = fs
  .readFileSync(CASES, "utf8")
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
