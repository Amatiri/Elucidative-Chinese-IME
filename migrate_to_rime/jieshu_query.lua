-- jieshu_query.lua —— 解书音形查询层（第八轮定案：lua translator 整段接管）
-- 1:1 移植 manager/dictionary_frontend.py 六函数（process_input / split_sequence /
-- query_by_prefix / query_multi_chars / query_phrase / get_phrase_segments），
-- 逻辑字节级（码域全 ASCII）。
-- 候选 type = "jieshu"；原生 table_translator 降级为音节图宿主，其候选由
-- jieshu_filter.lua 丢弃（依据：librime entry_collector 编译期丢弃词典 comment 列、
-- completion 跨音节合并按字典序——原生通道无法同时满足 页序=行序 / 余码注释 / 严格链）。
-- 真源与影子对拍：python 全管道 fuzz 3 万样本 0 差异（_tmp_lua_port_test）。
-- 数据文件由 migrate_to_rime/rime_export.py 从项目真源同步到 <user_data>/lua/data/。

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

-- ========== 候选组装（前端 update_display 两模式语义） ==========

-- 返回 { {text, comment}, ... }；空表 = 无候选（RIME fallback 字面输出）
local function build_candidates(seg_input)
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
    -- 多段模式：词全码命中居首（前端空格上词），首选字链随后（预览）
    -- comment 标记「词 / 字」：对齐 ime.py 用括号 "(病毒)" 标词的显示语义。
    -- RIME 侧不能把括号写进 text —— text 即上屏内容，会污染输出；comment 不参与上屏。
    -- 单行横向拼接候选下，仅靠位置无法分辨两者性质，故此标记是必要的。
    local ph = query_phrase(proc)
    if ph ~= "" then cands[#cands + 1] = { ph, "•" } end
    local chain = query_multi_chars(st)
    if chain ~= "" then cands[#cands + 1] = { chain, "" } end
  end
  return cands
end

-- ========== RIME 挂点 ==========
-- 无候选时输出字面（前端"编码原文"语义），保证本翻译器恒非空。
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
  local cands = build_candidates(input)
  if #cands == 0 then
    yield(Candidate("jieshu", seg.start, seg._end, input, ""))
    return
  end
  for _, c in ipairs(cands) do
    yield(Candidate("jieshu", seg.start, seg._end, c[1], c[2]))
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
    load = load_data,
  }
end

return jieshu_translator
