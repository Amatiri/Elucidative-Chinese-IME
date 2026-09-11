-- jieshu_query.lua —— 解书音形查询层（第八轮定案：lua translator 整段接管）
-- 1:1 移植 manager/dictionary_frontend.py 六函数（process_input / split_sequence /
-- query_by_prefix / query_multi_chars / query_phrase / get_phrase_segments），
-- 逻辑字节级（码域全 ASCII）。
-- 候选 type = "jieshu"；原生 table_translator 降级为音节图宿主，其候选由
-- jieshu_drop_native.lua 丢弃（依据：librime entry_collector 编译期丢弃词典 comment 列、
-- completion 跨音节合并按字典序——原生通道无法同时满足 页序=行序 / 余码注释 / 严格链）。
-- 真源与影子对拍：python 全管道 fuzz 3 万样本 0 差异（_tmp_lua_port_test）。
-- 数据文件由 migrate_to_rime/rime_export.py 从项目真源同步到 <user_data>/lua/data/。
-- P4-A（逐字粒度）：段首已有已确认前缀时只产出首个 part 的候选，候选 end 收到该 part
-- 末尾，借 librime Segment::Close() 的 partial 拆分让逐字选择能一字一字往下走。

-- ========== 数据 ==========

local CODE_SET = {}
do
  local s = "1234567890qwertyuiopasdfghjklzxcvbnm;'."  -- config.CODE_CHARS
  for i = 1, #s do
    CODE_SET[s:byte(i)] = true
  end
end

local buckets = nil  -- 首字节 -> { {word, code}, ... }，桶内=真源行序
local phrases = nil  -- 全码 -> 首个命中词（query_phrase 行序语义）
local load_error = nil

local function first_char(s)
  if not s or s == "" then return "" end
  local b = s:byte(1)
  local n = 1
  if b >= 0xF0 then n = 4 elseif b >= 0xE0 then n = 3 elseif b >= 0xC0 then n = 2 end
  return s:sub(1, n)
end

local function load_data()
  local dir = rime_api.get_user_data_dir() .. "/lua/data"
  local b, p = {}, {}
  local f = io.open(dir .. "/jieshu_single.txt", "r")
  if not f then
    load_error = "jieshu_single.txt 打不开（先运行 python migrate_to_rime/rime_export.py）"
    return
  end
  for line in f:lines() do
    local word, code = line:match("^(%S+)%s+(%S+)$")
    if word and code ~= "" then
      local k = code:sub(1, 1)
      local bucket = b[k]
      if not bucket then bucket = {} b[k] = bucket end
      bucket[#bucket + 1] = { word, code }
    end
  end
  f:close()
  f = io.open(dir .. "/jieshu_ciyu.txt", "r")
  if f then
    for line in f:lines() do
      local word, rest = line:match("^(%S+)%s+(.+)$")
      if word and rest then
        for code in rest:gmatch("%S+") do
          if not p[code] then p[code] = word end  -- 行序首个命中
        end
      end
    end
    f:close()
  end
  buckets, phrases = b, p
end

-- ========== 五函数移植（0-based 索引语义与 Python 原版逐一对齐） ==========

local function is_digit(b) return b ~= nil and b >= 48 and b <= 57 end
local function is_alpha(b) return b ~= nil and b >= 97 and b <= 122 end
local function byte_at(s, i0)  -- Python s[i]，0-based；越界 nil
  if i0 < 0 or i0 >= #s then return nil end
  return s:byte(i0 + 1)
end

local function split_str(s, sep)
  local out, pos = {}, 1
  while true do
    local np = s:find(sep, pos, true)
    if not np then
      out[#out + 1] = s:sub(pos)
      break
    end
    out[#out + 1] = s:sub(pos, np - 1)
    pos = np + 1
  end
  return out
end

local function has_digit(s)
  for i = 1, #s do
    if is_digit(s:byte(i)) then return true end
  end
  return false
end

local function process_input(s)
  local collecting, out = false, {}
  for i = 1, #s do
    local b = s:byte(i)
    if not collecting and is_alpha(b) then collecting = true end
    if collecting and CODE_SET[b] then out[#out + 1] = s:sub(i, i) end
  end
  return table.concat(out)
end

-- 段首残余码的字节数。上一位选字后，它的余码可能留在段首（例：按 "bu" 选「不44」后，
-- 段变成 "44ba13…"）。这些前导字符与 process_input 一样不参与查询，但逐字模式算候选
-- end 时必须把它们算进偏移，否则段会被切错位置。
local function lead_code_offset(s)
  for i = 1, #s do
    if is_alpha(s:byte(i)) then return i - 1 end
  end
  return #s
end

local function split_sequence(original)
  local parts = split_str(original, "'")
  local can = true
  while can do
    can = false
    local new_parts = {}
    for _, part in ipairs(parts) do
      local c1, c2, c3, c4, c5 = false, false, false, false, false
      local positions, positions3 = {}, {}
      if not has_digit(part) and #part > 2 then c1 = true end
      for index0 = 0, #part - 1 do
        local b = part:byte(index0 + 1)
        if is_digit(b) then
          if index0 > 2 and not is_digit(byte_at(part, index0 - 1)) then
            c2 = true
            positions[#positions + 1] = index0
          end
          if index0 > 0 and is_digit(byte_at(part, index0 - 1))
              and index0 + 1 < #part then
            local nb = part:byte(index0 + 2)
            if nb ~= 46 and not is_digit(nb) then   -- 46='.'
              c3 = true
              positions3[#positions3 + 1] = index0
            end
          end
        end
      end
      local d1 = part:find(".", 1, true)
      if d1 then
        local d2 = part:find(".", d1 + 1, true) or (#part + 1)
        if d2 - d1 - 1 > 1 then c5 = true end
      end
      if #part > 5 and not d1 then c4 = true end
      local function extend(s)
        for _, x in ipairs(split_str(s, "'")) do new_parts[#new_parts + 1] = x end
      end
      if c1 then
        local pieces = {}
        for i = 1, #part, 2 do pieces[#pieces + 1] = part:sub(i, i + 1) end
        extend(table.concat(pieces, "'"))
        can = true
      elseif c2 then
        local np = part
        for k = #positions, 1, -1 do
          local p = positions[k]           -- 0-based；Python np[:p-2] + "'" + np[p-2:]
          np = np:sub(1, p - 2) .. "'" .. np:sub(p - 1)
        end
        extend(np)
        can = true
      elseif c3 then
        local np = part
        for k = #positions3, 1, -1 do
          local p = positions3[k]          -- 0-based；Python np[:p+1] + "'" + np[p+1:]
          np = np:sub(1, p + 1) .. "'" .. np:sub(p + 2)
        end
        extend(np)
        can = true
      elseif c4 then
        extend(part:sub(1, 5) .. "'" .. part:sub(6))
        can = true
      elseif c5 then
        extend(part:sub(1, d1 + 1) .. "'" .. part:sub(d1 + 2))
        can = true
      else
        new_parts[#new_parts + 1] = part
      end
    end
    parts = new_parts
  end
  local kept = {}
  for _, x in ipairs(parts) do
    if x ~= "" then kept[#kept + 1] = x end
  end
  local result = table.concat(kept, "'")
  if original:sub(-1) == "'" and result:sub(-1) ~= "'" then
    result = result .. "'"
  end
  return result
end

-- 各 part 末尾的绝对位置表（P4-B 逐字定位用）。
-- 与查询层共用 process_input / split_sequence，避免出现第二份「拆分」真源；
-- 经 translator.api 供 jieshu_nav.lua 取用。
local function part_boundaries(full_input)
  local out, acc = {}, 0
  for _, p in ipairs(split_str(split_sequence(process_input(full_input)), "'")) do
    if p ~= "" then
      acc = acc + #p
      out[#out + 1] = acc
    end
  end
  return out
end

local function query_by_prefix(prefix)
  local out = {}
  if not prefix or prefix == "" then return out end
  local bucket = buckets[prefix:sub(1, 1)]
  if not bucket then return out end
  local plen = #prefix
  for _, wc in ipairs(bucket) do
    local word, code = wc[1], wc[2]
    local clen = #code
    if plen >= 5 and prefix:byte(5) == 97 then          -- 副码 a：prefix[4]=='a'
      local p4 = prefix:sub(1, 4)
      if plen == 5 and code == p4 then
        out[#out + 1] = word
      elseif clen >= 5 and code:sub(1, 4) == p4 then
        local p5 = prefix:sub(6)
        local p5_hit = (p5 == "" or code:sub(5, 4 + #p5) == p5)
        if p5_hit and code:byte(5) == 46 then
          out[#out + 1] = word .. code:sub(plen)        -- code[len-1:] 0-based
        end
      end
    elseif code:sub(1, plen) == prefix then
      local dot6 = code:find(".", 1, true)
      if dot6 and dot6 <= 6 then                        -- "." in code[:6]
        local pdot = prefix:find(".", 1, true)
        if pdot then
          out[#out + 1] = word .. code:sub(plen + 1)
        elseif (clen > 5 and code:byte(6) == 46)
            or (plen == 4 and is_digit(prefix:byte(4))) then
          local stem = code:sub(1, dot6 - 1)
          if prefix == stem then
            out[#out + 1] = word .. code:sub(plen + 1)
          end
        end
      else
        out[#out + 1] = word .. code:sub(plen + 1)
      end
    end
  end
  return out
end

local function query_multi_chars(split_text)
  local chars = ""
  for _, code in ipairs(split_str(split_text, "'")) do
    if code ~= "" then
      local res = query_by_prefix(code)
      if #res == 0 then return "" end
      chars = chars .. first_char(res[1])
    end
  end
  return chars
end

local function query_phrase(code)
  code = code:gsub(" ", "")
  return phrases[code] or ""
end

-- get_phrase_segments 的显示层（ime.py L273-286 / L578-586）：
-- 用户敲了人工单引号时，前端不再用「全段首选链」，而是逐个人工段各查一次词：
--   段长 < 3            → 该段前缀首候选
--   段长 >= 3 且命中词   → 该词（这就是「词语增强预览」）
--   段长 >= 3 且未命中词 → 该段自动拆分后的首选链
--   以上皆无候选         → 该段按编码原文字面输出
-- 各段显示串直接拼接 = 预览串，也就是空格上屏的内容。
-- 与前端唯一的差别：前端把字面段记进 literal_indices 供 =/- 逐字导航跳过，
-- RIME 侧逐字导航尚缺（P3），字面段直接拼进预览串，最终上屏文本一致。
local function phrase_segments_preview(processed)
  local out = {}
  for _, seg in ipairs(split_str(processed, "'")) do
    if seg ~= "" then
      local disp = nil
      if #seg < 3 then
        local res = query_by_prefix(seg)
        if #res > 0 then disp = first_char(res[1]) end
      else
        local ph = query_phrase(seg)
        if ph ~= "" then
          disp = ph
        else
          local chain = query_multi_chars(split_sequence(seg))
          if chain ~= "" then disp = chain end
        end
      end
      out[#out + 1] = disp or seg
    end
  end
  return table.concat(out)
end

-- ========== 页码提示（见 README 2.9） ==========

-- 小狼毫不显示页码，唯一「随高亮候选自动刷新」的位置是候选 preedit 的 prompt 位：
-- Composition::GetPreedit() 取当前高亮候选的 preedit()，遇 "\t" 时把后半段作为
-- prompt 追加（仅当光标在段尾）。preedit 每次现算，故翻页无需重跑 translator。
--
-- 形式只给「当前页号」，不给总页数 —— 对齐 ime.py:373 的「页 N」：
--   1. 使用体验统一（ime.py 是探测式取候选，只查当前页，本来就算不出总页数）；
--   2. 短前缀（如 `o`）可达 200+ 条，暴露总页数会给用户无谓的压力。
-- 仅当有下一页（total > page_size）时才追加，单页不挂「页1」这种噪音。
-- index 从 0 起；返回 nil = 不设置 preedit（回退显示原始输入串）。
local function preedit_with_page(input, index, total, page_size)
  if not page_size or page_size <= 0 then return nil end
  if total <= page_size then return nil end
  local page = math.floor(index / page_size) + 1
  return input .. "\t 页 " .. page
end

-- 逐字（partial）模式专用的页码标记：候选只覆盖段的一部分时，prompt 位的显示条件
-- 不再成立 —— Composition::GetPreedit 要求 caret_pos == cand->end() == full_input.length()
-- （composition.cc:52-60），而 partial 候选的 end 早于输入末尾，页码会静默消失。
-- 故该模式把页码挂到 comment 尾部（余码在前，保持可读），且只挂每页首个候选，
-- 避免整页重复同一个页号。空串 = 不显示。
local function page_marker(index, total, page_size)
  if not page_size or page_size <= 0 or total <= page_size then return "" end
  if index % page_size ~= 0 then return "" end
  return " 页 " .. (math.floor(index / page_size) + 1)
end

-- 页大小：Schema 暴露 page_size（= menu/page_size）。取值失败回退 5（本方案配置值）。
local function page_size_of(env)
  if env.page_size then return env.page_size end
  local n = nil
  if env.engine then
    local ok, v = pcall(function() return env.engine.schema.page_size end)
    if ok and type(v) == "number" and v > 0 then n = v end
  end
  env.page_size = n or 5
  return env.page_size
end

-- preedit prompt 位是否可用：光标必须停在段尾，且段尾就是整串输入的末尾
-- （这正是 Composition::GetPreedit 追加 prompt 的条件，composition.cc:52-60）。
-- 逐字 partial 的候选 end 早于段尾，天然不可用。取不到上下文时保守返回 false
-- —— 宁可把页码挂到 comment，也不要静默丢掉。
local function is_prompt_ok(env, seg, cands)
  if cands[1] ~= nil and cands[1][3] ~= nil then return false end
  local ctx = env.engine and env.engine.context
  if not ctx then return false end
  local ok_in, input_len = pcall(function() return #ctx.input end)
  if not ok_in or type(input_len) ~= "number" then return false end
  local ok_c, caret = pcall(function() return ctx.caret_pos end)
  if not ok_c or type(caret) ~= "number" then return false end
  return caret == seg._end and seg._end == input_len
end

-- ========== 候选组装（前端 update_display 两模式语义） ==========

-- 返回 { {text, comment, end_pos?}, ... }；空表 = 无候选：不产出任何候选，候选栏隐藏，
-- 编码留在行内 preedit（虚线），此时按空格由 RIME 原生 raw 段机制上屏原编码。
-- 第三项 end_pos 只在逐字模式（P4-A）出现：候选只覆盖段的一部分，需要让
-- Segment::Close() 把段切到该位置（不出现时按段尾处理，即覆盖整段）。
-- seg_start = 段在输入串中的起始偏移；0 = 段从输入头开始（无已确认前缀）。
local function build_candidates(seg_input, seg_start)
  seg_start = seg_start or 0
  local proc = process_input(seg_input)
  if proc == "" then return {} end
  -- 人工单引号（proc 里的 ' 必然是用户敲的，split_sequence 产出的不算）→ 词语增强预览。
  -- 分隔符会原样进入 input 且不打断分段（librime speller.cc / abc_segmentor.cc），
  -- 故本分支能收到完整的 "b;du'ceu"。
  if proc:find("'", 1, true) then
    local disp = phrase_segments_preview(proc)
    if disp == "" then return {} end
    return { { disp, "" } }
  end
  local st = split_sequence(proc)
  if st == "" then return {} end
  -- ── 逐字模式（P4-A）───────────────────────────────────────────────────
  -- 触发条件：段首已有已确认前缀（seg_start > 0）且剩余串还能拆出多个 part。
  -- RIME 的分段只看字符类（abc_segmentor 读 speller/alphabet），不知道解书的自动
  -- 拆分，故「选完第一个字后的剩余整串」会被当成一个段交进来；若照旧走多段分支，
  -- 候选就退化成「首选字链」，逐字粒度丢失（实测 bu44ba13bu44：剩余段 ba13bu44
  -- 只出 1 条「八不」）。
  -- 处置：只产出**首个 part** 的候选，并把候选 end 收到该 part 末尾 —— 依据 librime
  -- Segment::Close()（segmentation.cc:17-25）：候选 end < 段 end 时把段切到候选 end
  -- 并打 "partial" 标签；随后 engine.cc:259-282 的 OnSelect 会 Forward + 重新 Compose，
  -- 剩余部分自动成为下一段，于是 Shift+1~5 可以连续逐字。
  -- 首个 part 无候选时退回下面的整体语义（与改动前一致：不产出候选）。
  local parts = split_str(st, "'")
  if seg_start > 0 and #parts > 1 then
    local res = query_by_prefix(parts[1])
    if #res > 0 then
      local end_pos = seg_start + lead_code_offset(seg_input) + #parts[1]
      local out = {}
      for i = 1, #res do
        local c = res[i]
        local w = first_char(c)
        out[#out + 1] = { w, c:sub(#w + 1), end_pos }
      end
      return out
    end
  end
  local cands = {}
  if not st:find("'", 1, true) then
    -- 单字模式：前缀候选（字+余码注释），桶序=真源行序
    local res = query_by_prefix(st)
    for i = 1, #res do
      local c = res[i]
      local w = first_char(c)
      cands[#cands + 1] = { w, c:sub(#w + 1) }
    end
  else
    local ph = query_phrase(proc)
    if ph ~= "" then cands[#cands + 1] = { ph, "•" } end
    local chain = query_multi_chars(st)
    if chain ~= "" then cands[#cands + 1] = { chain, "" } end
  end
  return cands
end

-- ========== RIME 挂点 ==========
-- 无候选时不产出任何候选（对齐前端 ime.py「候选栏清空、编码留在输入位」的语义）：
-- 编码字符串由 weasel 的行内 preedit（inline_preedit，style/inline_preedit: true）
-- 在目标应用内以虚线呈现，不再伪造成一条候选占住候选栏。
-- 第九轮：tag 门放宽——matcher 命中段带 jieshu，回退段只有 abc；两种都接。
-- env.tags_probe 前 10 次调用把段 tag 集写日志，暴露真实分段行为。
local function seg_tags_str(seg)
  local ok, s = pcall(function() return tostring(seg.tags) end)
  return ok and s or "?"
end

local function jieshu_translator(input, seg, env)
  if not (seg:has_tag("jieshu") or seg:has_tag("abc")) then return end
  env.probe_n = (env.probe_n or 0) + 1
  if env.probe_n <= 10 then
    log.info("[jieshu_probe] call#" .. env.probe_n
      .. " input=" .. input .. " tags=" .. seg_tags_str(seg))
  end
  if not buckets and not load_error then
    local ok, err = pcall(load_data)
    if not ok then load_error = "数据加载异常: " .. tostring(err) end
  end
  if not buckets then
    if not env.warned then
      log.error("[jieshu_query] " .. (load_error or "数据缺失"))
      env.warned = true
    end
    return
  end
  local cands = build_candidates(input, seg.start)
  local total = #cands
  local ps = page_size_of(env)
  -- 页码落点判定。preedit 的 prompt 位有三个前置条件（Composition::GetPreedit，
  -- composition.cc:52-60）：`caret_pos == cand->end() && cand->end() == full_input.length()`
  -- —— 也就是「光标在段尾，且这个段一直铺到输入末尾」。三种状态都不满足：
  --   ① 逐字 partial：cand->end() 被收到 part 末尾，天然早于段尾；
  --   ② 光标停在中间（`=` 定位、手动 Left）：段被 Compose 截断，段尾 < 输入尾
  --      ——用户在 `bu44ba13bu44` 上按 `=` 后就是这一种（段 bu44，输入尾 12）；
  --   ③ 已确认前缀之后按 `=`：段 [8,12) 到输入尾了，但光标在 8 而非 12。
  -- 不满足时页码改挂 comment（`page_marker` 只在每页首个候选上挂），否则页码会静默消失。
  local prompt_ok = is_prompt_ok(env, seg, cands)
  for i, c in ipairs(cands) do
    local comment = c[2]
    if not prompt_ok then comment = comment .. page_marker(i - 1, total, ps) end
    local cand = Candidate("jieshu", seg.start, c[3] or seg._end, c[1], comment)
    if prompt_ok then
      -- 页码挂在 preedit 的 prompt 位（"\t" 之后），不进候选 comment，故不影响余码显示，
      -- 也不进上屏文本。前半段用段原文 input，保证应用内显示的编码仍是用户敲的那串。
      local pe = preedit_with_page(input, i - 1, total, ps)
      if pe then cand.preedit = pe end
    end
    yield(cand)
  end
end

-- 测试面（lupa 离线对拍用：先置 __jieshu_test_mode 再加载；线上不引用）
if __jieshu_test_mode then
  __jieshu_test = {
    process_input = process_input,
    split_sequence = split_sequence,
    query_by_prefix = query_by_prefix,
    query_multi_chars = query_multi_chars,
    query_phrase = query_phrase,
    phrase_segments_preview = phrase_segments_preview,
    build_candidates = build_candidates,
    preedit_with_page = preedit_with_page,
    part_boundaries = part_boundaries,
    load = load_data,
  }
end

-- 供同目录的 jieshu_nav.lua（P4-B 逐字定位）复用。Lua 的函数值不能挂字段，
-- 故走一个具名全局表；nav 侧若先加载会 require 本模块兜底触发赋值。
jieshu_query_api = {
  process_input = process_input,
  split_sequence = split_sequence,
  part_boundaries = part_boundaries,
}

return jieshu_translator
