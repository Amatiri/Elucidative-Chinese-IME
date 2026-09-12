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

-- （旧 part_boundaries 已升级为 char_walk / nav_scan，见 query_phrase 之后：
--   旧版漏算人工 `'` 占的 1 字节，且无「段是否有候选」闸。）

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

-- 逐字导航（P4-B）用的部件扫描。入参是已 process_input 的编码串，走成逐部件表，
-- 每项 { code, end, literal, cand }，end = 该 part 在此串中的末尾字节偏移：
--   无人工引号 → 自动拆分的各 part 全按「可查询段」处理（= 前端 main_function 的
--     split_parts，不做字面归类）；
--   有人工引号 → 按 get_phrase_segments 语义逐段归类：
--       段长 <3 且有前缀候选       → 单 part；无候选 → 字面段
--       段长 ≥3 命中词             → 词的自动拆分 parts（前端同样逐字可选）
--       段长 ≥3 未命中但首选链完整 → 自动拆分 parts
--       以上皆不满足               → 字面段（原码，不参与逐字导航）
-- 人工 `'` 实际占据输入串 1 字节，必须计入 end —— 旧 part_boundaries 漏算它，
-- "ceu'jmia" 里 'u' 段真实末尾是 3、旧算 4，选字后光标与候选覆盖范围整体偏移。
-- 自动拆分产生的 `'` 是虚拟边界、不占输入，不计数（与旧版无人工引号语义一致）。
local function char_walk(proc)
  local out, acc = {}, 0
  local function push(p, literal)
    if p == "" then return end
    acc = acc + #p
    out[#out + 1] = { code = p, end_ = acc, literal = literal,
                      cand = (not literal) and #query_by_prefix(p) > 0 or false }
  end
  if not proc:find("'", 1, true) then
    for _, p in ipairs(split_str(split_sequence(proc), "'")) do push(p, false) end
    return out
  end
  local first = true
  for _, seg in ipairs(split_str(proc, "'")) do
    if not first then acc = acc + 1 end   -- 人工引号占 1 字节
    first = false
    if seg ~= "" then
      local parts
      if #seg < 3 then
        if #query_by_prefix(seg) > 0 then parts = { seg } end
      elseif query_phrase(seg) ~= "" then
        parts = split_str(split_sequence(seg), "'")
      else
        local st = split_sequence(seg)
        if query_multi_chars(st) ~= "" then parts = split_str(st, "'") end
      end
      if parts then
        for _, p in ipairs(parts) do push(p, false) end
      else
        push(seg, true)
      end
    end
  end
  return out
end

-- P4-B 进入闸与定位目标（对齐 ime.py navigate_parts:178-182 + handle_special_keys:387）。
-- 返回 gate_ok, target, has_cand, head_end：
--   gate_ok  = 每个非字面段都有前缀候选。任一缺 → `=`/`-` 禁止动作、候选与输入不变化
--              （用户报的 deepseek 一类场景；前端真值即如此）；
--   has_cand = 存在可查询的非字面段（全字面段如 "deepseek'harness" 为 false）；
--   target   = 第一个「非字面、有候选、末尾 > confirmed」段的绝对末尾；nil = 无处可跳；
--   head_end = 段首字面段的绝对末尾（"deepseek'ce" 的 "deepseek"），且其后还有可查段时给出。
--              它是给 nav 用来「冻结字面头」的：把段收窄到 head_end 并标成已确认，字面段
--              就成了独立的原码段，不再挤进每条候选的文本（见 jieshu_nav.lua）。
local function nav_scan(full_input, confirmed)
  local gate_ok, has_cand, target, head_end = true, false, nil, nil
  local offset = lead_code_offset(full_input)
  for i, p in ipairs(char_walk(process_input(full_input))) do
    if not p.literal then
      if not p.cand then
        gate_ok = false
      else
        has_cand = true
        if not target and p.end_ > confirmed then target = p.end_ end
      end
    elseif i == 1 and offset == 0 then
      -- 只在输入**从字面段本身开始**时给冻结点：段首若还有残余码/人工 `'`，那段原码
      -- 上屏时会把这些不该输出的字符一起带上（`'` 与上一位已吃掉的余码）
      head_end = p.end_
    end
  end
  if not has_cand then head_end = nil end   -- 全字面（deepseek'harness 一类）没有可冻结的对象
  return gate_ok, target, has_cand, head_end
end

-- 自动上字判定（P4-D）。1:1 对齐 ime.py:581-598 的四条件：
--   ① 单字态 —— 输入无人工 `'`，且自动拆分 split_sequence 后仍无 `'`
--      （有虚拟 `'` 即多字态，前端走多字分支，根本没有自动上字）；
--   ② 码长 > 3（`#st` 是全 ASCII 字节数，与前端 len 等价）；
--   ③ 当前页候选里「余码不含 `.`」的恰好 1 条 —— 前端只查当前页，
--      而 main_function 开头会把 current_page 重置为 0（ime.py:544-545），
--      翻页不重跑该函数，故判定恒基于第 0 页 5 条，这里同样只看前 page_size 条；
--   ④ 上屏那一条的首字。
-- 返回该候选的 0-based 页内下标与首字；不触发返回 nil。
--
-- 为什么不能直接用 librime 原生 speller/auto_select（判据见 gear/speller.cc
-- AutoSelectUniqueCandidate）：它要求「段内候选总数恰好 1 条」，与 ③ 不等价 ——
--   漏触发：ba13 → 八 / 捌.（ba13. 是捌的补码）总数 2，原生不触发而前端要上屏「八」；
--   误上屏：gs34 → 廾.c、mo24 → 无.u，候选恰 1 条但余码以 `.` 开头（补码引导中），
--           ① 的语义是「尚未确定」不上屏，原生会直接上屏；
--   更致命：原生看不见解书的自动拆分（delimiters 只含人工 `'`），多字态输入整串被当一段，
--           字链候选天然恰好 1 条 → buce/bucen/bu44x 一类连续双字输入会被整串误上屏。
-- 故判定一律在 Lua 侧做，上屏走 lua_processor@*jieshu_autocommit 的 ctx:select()。
local function auto_commit_target(full_input)
  if not full_input or full_input == "" then return nil, nil end
  if full_input:find("'", 1, true) then return nil, nil end
  local proc = process_input(full_input)
  -- proc ~= full_input 说明首字符前有非码字符（process_input 会丢弃前导），
  -- 此时候选下标与输入长度对不上，保守不判（线上 gate 保证不可达）。
  if proc == "" or proc ~= full_input then return nil, nil end
  local st = split_sequence(proc)
  if st == "" or #st <= 3 then return nil, nil end
  if st:find("'", 1, true) then return nil, nil end
  local res = query_by_prefix(st)
  local hit_i, hit_w, n = nil, nil, 0
  local page = 5                                  -- menu/page_size（前端页大小同为 5）
  for i = 1, #res do
    if i > page then break end
    local c = res[i]
    local w = first_char(c)
    if not c:sub(#w + 1):find(".", 1, true) then -- 余码不含 '.' = 这条已打全
      n = n + 1
      if n > 1 then return nil, nil end          -- 非点候选 >1 → 无法确定，不触发
      hit_i, hit_w = i - 1, w
    end
  end
  if n ~= 1 then return nil, nil end
  return hit_i, hit_w
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
-- seg_start = 段在 composition 输入里的绝对起始偏移。⚠ translator 收到的 seg_input 是**段自己
--   的字面**（engine.cc::TranslateSegments：input = segments->input().substr(segment.start, len)），
--   不是整条 composition 输入；seg.start/_end 是它在 composition 输入里的绝对下标。
--   段首因此可能是这两种「残头」，必须分别处理：
--     · 段首人工 `'`：上一位选字后剩余的人工分段（"'mo"、"'ceu"）。process_input 会把段首的
--       `'` 吃掉，归类时必须补回来 —— 否则 char_walk 走「自动拆分」路径，会把字面段的自动
--       拆分（"deepseek"→de/ep/se/ek）当成当前 part，给出 "de" 的候选（用户报的「多出 d 的
--       逐字选择」）。
--     · 未冻结的字面段头："deepseek'ce" 这种整段形态 → 走前端 get_phrase_segments 预览串。
-- full_input = 整条 composition 输入（env.engine.context.input），供 P4-D 预上字提示判定；
--   nil = 不判定（离线回归逐字用例没有整串上下文）。判定命中时给目标候选 comment 挂
--   「预」（延迟一键语义：候选即下一键将自动上屏的字，见 jieshu_autocommit.lua）。
--   auto_commit_target 的守卫（无引号、单字态、无前导残码）天然挡掉人工分段/逐字
--   partial 等形态，故只有「段铺满整串的单字态」才可能命中 —— 此时 res 与判定同源
--   同序，ac_index 直接就是本函数单字分支产出的页内下标。
local function build_candidates(seg_input, seg_start, full_input)
  seg_start = seg_start or 0
  local manual_lead = seg_input:sub(1, 1) == "'"
  local proc = process_input(seg_input)
  if proc == "" then return {} end
  -- 人工引号参与归类：段首的 `'` 已被 process_input 吃掉，靠**尾接**一个虚拟 `'` 让 char_walk
  -- 走人工分段分支（每个非首分段的 acc 才 +1，尾接的空分段不产出条目，故偏移不受影响；
  -- 不能前置引号——那会把段首那个 `'` 当成内部引号，把所有 end 多算 1 字节）。
  local manual = manual_lead or proc:find("'", 1, true) ~= nil
  local walk = char_walk(manual and (proc .. "'") or proc)
  local first = walk[1]
  local base = seg_start + lead_code_offset(seg_input)
  -- 单个分段的候选：end 收到该分段末尾（< 段尾时由 Segment::Close() 切段，剩余自动成下一段）
  local function part_cands(p)
    local out = {}
    for _, c in ipairs(query_by_prefix(p.code)) do
      local w = first_char(c)
      out[#out + 1] = { w, c:sub(#w + 1), base + p.end_ }
    end
    return out
  end
  -- ① 首个分段被归类为**字面段**（无候选）。只有人工分段归类会产出这种段，两种形态：
  --    · 字面段头 + 后面还有可查段（"deepseek'ce"、"deepseek'mox;" 整段）→ 前端整串预览串
  --      （预览串本身含字面段原码，信息不丢）；
  --    · 整段就是一个字面人工分段（"ce'deepseek" 选完「厕」后的 "'deepseek"）→ 只给一条
  --      「原码」候选覆盖整段。两个作用：可确认（空格）把原文原样留下；把人工 `'` 一并覆盖
  --      —— 段尾没被候选覆盖时 `'` 会随原码上屏，而前端从不输出 `'`。
  if first and first.literal then
    if #walk > 1 then
      local disp = phrase_segments_preview(proc)
      if disp ~= "" then return { { disp, "" } } end
    end
    local text = {}
    for _, p in ipairs(walk) do text[#text + 1] = p.code end
    return { { table.concat(text), "", base + walk[#walk].end_ } }
  end
  -- ② 含人工引号的段：整段形态（段从输入头起，如 "b;du'ceu"）走前端 get_phrase_segments
  --    预览串；截断形态（段首已有已确认前缀，如 "'ceu"、"'mo"）只出**首个分段**的候选，
  --    与 P4-A 同一机制（选字后 partial 拆分接手）。
  if manual then
    if seg_start == 0 then
      local disp = phrase_segments_preview(proc)
      if disp == "" then return {} end
      return { { disp, "" } }
    end
    if first and first.cand then return part_cands(first) end
    return {}
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
    -- P4-D 预上字提示：判定与 res 同一次查询口径（见本函数头注），命中即挂「预」
    local ac_index = nil
    if full_input then
      ac_index = auto_commit_target(full_input)
    end
    for i = 1, #res do
      local c = res[i]
      local w = first_char(c)
      local comment = c:sub(#w + 1)
      if ac_index ~= nil and ac_index == i - 1 then
        comment = comment == "" and "预" or ("预 " .. comment)
      end
      cands[#cands + 1] = { w, comment }
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
  -- 整串输入供预上字判定（P4-D）；取不到时 nil，退化为无「预」提示的既有行为
  local full_input = nil
  local ok_fi, fi = pcall(function() return env.engine.context.input end)
  if ok_fi and type(fi) == "string" then full_input = fi end
  local cands = build_candidates(input, seg.start, full_input)
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
    char_walk = char_walk,
    nav_scan = nav_scan,
    auto_commit_target = auto_commit_target,
    load = load_data,
  }
end

-- 供同目录的 jieshu_nav.lua（P4-B 逐字定位）复用。Lua 的函数值不能挂字段，
-- 故走一个具名全局表；nav 侧若先加载会 require 本模块兜底触发赋值。
jieshu_query_api = {
  process_input = process_input,
  split_sequence = split_sequence,
  nav_scan = nav_scan,
  auto_commit_target = auto_commit_target,
}

return jieshu_translator
