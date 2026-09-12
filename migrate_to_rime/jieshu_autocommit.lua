-- jieshu_autocommit.lua —— P4-D 自动上字（>3 码且唯一候选自动上屏）
--
-- 判定完全在 Lua 侧（jieshu_query 的 auto_commit_target，那里解释了为什么不能用
-- librime 原生 speller/auto_select）；本组件只负责「何时问」与「怎么上屏」。
--
-- 时机：lua processor 在按键到达时先跑，此刻 ctx.input 还是**上一次按键之后**的状态，
-- 所以判定命中时上屏的是上一键打出的那串码，当前键随后照常走链（这一次击键不受影响）。
-- 连打时无感（上屏早于新字出现）；停手时编码保留、按空格上屏（首选即目标字）。
--
-- 必须排在 jieshu_gate **之前**：这里 select() 上屏会 Clear()（清空 input），
-- 当前键要继续流到 gate，由 gate 按「空输入流」规则处置（小写字母放行、
-- 数字/大写/符号拦截穿透）—— 这才等价于 ime.py「自动上字后输入框已清空」的状态。
-- 若排在 gate 之后，gate 已用清空前的输入判过一轮，当前键会被当成码字符
-- 推进刚清空的输入流。
--
-- 只对「码字符」触发：选字键（Shift+1~5 → !@#$%）、方向键、Esc、Backspace、
-- `=`/`-` 一律不触发 —— 用户按这些键说明想操作当前编码/候选，不该被自动上字截胡。
--
-- 空格（0x20）**不在**白名单（2026-09-12 修复实机 bug①「bu44+空格 → 不 」）：
-- 若由本组件 commit，空格随后在已 Clear 的空输入流上被 gate REJECT 穿透到应用，
-- 多出一个字面空格。改走 express_editor 原生路径：有输入流时空格经 gate（composing
-- 放行）到 express_editor 的 Confirm → ConfirmCurrentSelection() 上屏当前高亮候选。
-- 全码表统计背书（14642 个可达输入，_tmp_hit_stat 实测）：auto_commit_target 判定
-- 命中时目标候选恒在第 0 位（高亮默认位），原生上屏即目标字；且用户翻页后空格
-- 上屏的是翻到的候选，尊重用户的主动选择。
--
-- `.`（0x2e）保留触发但带 peek（2026-09-12 修复实机 bug②「ba13. → 八.」）：
-- `.` 有码字符身份（补码引导，ba13. 是捌的码）。预上字状态下按 `.` 先试
-- 「并入编码重判」——auto_commit_target(input..".") 命中（ba13.→捌）则不 commit，
-- 让 `.` 进输入流重新判定；不命中（bu44. 无此码形态）则照常上屏目标字，`.` 随后
-- 在空输入流穿透（既有标点行为）。
--
-- 返回值映射与 C++ 枚举相反（lua_gears.cc，见 jieshu_gate.lua 头注）：
--   0 = kRejected（终止键链、按键穿透到应用）；1 = kAccepted（吞键）；2 = kNoop（继续链）。
-- 本组件是旁路动作，一律返回 2，绝不吞键。
--
-- P4-E 开关「自动上字」（switches: jieshu_auto_commit，states [ 字, · ]，默认开）：
-- 对齐 ime.py 的 auto_commit_enabled（ime.py:48 默认 "1"，ime.py:585 处判定）。
-- 关闭时本组件整段不动作 —— 判定与上屏都不跑，编码照常留在输入流里按空格上屏。
-- 查询层的「预」提示同步由 jieshu_translator 用同一开关关掉（见 jieshu_query.lua
-- 的 option_on），否则会出现「挂着预标记却永不自动上屏」的矛盾状态。

local K_CONTINUE = 2

-- 触发用键：a-z（0x61-0x7a）、0-9（0x30-0x39）、`;`（0x3b）、`.`（0x2e）、`'`（0x27）。
-- 即 speller/alphabet 全集（空格除外，见上）；键位依据与 CODE_CHARS 同源（config.CODE_CHARS）。
local function triggers_autocommit(kc)
  if kc >= 0x30 and kc <= 0x39 then return true end
  if kc >= 0x61 and kc <= 0x7a then return true end
  return kc == 0x3b or kc == 0x2e or kc == 0x27
end

-- 查询层（同目录 jieshu_query.lua）经全局表 jieshu_query_api 借出 auto_commit_target
-- （函数值不能挂字段）。若本组件先加载则 require 一次查询层触发赋值 —— require 走
-- <user_data>\lua\?.lua（librime-lua modules.cc 设置 package.path），与 translator
-- 组件共用同一份缓存，不产生第二份数据。
local api = nil
local warned_api = false

local function get_api()
  if api then return api end
  api = jieshu_query_api
  if type(api) ~= "table" then
    pcall(require, "jieshu_query")
    api = jieshu_query_api
  end
  if type(api) ~= "table" then api = nil end
  return api
end

-- P4-E 开关读取（与 jieshu_query.lua 的 option_on / auto_commit_on 逐字一致，三处必须同步）：
--   · `Context:get_option` 在 lua 侧由 WRAPMEM 直通 C++ 成员，**永远返回 bool，不会返回 nil**。
--   · 默认态由 schema 的 `reset` 决定（engine.cc::InitializeOptions 只在 reset>=0 时
--     set_option；不写 reset 的开关根本不 set_option，读到的就是 false）。
--     本方案写了 `reset: 1` → 默认开，对齐 ime.py:48。
--   ⇒ 无需三态兜底：true=开、false=关，直接照用。
--     `pcall` 只防「ctx/方法不可用」（测试桩、引擎异常），失败时按 ime.py 默认值 true 走。
local function auto_commit_on(ctx)
  if not ctx then return true end
  local ok, v = pcall(function() return ctx:get_option("jieshu_auto_commit") end)
  if not ok then return true end
  return v and true or false
end

local function autocommit(key, env)
  local ctx = env.engine and env.engine.context
  if not ctx then return K_CONTINUE end
  -- 抬键事件必须放过：Weasel 会把 release 也送进来（gate/nav 同样显式处理），
  -- 不拦的话一次按键会判定两回。
  if key:release() then return K_CONTINUE end
  -- Ctrl/Alt/Super 组合键一律不碰（保留系统与其他组件的手感）
  if key:ctrl() or key:alt() or key:super() then return K_CONTINUE end
  if not triggers_autocommit(key.keycode) then return K_CONTINUE end
  local ok_c, composing = pcall(function() return ctx:is_composing() end)
  if not ok_c or not composing then return K_CONTINUE end
  -- 西文模式（含 ascii_composer 的 inline_ascii 临时态）整体放行
  local ok_a, ascii = pcall(function() return ctx:get_option("ascii_mode") end)
  if ok_a and ascii then return K_CONTINUE end
  -- P4-E 开关：关掉自动上字就整段不动作（判定与上屏都不跑）。
  -- 三态判定见上面的 auto_commit_on —— nil（option 从未被 set_option 过）按默认态开。
  if not auto_commit_on(ctx) then return K_CONTINUE end

  local a = get_api()
  if not a or not a.auto_commit_target then
    if not warned_api then
      warned_api = true
      if log and log.warning then
        log.warning("[jieshu_autocommit] 查询层 api 未就绪，自动上字暂不生效")
      end
    end
    return K_CONTINUE
  end

  -- 注意 index 可能是 0（Lua 里 0 为真），故判 nil 而非真假。
  local index, text = a.auto_commit_target(ctx.input or "")
  if index == nil then return K_CONTINUE end
  -- `.` peek：预上字状态下按 `.`，先试「并入编码重判」——重判命中（ba13.→捌）
  -- 则不 commit，放 `.` 进输入流重新判定（候选与「预」提示随之刷新为捌）；
  -- 重判不命中（bu44. 这类无补码形态）则照常 commit 目标字，`.` 在空输入流穿透。
  if key.keycode == 0x2e then
    local idx2 = a.auto_commit_target((ctx.input or "") .. ".")
    if idx2 ~= nil then return K_CONTINUE end
  end
  -- select(index) 会触发 select_notifier → engine.cc::OnSelect：段铺到输入末尾
  -- → 段标 kConfirmed → `_auto_commit`（ExpressEditor 构造时置 true）→ ctx->Commit()
  -- 上屏该候选文本。与 librime 原生 auto_select 的上屏路径完全同一条。
  -- 下标越界时 Context::Select 返回 false，天然安全（不上屏）。
  local ok_s, selected = pcall(function() return ctx:select(index) end)
  if not ok_s or not selected then
    if log and log.warning then
      log.warning("[jieshu_autocommit] 候选下标越界，跳过自动上字："
        .. tostring(text) .. " idx=" .. tostring(index))
    end
  end
  return K_CONTINUE
end

-- 测试面（离线回归用：先置 __jieshu_autocommit_test_mode 再加载；线上不引用）
if __jieshu_autocommit_test_mode then
  __jieshu_autocommit_test = {
    get_api = get_api,
    triggers_autocommit = triggers_autocommit,
    autocommit = autocommit,
    auto_commit_on = auto_commit_on,
  }
end

return autocommit
