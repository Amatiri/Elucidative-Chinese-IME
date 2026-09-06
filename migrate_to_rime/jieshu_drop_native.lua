-- jieshu_drop_native.lua —— 丢弃原生 table 候选（第九轮：真丢弃，兜底防泄漏）
-- lua_translator@jieshu_query 已排 table 之前且恒非空，正常不会有 table 候选；
-- 本 filter 兜底丢弃 type=="table"（标点 punct、lua 的 jieshu 等一律放行），
-- 同时计数留日志，供接管假设破裂时定位。
local count = 0

local function drop_native(input)
  for cand in input:iter() do
    if cand.type == "table" then
      count = count + 1
      if count % 50 == 1 then
        log.error("[jieshu] 原生 table 候选被丢弃，累计 " .. count)
      end
    else
      yield(cand)
    end
  end
end

return drop_native
