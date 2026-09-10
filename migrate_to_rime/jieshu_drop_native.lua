-- jieshu_drop_native.lua —— 丢弃原生 table 候选（第九轮：真丢弃，兜底防泄漏）
-- lua_translator@jieshu_query 排在 table 之前：有候选时由其独占同段；无候选时
-- lua 不产出，table 可能接盘（词典前缀区与查询可见性规则同源，正常无候选=无条目）。
-- 本 filter 兜底丢弃 type=="table"（标点 punct、lua 的 jieshu 等一律放行）。
--
-- 日志策略（第十一轮）：默认静默，只在首次丢弃时打一条 info。
-- 依据（2026-09-10 实测）：泄漏是设计内的常态——table_translator 作为音节图宿主，
-- 词典里 25413 条「可见前缀」条目它都认，而 lua 的 query_by_prefix 带补码隐藏规则，
-- 于是大量条目只被 table 看见。单个会话（1h45m）实测丢弃 15501 条，按「每 50 条一行」
-- 打印会灌出 1870 行 ERROR，把错误日志整个占满，而**累计丢弃量本身不是异常指标**。
-- 真正需要告警的是 lua 加载失败 / 数据缺失 —— 那由 jieshu_query.lua 自己 log.error 上报
-- （见 jieshu_query.lua 的 `[jieshu_query] 数据缺失`）。此时垫片会丢弃 table 候选、
-- 候选栏变空，现象足够明显，不依赖这里的日志。
--
-- 排查时把 VERBOSE 改成 true，即恢复「每 50 条一条 warning」的明细日志。
local VERBOSE = false

local count = 0
local announced = false

local function drop_native(input)
  for cand in input:iter() do
    if cand.type == "table" then
      count = count + 1
      if not announced then
        announced = true
        log.info("[jieshu_pad] 兜底丢弃原生 table 候选已生效（泄漏属常态，需明细请看 jieshu_drop_native.lua 的 VERBOSE）")
      elseif VERBOSE and count % 50 == 1 then
        log.warning("[jieshu_pad] 原生 table 候选被丢弃，累计 " .. count)
      end
    else
      yield(cand)
    end
  end
end

return drop_native
