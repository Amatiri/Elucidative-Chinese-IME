-- jieshu_nav.lua —— P4-B 逐字定位（`=` / `-`）。挂在 processor 链首的 jieshu_gate 之后。
--
-- 目标：替掉「手按 Left 数步把光标挪到拆分点」，对齐 ime.py 的 navigate_parts 手感。
--
--   `=`  把光标移到「第一个未确认段的末尾」= 最小的 拆分点 > 已确认位置。
--        RIME 的 Compose 按光标截断输入（engine.cc:158：composition 输入 = input()[0:caret]），
--        于是该段被单独翻出来，候选即该字的前缀候选；再往下选由 P4-A 的 partial 拆分
--        （段首已确认时只出首个 part 的候选）自动接手，故 `=` 每次按都是「回到当前待选段」，
--        天然幂等。
--   `-`  等同 Backspace（ReopenPreviousSelection）：回退上一个已确认段并重新出候选。
--        这是 RIME 段模型里唯一有意义的「往回」动作 —— 未确认段永远是「光标前那一段」，
--        不存在 ime.py 里可以回跳的「上一个未解析段」。顺带消掉一个坑：`-` 不改绑的话会
--        落到 express_editor 的 DirectCommit（editor.cc:216），把原码直接上屏。
--
-- 键位冲突（已核实本机 default.yaml，万象）：`-`/`=` 被绑成 Page_Up/Page_Down。
-- 本 processor 排在 key_binder **之前**，故 composing 时优先按逐字定位解释；翻页仍可用 ↑↓。
--
-- 返回值映射与 C++ 枚举相反（lua_gears.cc，见 jieshu_gate.lua 头注）：
--   0 = kRejected（终止链、按键穿透到应用）；1 = kAccepted（吞键）；2 = kNoop（继续链）。

local K_ACCEPT = 1
local K_CONTINUE = 2
local K_EQUAL = 0x003d   -- XK_equal
local K_MINUS = 0x002d   -- XK_minus

-- 查询层（同目录 jieshu_query.lua）暴露的共享工具：process_input / split_sequence /
-- part_boundaries，经全局表 jieshu_query_api 传递（函数值不能挂字段）。若本组件先加载，
-- 则 require 一次查询层触发赋值 —— require 走 <user_data>\lua\?.lua（librime-lua
-- modules.cc 设置 package.path），与 translator 组件共用同一份缓存，不产生第二份数据。
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

-- 纯函数（便于离线回归）：返回「第一个未确认段的末尾」；nil = 没有可跳的目标。
local function next_target(bounds, confirmed)
  for i = 1, #bounds do
    if bounds[i] > confirmed then return bounds[i] end
  end
  return nil
end

-- 已确认前缀的字节长度。
-- Composition 的 lua 绑定只暴露 back()（types.cc 的 CompReg），而稳定态下最后一段必然紧贴
-- 已确认前缀（Segmentation::Reset 保留已确认段 + Trim/Forward，segmentation.cc:57-76/114-130），
-- 故用 back() 判定：段已确认 → 取段尾；未确认 → 取段首（= 已确认前缀长度）。
local function confirmed_pos(ctx)
  local comp = ctx.composition
  if not comp then return 0 end
  local ok, seg = pcall(function() return comp:back() end)
  if not ok or not seg then return 0 end
  local st = seg.status or ""
  if st == "kSelected" or st == "kConfirmed" then return seg._end or 0 end
  return seg.start or 0
end

local function nav(key, env)
  local ctx = env.engine.context
  if not ctx or not ctx:is_composing() then return K_CONTINUE end
  -- 抬键事件必须放过：Weasel 会把 release 也送进来（gate 同样显式处理），
  -- 不拦的话 `=`/`-` 会按一次触发两回（`-` 会连退两段）。
  if key:release() then return K_CONTINUE end
  -- Ctrl/Alt/Super 组合键一律不碰（保留系统与其他组件的手感）
  if key:ctrl() or key:alt() or key:super() then return K_CONTINUE end
  local ch = key.keycode
  if ch ~= K_EQUAL and ch ~= K_MINUS then return K_CONTINUE end
  -- 西文模式（含 ascii_composer 的 inline_ascii 临时态）整体放行，`=`/`-` 应原样上屏
  local ok_ascii, ascii = pcall(function() return ctx:get_option("ascii_mode") end)
  if ok_ascii and ascii then return K_CONTINUE end

  if ch == K_MINUS then
    local ok, err = pcall(function() return ctx:reopen_previous_selection() end)
    if not ok and log and log.warning then
      log.warning("[jieshu_nav] reopen 失败: " .. tostring(err))
    end
    return K_ACCEPT
  end

  local a = get_api()
  if not a then
    -- 查询层 api 未就绪（正常不该发生：translator 组件加载时就会建立）。此时仍然吞键 ——
    -- 放行的话 `=` 会一路落到 express_editor 的 DirectCommit，把原码直接上屏。
    if not warned_api then
      warned_api = true
      if log and log.warning then
        log.warning("[jieshu_nav] 查询层 api 未就绪，`=` 暂不动作（避免原码上屏）")
      end
    end
    return K_ACCEPT
  end
  local target = next_target(a.part_boundaries(ctx.input or ""), confirmed_pos(ctx))
  if target then
    ctx.caret_pos = target              -- set_caret_pos → update_notifier → Compose
  end
  return K_ACCEPT                       -- 无处可跳也吞键，避免落到 DirectCommit
end

-- 测试面（离线回归用：先置 __jieshu_nav_test_mode 再加载；线上不引用）
if __jieshu_nav_test_mode then
  __jieshu_nav_test = {
    next_target = next_target,
    confirmed_pos = confirmed_pos,
  }
end

return nav
