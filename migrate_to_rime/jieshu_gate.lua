-- jieshu_gate.lua —— 输入流检入（第十一轮·返工 2）
-- 目标（对齐 ime.py:772）：空输入流时只有 26 个小写字母能唤起 composing；
-- 数字、大写字母与其他可打印符号一律穿透到应用程序，原样半角上屏。
--
-- ⚠️ librime-lua 的 processor 返回值映射与 C++ 枚举不同（lua_gears.cc）：
--   lua 返回 0      → kRejected（终止链，按键穿透到应用）
--   lua 返回 1      → kAccepted（吞键）
--   lua 返回其他(2) → kNoop（继续 processor 链）
--
-- 本版 probe 全量打印每个到达 gate 的按键决策（上限 60 条），
-- 用于定位「数字 1 未被拦截仍进查字」时 gate 实际收到的 keycode。
-- ascii_mode 无需检查：西文模式下 ascii_composer（排在 gate 之前）
-- 对非 composing 按键直接 kRejected 终止链，gate 根本轮不到。

local K_PASS_THRU = 0 -- → kRejected：终止链，按键穿透到应用（原样上屏）
local K_CONTINUE = 2  -- → kNoop：交给后续 processor（key_binder/speller/...）

local probe_n = 0

local function probe(env, key, action)
  probe_n = probe_n + 1
  if probe_n > 60 then return end
  local ctx = env.engine.context
  local config = env.engine.schema.config
  local ch = key.keycode
  local ok_ascii, ascii = pcall(function() return ctx:get_option("ascii_mode") end)
  local c = (type(ch) == "number" and ch >= 0x20 and ch < 0x7f)
    and string.char(ch) or tostring(ch)
  log.info(string.format(
    "[jieshu_gate] #%d ch=%s(%s) input_len=%s input='%s' caret=%s ascii=%s/%s initials=%s -> %s",
    probe_n, c, tostring(ch),
    tostring(type(ctx.input) == "string" and #ctx.input or "nil"),
    tostring(ctx.input),
    tostring(ctx.caret_pos),
    tostring(ok_ascii), tostring(ascii),
    tostring(config:get_string("speller/initials")),
    action))
end

local function gate(key, env)
  local ctx = env.engine.context
  local ch = key.keycode
  local ok_ascii, ascii = pcall(function() return ctx:get_option("ascii_mode") end)
  local action
  if key:release() then
    action = "release"
  elseif key:ctrl() or key:alt() or key:super() then
    action = "combo"
  elseif ok_ascii and ascii then
    action = "ascii"          -- 西文模式：整体交给 ascii_composer，不拦
  elseif #ctx.input > 0 then
    action = "composing"
  elseif ch < 0x20 or ch >= 0x7f then
    action = "nonprint"
  elseif ch >= 0x61 and ch <= 0x7a then
    action = "alpha"
  else
    action = "REJECT"
  end
  local ret = (action == "REJECT") and K_PASS_THRU or K_CONTINUE
  probe(env, key, action .. "->" .. ret)
  return ret
end

return gate
