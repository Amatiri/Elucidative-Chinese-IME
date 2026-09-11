-- jieshu_nav.lua —— P4-B 逐字定位（`=` / `-`）。挂在 processor 链首的 jieshu_gate 之后。
--
-- 目标：替掉「手按 Left 数步把光标挪到拆分点」，对齐 ime.py 的 navigate_parts 手感。
--
--   `=`  把光标移到「第一个未确认且有候选的段的末尾」（查询层 nav_scan 给出）。
--        RIME 的 Compose 按光标截断输入（engine.cc:158：composition 输入 = input()[0:caret]），
--        于是该段被单独翻出来，候选即该字的前缀候选；再往下选由 P4-A 的 partial 拆分
--        （段首已确认时只出首个 part 的候选）自动接手，故 `=` 每次按都是「回到当前待选段」，
--        天然幂等。
--   `-`  等同 Backspace（ReopenPreviousSelection）：回退上一个已确认段并重新出候选。
--        这是 RIME 段模型里唯一有意义的「往回」动作 —— 未确认段永远是「光标前那一段」，
--        不存在 ime.py 里可以回跳的「上一个未解析段」。顺带消掉一个坑：`-` 不改绑的话会
--        落到 express_editor 的 DirectCommit（editor.cc:216），把原码直接上屏。
--
--   进入闸（对齐 ime.py navigate_parts:178-182）：任一「非字面段」无前缀候选
--        （deepseek / deepseek'harness 一类整段或分段未匹配）→ `=` 不跳光标、`-` 不回退，
--        只吞键 —— 候选与输入不变化（放行会落到 DirectCommit 把原码上屏，更糟）。
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
-- nav_scan（旧 part_boundaries 已在 P4-C 并入 char_walk/nav_scan），经全局表
-- jieshu_query_api 传递（函数值不能挂字段）。若本组件先加载，
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

-- 把段首字面段「冻结」成一条独立的已确认段（原样输出），随后段边界就落在字面段末尾。
-- 依据（librime 1.13.1 源码实证）：
--   · TranslateSegments 只给 translator 段自己的文本，而候选文本会替换**整段**区间
--     （Composition::GetCommitText 用 cand->end() 推进、段未被候选覆盖时按原码补），
--     所以字面段原码若与可查段同处一段，就只能挤进每条候选的文本里 → 候选串变长；
--   · Segment::status 在 lua 侧可写（types.cc 的 vars_set），无候选段标 kConfirmed 后
--     GetCommitText 走 `input_.substr(seg.start, seg.end - seg.start)` 原码分支；
--   · Segmentation::GetCurrentStartPosition() = back().start，故必须 push_back 一个空段把
--     「当前起点」推到冻结段末尾，否则下一次 Compose 会从段首重新切段、把冻结段吞回去。
-- 四步：①光标收到字面段末尾（Compose 只翻这段，它无候选 → 菜单空）；
--       ②重取 back()（Compose 会重建段）；③标 kConfirmed；④push 空段。
local function freeze_literal_head(ctx, comp, head_end)
  ctx.caret_pos = head_end
  local seg = comp:back()
  if not seg then return false end
  seg.status = "kConfirmed"
  comp:push_back(Segment(head_end, head_end))
  return true
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
  local gate_ok, target, has_cand, head_end =
    a.nav_scan(ctx.input or "", confirmed_pos(ctx))
  if not gate_ok or (ch == K_MINUS and not has_cand) then
    -- 进入闸不过（任一非字面段无候选）：`-`/`=` 均不产生效果（问题1/2），
    -- 但仍吞键，防止落到 DirectCommit 上屏原码。
    return K_ACCEPT
  end
  if ch == K_MINUS then
    -- 有候选可回退：等同 Backspace 重选上一段（已确认前缀为空时 reopen 自身即无操作）
    local ok, err = pcall(function() return ctx:reopen_previous_selection() end)
    if not ok and log and log.warning then
      log.warning("[jieshu_nav] reopen 失败: " .. tostring(err))
    end
    return K_ACCEPT
  end
  if target then
    -- 段首字面段（"deepseek'ce" 的 "deepseek"）先冻成独立原码段：候选文本就不必再带上它
    -- （用户报的「候选都带 deepseek 前缀、候选串过长」）。冻结后新段文本 = 目标 part
    -- （如 "'ce"），出的正是该 part 的裸候选；`'` 落在候选区间内，随候选一起被覆盖，
    -- 不会随原码上屏。
    -- 只能冻**当前段**：段必须从输入头起（start==0）且一直铺到字面段末尾 —— 否则
    -- （中途按 `=`、手动 Left 收到的段）冻出来会留下空隙，段原码拼接会丢掉中间那截。
    local comp = ctx.composition
    local seg = comp and comp:back()
    if head_end and seg and seg.start == 0 and (seg._end or 0) >= head_end then
      local ok_f, err_f = pcall(freeze_literal_head, ctx, comp, head_end)
      if not ok_f and log and log.warning then
        log.warning("[jieshu_nav] 冻结字面段头失败，退回整段预览：" .. tostring(err_f))
      end
    end
    ctx.caret_pos = target              -- set_caret_pos → update_notifier → Compose
  end
  return K_ACCEPT                       -- 无处可跳也吞键，避免落到 DirectCommit
end

-- 测试面（离线回归用：先置 __jieshu_nav_test_mode 再加载；线上不引用）
if __jieshu_nav_test_mode then
  __jieshu_nav_test = {
    confirmed_pos = confirmed_pos,
    nav_scan = get_api().nav_scan,
    freeze_literal_head = freeze_literal_head,   -- 桩 ctx/comp 可离线验流程（引擎反应需实机）
  }
end

return nav
