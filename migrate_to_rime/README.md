# 解书音形 → RIME 移植（migrate_to_rime）

把本仓库的「解书音形」码表移植为一套 RIME 输入方案（标识 `jieshu`，菜单名「解书音形」），
在小狼毫（Weasel）等 librime 发行版下日常可用。本目录是 **RIME 侧的全部真源**：
导出脚本、Lua 模块、方案配置、离线回归都在这里；改这里 → 跑导出 → 部署生效。

> 依据：RIME 官方《Rime with Schemata》、librime 源码（`speller.cc` / `abc_segmentor.cc` /
> `entry_collector.cc` 等）、本仓库 Python 前端（`ime.py` + `manager/dictionary_frontend.py`）。

---

## 一、部署方法

### 前置条件

1. 已安装任一 librime 发行版（推荐 [小狼毫 Weasel](https://rime.im/)），并知道自己的
   **RIME 用户资料夹**（小狼毫：托盘菜单「用户资料夹」打开的目录）。
2. 本机有 Python 3（导出脚本只依赖标准库）。
3. 本仓库完整（导出脚本从仓库根 `config.py` 读取码表路径，码表真源在 `dict/`）。

### 三步部署

```
第 1 步  在仓库根运行：
            python migrate_to_rime\rime_export.py

第 2 步  小狼毫托盘菜单 →「重新部署」

第 3 步  小狼毫托盘 →「输入法设定」→ 勾选「解书音形」→ 确定（会自动再部署）
```

**首次运行**第 1 步时，脚本会交互式询问 RIME 用户资料夹的绝对路径：

- 粘贴路径回车即可，脚本会把该路径**写回仓库根 `config.py` 的 `RIME_USER_DIR`**，
  以后运行不再询问；
- 输入为空 = 放弃迁移，不做任何写入；
- ⚠️ **如果你以后更换了 RIME 用户资料夹，必须同步修改 `config.py` 中的
  `RIME_USER_DIR` 一行**，否则导出仍会写入旧路径。

导出完成后，`<RIME 用户资料夹>` 下会多出（全部以 `jieshu` 命名，不触碰其他方案文件）：

```
<RIME 用户资料夹>\
  jieshu.schema.yaml              # 输入方案定义
  jieshu.dict.yaml                # 音节图宿主词典（字全码 + 可见前缀 + 词全码）
  weasel.custom.yaml              # 小狼毫皮肤（「宣纸」双配色 + 字体布局）
  lua\jieshu_query.lua            # 查询层（候选的实际生产者）
  lua\jieshu_drop_native.lua      # 原生候选丢弃垫片
  lua\jieshu_gate.lua             # 输入流检入门控
  lua\jieshu_nav.lua              # 逐字定位（`=` 跳到待选段 / `-` 回退重选）
  lua\jieshu_autocommit.lua       # 自动上字（>3 码且页内唯一非点候选，见 2.14）
  lua\data\jieshu_single.txt      # 单字真源逐字节拷贝（查询层运行期直读）
  lua\data\jieshu_ciyu.txt        # 词表真源逐字节拷贝
```

### 日常维护

- **码表更新后**：在 `main.py` 工具链里整理码表（真源永远是 `dict/`），然后重跑
  `python migrate_to_rime\rime_export.py` 并「重新部署」——一条命令同时刷新词典与 Lua 数据。
- **改方案 / 皮肤**：只改本目录的 `jieshu.schema.yaml` / `weasel.custom.yaml`，再跑导出回灌。
  注意小狼毫「输入法设定」会回写已部署的 `weasel.custom.yaml`，下次导出以本目录真源为准覆盖。
- `rime_export.py` 其他参数：`--single`（只导单字表）、`--skip-config`（不动方案/皮肤）、
  `--version <串>`（词典版本字段）、`--target <路径>`（本次临时指定资料夹，不写回 config）。

---

## 二、RIME 侧实现

### 2.1 总体决策（方案基石）

1. **真源不变，RIME 侧拉取**。唯一真源是本仓库 `dict/`（`main.py` 工具链继续在此编辑）。
   `rime_export.py` 从仓库**读取**码表、向 RIME 用户资料夹**写入**产物，方向是「RIME 侧取」。
   Lua 查询层运行期直读真源的**逐字节拷贝**（`lua/data/*.txt`）——与 Python 前端共用同一份
   字节，不存在第二真源。
2. **零重码的排序纪律**。解书承诺码→字唯一、码表顺序即候选优先级。落实方式：**候选序由
   Lua 查询层按真源行序直接产出**，不依赖 RIME 的排序机制。配套红线：
   `enable_user_dict: false`（禁调频）、`enable_completion: false`、`enable_sentence: false`
   （关掉会按字典序/DP 重排的三条原生通道）。
3. **数字选字冲突已消解**。解书编码含 `0-9`。实测：数字进入 `speller/alphabet` 后由 speller
   收编为码字符，不触发 selector 劫持，原生数字键可直接选字。

### 2.2 引擎链路

```
按键 → lua_processor: jieshu_autocommit（自动上字判定，必须排在 gate 前，见 2.14）
     → lua_processor: jieshu_gate（链首检入）
     → lua_processor: jieshu_nav（`=`/`-` 逐字定位，必须排在 key_binder 前，见 2.12）
     → ascii_composer / selector / speller（alphabet 收编码字符，' 作分段符）
     → translator 链: lua_translator@*jieshu_query（产出全部候选）
                      table_translator（仅作音节图宿主，供分段判定）
     → filters: lua_filter@*jieshu_drop_native（丢弃原生候选；不写 uniquifier，见 2.10）
```

组件引用一律写 `@*名字`（本资料夹无 `rime.lua` 注册表时，`@*` 按路径直载 `lua\名字.lua`）。

### 2.3 查询层：为什么整段由 Lua 接管

最初期望用 RIME 原生通道（词典权重、补全、句构、派生拼写）复现解书语义，被实测与源码
逐一证伪（保留记录避免重复踩坑）：

| 尝试                       | 失败点                                                                    |
| ------------------------ | ---------------------------------------------------------------------- |
| 词典 comment 列携带余码         | 编译期只保留 text/code/weight/stem，第 4 列不进 `table.bin`（`entry_collector.cc`） |
| `sort: by_weight` 约束补全页序 | 补全跨音节合并按**音节字典序**，权重只管同页                                               |
| stabledb 独立词表            | 不参与编译（`dict_compiler.cc`）                                              |
| 原生表出候选、靠队列顺序压后           | 同段候选由首个产出非空的 translator 独占，且句构 DP 会造非白名单链                              |

结论：`lua_translator@*jieshu_query` 整段接管查询，原生 `table_translator` 降为
**音节图宿主**（prism 供 `matcher`/`abc_segmentor` 判定合法编码段），其泄漏候选由
`jieshu_drop_native` 丢弃。查询层是 `manager/dictionary_frontend.py` 六个函数的 1:1 移植：
`split_sequence`（自动拆分连续编码）、`query_by_prefix`（前缀查字，含补码隐藏规则与
`;` 占位、`.X` 简打容错）、`query_phrase`（词码整串全等，天然满足「完全匹配优先」）、
`query_multi_chars`（各段首选字链）、`get_phrase_segments`（人工 `'` 分段预览，见 2.8）、
以及余码注释（原生通道物理不可达，由 Lua 写在候选 comment 上）。

词典侧仍按纪律渲染（全码 + 全部**可见**前缀 + 词全码，权重 `q × 10^len`，`q` 内嵌逆源行序
且 ≤ 1），保证音节图宿主词典保持「码表顺序即优先级」形态，日后回退原生通道时行为不退化。

代价是**泄漏是常态**：词典里 25413 条「可见前缀」table_translator 都认，而 lua 的
`query_by_prefix` 带补码隐藏规则，于是大量条目只被 table 看见、由 `jieshu_drop_native` 丢弃
（实测单会话 15501 条）。这不影响正确性，但垫片日志必须静默：默认只在首次丢弃时打一条
`log.info`，要明细需把 `jieshu_drop_native.lua` 的 `VERBOSE` 改为 true。
若日后要治本（减少泄漏源头），可评估只导「全码 + 词全码」、不导前缀条目——
prism 由全部码构建、与前缀条目无关（推断，未实测），但会削弱「回退原生通道」的保险。

### 2.4 输入流检入（`jieshu_gate` lua_processor）

对齐前端规则：**输入流为空时，只有 26 个小写字母能唤起输入**（出现候选框）；
大写字母、数字、其他符号直接上屏不进查字。按序决策：release 与 ctrl/alt/super、西文模式、
输入流非空（码内数字 / `;` / `.` / 人工 `'` 照常输入）、功能键与方向键、`a-z` 一律放行；
其余可打印字符（空流下的大写、数字、符号）**拦截**，按键原样穿透到应用。

**gate 必须排在 `ascii_composer` 之前**：`ascii_composer` 在西文模式下会直接 `PushInput`
并终止链，排它身后的 processor 收不到按键（返工两轮的根因）。P4-D 的
`jieshu_autocommit` 又排在 gate **之前**（上屏后要由 gate 按空输入流规则处置当前键，
见 2.14），所以 gate 不再是字面上的「链首」，但「gate 在 ascii_composer 前」的约束不变。

**P4-B 的 `jieshu_nav` 紧随 gate 之后**（在 `key_binder` 之前）：本机 `default.yaml`（万象）
把 `-`/`=` 绑成了 `Page_Up`/`Page_Down`，排到 key_binder 后面就抢不到键。理由与取舍见 2.12。

### 2.5 `jieshu.schema.yaml` 关键配置及原因

| 配置                                                                      | 值                                                        | 原因                                                                        |
| ----------------------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------- |
| `engine/translators`                                                    | lua 排在 `table_translator` 前                              | 同段候选由首个产出非空的 translator 独占；lua 有候选时独占，无候选时不产出（真源无该前缀码，table 也空，整段落 raw）   |
| `engine/filters`                                                        | **只留丢弃垫片，不写 `uniquifier`**                               | 丢弃泄漏的原生 table 候选；不写 uniquifier 的原因见 2.10（会吞掉多音字条目）                        |
| `speller/alphabet` + `delimiter`                                        | 字母表 = `CODE_CHARS` 去掉 `'`；`'` 只作分隔符                      | 数字/`;`/`.` 收编为码字符（`.` 必须收，数百条补码）；真源 0 条码含 `'`                             |
| `speller/initials`                                                      | 仅小写字母                                                    | 段首准入的纵深防御，与 gate 互补（见 2.4）                                                |
| `translator/enable_completion` / `enable_sentence` / `enable_user_dict` | 全 `false`                                                | 2.1 纪律红线                                                                  |
| `menu/page_size` + `alternative_select_keys`                            | `5` + `!@#$%`                                            | 对齐前端 5 选；选字键 = Shift+1~5，见 2.7                                            |
| `punctuator`                                                            | 内联最小符号表                                                  | 不写 `import_preset: default`——定制环境下 default.yaml 可能没有 punctuator 段，照抄会编译失败 |
| `key_binder`                                                            | `import_preset: default` + `Up/Down → Page_Up/Page_Down` | 原生 ↑↓ 是移高亮，翻页需重绑                                                          |
| `recognizer/patterns.jieshu`                                            | 含 `'` 的码集正则                                              | 人工分段后整段仍带 jieshu tag；**不引 default**（其 email/url pattern 会抢键，见 2.7）        |

`ascii_composer/switch_key` 用官方默认（Shift_L: inline_ascii），与 gate 让位不冲突；
`speller/algebra` 不设（派生拼写会引入跨音节合并并按字典序排，已废弃）。

### 2.6 源码级大坑（可复用结论）

1. **librime-lua processor 返回值映射与 C++ 枚举相反**（`lua_gears.cc`）：Lua 返回
   `0 = kRejected`（终止链、穿透）、`1 = kAccepted`（吞键）、其他（约定 `2`）= 继续链。
   按 C++ 直觉写 `kNoop=0` 会全反。
2. **`ascii_composer` 西文模式绕过整条链**：`switch_key: Shift_L: inline_ascii` 单击即静默
   切西文；西文模式下它对 composing 按键直接 PushInput 并终止链，下游 processor 眼里按键
   「凭空消失」。处置 = gate 链首方案（2.4）。
3. **filter 迭代器方法名**是 `input:iter()`，不是 `input:iterator()`。
4. **YAML 重复键静默覆盖**：`recognizer:` 段曾与文末同名段重复，后者吞掉前者，pattern
   根本没进编译版。改完配置务必核对 `<用户资料夹>\build\jieshu.schema.yaml`。

### 2.7 选字键 `!@#$%`（Shift+1~5）

原前端用 `!@#$%` 选第 1~5 个候选（`ime.py:419`）。RIME 侧数字 1-9 已被 `speller/alphabet`
收编为编码字符，selector 收不到数字键，数字选字物理不可用。改用官方为「编码占用数字键」
准备的开关：

```yaml
menu:
  alternative_select_keys: "!@#$%"
```

- **源码依据**：`selector.cc` 中 `schema()->select_keys()` 非空时只按该串取 index，不再走数字
  分支；该值由 `Schema::FetchUsefulConfigItems()` 从 **`menu/alternative_select_keys`** 读取
  （不是顶层 `select_keys`）。官方 bopomofo 方案即为此写法。
- **punctuator 让位**：punctuator 排在 selector 之前，已把 `!` `$` 从标点表移除，否则 composing
  时按键会被标点抢先上屏「！」「￥」。空流下符号由 gate 拦截后原样半角穿透，不受影响。
- **Recognizer 会抢键**：`recognizer.cc` 试探 `input + ch`，命中 pattern 就 `PushInput` 并
  `kAccepted`，而它排在 selector **之前** —— 万象 `default.yaml` 的 email pattern 吞掉 `@`，
  表现为「Shift+1/3/4/5 正常，唯独 Shift+2 打出 @」。
  → 本方案 **不写** `recognizer: import_preset: default`，只保留自有的 jieshu pattern。
- **候选标记「词」**：多段模式下词候选 comment 为 `•`（字链为空）。本方案是单行横排拼接候选，
  仅靠位置无法分辨两者性质，故此标记必要。注：改 comment 会触发回归差异，需 `--update`。
- **多字逐字选择见 2.11**（2026-09-11 落地 P4-A）：选字后能一字一字往下走，末字自动上屏。
  `=`/`-`「自动定位到拆分点」也已落地（P4-B，见 2.12）——不再需要手数 Left。

**2026-09-10 键盘复测**：Shift+1~5 全部正常选字，P3-1 闭环。确认小狼毫下 Shift+数字传的是
**符号本身**的 keycode（exclam/at/numbersign/dollar/percent），不在 alphabet 故 speller 放行、
落到 selector，无需 Lua 兜底；也确认自持 recognizer 段后 `@` 不再被吞。

### 2.8 逐段子回显（已实现，与前端一致）

多段输入下**按子段逐个产出回显**：能查到的段出字/出词，查不到的段按编码原样留在串里
（「字面段」），拼成预览串。真源是 `manager/dictionary_frontend.py:204` 的
`get_phrase_segments`（返回 `display` + `parts` + `literal_indices`），RIME 侧移植为
`jieshu_query.lua` 的 `phrase_segments_preview` —— 坏段留原码就是 `disp or seg` 这一行。

与前端保持同步，2026-09-10 用同一份码表对拍逐例一致：`ni';hk`→你;hk、`b;'qil`→兵起来、
`b;du'ceu`→病毒测试、`bu44ba13`→不八。

自动拆分路径下若某段无候选，三端行为一致——不产出候选、编码留在原位、空格上屏原编码
（`ime.py` 无预览、`mobile` 回退整段字面、RIME 保留行内 preedit），故不另作处理。

### 2.9 页码显示（已实现）

小狼毫**不原生显示页码**（官方 `weasel.yaml` 无相关配置项）。RIME 有分页概念
（`menu/page_size`、`Page{page_size, page_no, is_last_page}`），但页码**不是持久状态**：
`Menu` 不存 page_no，由 `CreatePage()` 现算（`librime/src/rime/menu.h`）。

**落点：候选 `preedit` 的 prompt 位。** 候选能承载的附属文字只有 `comment` 与 `preedit`
（`Candidate` **没有 label**，`label_format` 由前端按页内序号生成）。而 preedit 每次由
`Composition::GetPreedit()`（`composition.cc`）取**当前高亮候选**现算：高亮段候选的
`preedit()` 遇 `\t` 时，后半段作为 **prompt** 追加（仅当光标在段尾）。于是

```
cand.preedit = "bu\t 页2"   →   应用内显示：bu（虚线） 页2（无虚线）
```

**关键收益**：翻页只改 `selected_index`，提示串自动跟着变 —— **不需要重跑 translator，
也不需要接管分页**（相比之下，写进 comment 的页码不会刷新，因为原生翻页不重跑 translator）。

**形式**：只给当前页号 `页N`，不给总页数，与 `ime.py:373` 的「页 N」一致 ——
① 体验统一（`ime.py` 是探测式取候选，本来就算不出总数）；② 短前缀候选极多
（`o` 有 223 条 = 45 页），暴露总数徒增压力。仅在有多页（`total > page_size`）时追加，
单页不挂「页1」。

**实现**：`jieshu_query.lua` 的 `preedit_with_page`（`input .. "\t 页" .. 页号`）与
`page_size_of`（取 `env.engine.schema.page_size`，失败回退 5），在 yield 前写 `cand.preedit`。
前半段用**段原文 `input`**（不用 `process_input` 的结果），保证应用内显示的编码仍是用户敲的那串。
2026-09-10 已实机验证：页码出现在应用内编码之后，翻页自动更新。

> 字面差异：`ime.py` 是独立第三行的「页 2」（带空格），RIME 侧跟在编码后写作紧凑的「页2」；
> 要字面一致把 `"\t 页"` 改成 `"\t 页 "`。

**例外：段没铺到输入末尾时，页号改挂 `comment`（2026-09-11 修）。** prompt 位有前置条件
——`Composition::GetPreedit()` 只在 `caret_pos == cand->end() && cand->end() == full_input.length()`
时才拼后半段（`composition.cc:52-60`），即「光标停在**段尾**，且这个段**一直铺到输入末尾**」。
三种常用状态不满足，页号会静默消失：

1. **逐字 partial**（2.11）：候选 `end` 被收到 part 末尾，天然早于段尾；
2. **光标停在中间**：段被 `Compose` 按光标截断（`engine.cc:158`），段尾 < 输入尾 —— 在
   `buba13bu44` 上按 `=` 后是这一种（段 `bu`、输入尾 10）；
3. **已确认前缀之后按 `=`**：段 `[8,12)` 到输入尾了，但光标在 8 而非 12。

故 translator 用 `is_prompt_ok()` 直接按上面那条式子判定：不成立就由 `page_marker` 把页号挂在
`comment` 尾部（余码在前），且**只挂每页首个候选**，避免整页重复同一个页号；成立时维持原样
（走 prompt 位，不进 comment）。判据来源：`#ctx.input`（Context 的完整输入，不是被截断的
composition 输入）+ `ctx.caret_pos`。

> 第一阶段（P4-A）只判了第 1 种，漏了 2、3 —— 用户复测时发现「按 `=` 进入后页号消失」即此因。
> 注：`comment` 是**逐候选**现算的，页号由候选下标推出，与「当前页」天然一致。

**2026-09-11 键盘复测**：前缀段（20 条 / 4 页）按 `=` 后第一行显示「不44 页 1」、翻页后首行显示
页 2；单字查询仍显示在应用内编码之后（prompt 位）；单页时不显示页号。修复闭环。

### 2.10 不写 `uniquifier`：去重会吞掉多音字条目

`uniquifier` 按候选 **text** 去重，会把同字不同读音的多音字条目判成重复。
实测 `oo`：真源 7 条（`哦4k/噢1k/哦2k/哦3k/嚄3kc` + `喔4ks/喔0k`），去重后只剩 4 条，
`哦2k`/`哦3k`/`喔0k` 消失 —— 而页码仍按 7 条算。**「显示条数 < 页码基数」就是这个坑的指纹。**

**处置**：`engine/filters` 只留 `lua_filter@*jieshu_drop_native`。安全依据（2026-09-10 统计
`dict/dictionary.txt`）：8344 条中「字+码」完全重复 = **0**，而 **816 个字有多条编码**
（和 6 次、苴/啊 5 次…）。解书的「零重码」是**码 → 字唯一**，不是「字在候选栏只出现一次」；
同字多读音靠 comment（余码）区分，与 `ime.py` 一致。

**遗留前提**：若日后码表出现「同字同码」完全重复的行，需补一个**按 text+comment 去重**的
lua filter，而不是把 `uniquifier` 加回来。

### 2.11 多字逐字选择（P4-A，2026-09-11 已复测）

RIME 分段只看字符类，选完首字后剩余串会被当成一段，原逻辑只产出“首选字链”，粒度丢失（`bu44ba13bu44` →「八不」1 条）。查询层新增逐字模式：当段 `start > 0` 且剩余串可拆出 ≥2 个 part 时，只产第一个 part 的候选，并把候选 `end` 收到该 part 末尾。候选 `end < 段 end` 时，`Segment::Close()` 会把段切到候选 `end` 并标 `partial`；`OnSelect` 后剩余部分自动成为下一段。于是「`=`/Left 定位一次 + 连续 Shift+1~5」即可逐字选完，末字自动上屏。不需要 ime.py 的余码补回/`resolved_chars`；输入串保持原样，Backspace 可回退重选。边界：逐字页号改挂 `comment`；首 part 无候选退回整体语义；人工 `'` 仍走词语增强预览；段首余码计入 `lead_code_offset`。键盘复测通过。

### 2.12 逐字定位键 `=` / `-`（P4-B，2026-09-11 已复测）

新增 `lua_processor@*jieshu_nav`，排在 gate 后、`key_binder` 前。`=`：光标跳到第一个未确认段末尾（最小拆分点 > 已确认位置），`Compose` 按光标截断后该段单独出候选；`-`：等同 Backspace（`ReopenPreviousSelection`），回退上一已确认段并重出候选。拆分点由 `jieshu_query.nav_scan` 提供，与查询层共用 `process_input` / `split_sequence`。已确认位置：段已确认取段尾，未确认取段首。本机 `default.yaml` 把 `-`/`=` 绑成 PageUp/PageDown，nav 提前拦截，翻页仍用 ↑↓；西文模式、非 composing、release、Ctrl/Alt/Super 组合放行。`=` 后页号改挂 `comment`。复测通过。

### 2.13 `=` / `-` 进入闸与字面段逐字化（P4-C，2026-09-11 已复测）

**问题**：① `deepseek` 整段未匹配按 `=` 不应变化；② `deepseek'harness` 全段未匹配同上；③ `deepseek'mox;` 只对 `mo`/`x;` 出候选；④ `ceu'jmia` 选「厕」后余段 `u'jmia` 不应错出「是检查」、光标不应甩尾。

**处置**：

- **进入闸**：`nav_scan` 判定任一非字面段无前缀候选时，`=` 不跳、`-` 不回退，只吞键；字面段不参与闸判定。
- **统一 `char_walk`**：人工 `'` 计入 `end`，自动拆分虚拟 `'` 不计。
- **人工引号逐字化**：`build_candidates` 对段首已有已确认前缀的人工引号段，只出首个分段候选，`end` 收到该分段末尾；整段形态仍走 `phrase_segments_preview` 预览串。
- **入参语义更正**：translator 第一参数是段自己的字面；`segment.start/end` 是 composition 绝对下标。
- **冻结段首字面段**：`nav_scan` 返回 `head_end`，`freeze_literal_head` 依次：光标收到 `head_end` → 重取 `comp:back()` → 标 `kConfirmed` → `comp:push_back(Segment(head_end, head_end))` 推进当前起点。效果：`deepseek'ce` 进入 `ce` 裸候选，上屏保留 `deepseek`；`ce'deepseek` 不再出 `de` 系；`deepseek'mox;` 出 `mo` 裸候选。仅当前段 `start==0` 且铺到 `head_end` 时冻结。
- **段首人工 `'` 归类**：`manual_lead` 时用 `char_walk(proc.."'")`；字面段只给一条原码候选覆盖整段，可查段只出首分段候选。

**回归与边界**：88 例 fengari 通道 0 差异；新增真实段形态用例，nav 快照改四元组（gate/has_cand/target/head_end）；`get_phrase_segments` 对拍一致。冻结失败走 pcall 兜底回整段预览；多个可查段二次 `=` 走整串预览；手动 Left 停在 `'` 后归类退化；`-` 对冻结段无效。2026-09-11 实机复测：① `deepseek'ce` 按 `=` 出 6 条 `ce` 裸候选；② `ce'deepseek` 按 `=` 不再出 `de` 系；③ `deepseek'mox;` 按 `=` 出 `mo` 35 条裸候选且上屏保留 `deepseek`。全部闭环。

### 2.14 自动上字（P4-D，2026-09-12 实机复测通过）

> 3 码且唯一候选自动上屏。对齐 `ime.py:581-598` 四条件：① 单字态（输入无人工 `'`，
> 且 `split_sequence` 后仍无 `'`）；② 码长 > 3；③ 当前页 5 条中「余码不含 `.`」的
> 恰好 1 条（前端 main_function 开头把 current_page 重置为 0 且翻页不重跑判定，
> 故恒基于第 0 页）；④ 上屏那一条的首字。

**先纠错**：本表 §四 原判「RIME 无原生等价物」**不成立** —— librime 有
`speller/auto_select`，且本方案的 express_editor 构造时把 `_auto_commit` 置 true
（`gear/editor.cc`），`AutoSelectUniqueCandidate` → `ConfirmCurrentSelection` →
`OnSelect` 会真正 `Commit()` 上屏，不只是选中。但它的**判定口径**不可用：

| 原生判据（`gear/speller.cc`）       | 与前端的偏差                        | 真源实测（8398 条单字，码长全 ≥4）                                                          |
| ----------------------------- | ----------------------------- | ------------------------------------------------------------------------------ |
| 段内候选总数恰好 1 条（`Prepare(2)==1`） | 前端是「页内非点候选恰 1 条」              | 漏触发 98 例（`ba13`→八/捌.，前端要上屏「八」原生不动）；误上屏 15 例（`gs34`→廾.c、`mo24`→无.u，补码引导中前端明确排除） |
| `delimiters` 只含人工 `'`         | 看不见解书的自动拆分                    | 多字态输入整串被当一段，字链候选天然恰好 1 条 → `buce/bucen/bu44x/b;,d` 一类连续双字输入全部被整串误上屏            |
| `auto_select_pattern`（C++ 正则） | 无法表达 `split_sequence` 的迭代拆分语义 | 纯配置无解                                                                          |

**实现**：判定收进查询层 `auto_commit_target(full_input)`（1:1 复刻上述四条件，
复用 `process_input` / `split_sequence` / `query_by_prefix`，返回候选 0-based 页内
下标与首字），上屏交给新组件 `lua_processor@*jieshu_autocommit`：`ctx:select(index)`
→ `select_notifier` → `engine.cc::OnSelect` → 段 kConfirmed → `_auto_commit` →
`Commit()` —— 与原生 auto_select 的上屏路径完全同一条；下标越界时 `Select` 返回
false，天然安全。

**两个时机事实**：

1. processor 在按键到达时先跑，此刻 `ctx.input` 还是**上一次按键之后**的状态 ⇒
   判定命中时上屏的是上一键打出的码，当前键随后照常走链（连打无感；停手时编码
   保留、按空格上屏，首选即目标字）。
2. 组件必须排在 `jieshu_gate` **之前**：`select()` 上屏会 `Clear()` 清空输入流，
   当前键要继续流到 gate、由它按「空输入流」规则处置（小写字母放行、数字/大写/
   符号拦截穿透）—— 等价 ime.py「自动上字后输入框已清空」；排在 gate 之后则 gate
   已用清空前的输入判过一轮，当前键会被当成码字符推进刚清空的输入流。

**触发键白名单**：a-z / 0-9 / `;` / `.` / `'`（alphabet 全集，**空格不在内**，见下）。
选字键（Shift+1~5 → !@#$%）、方向键、Esc、Backspace、`=`/`-` 一律不触发 ——
用户按这些键说明想操作当前编码/候选，不该被自动上字截胡。

**实机修复记录（2026-09-12 首轮复测出 2 bug，均已修）**：

1. **`bu44`+空格 → 「不 」**（多出一个字面空格）。根因：空格在白名单内，commit
   `Clear()` 后空格继续走链，空输入流下 gate 对空格 REJECT 穿透到应用。
   修复：**空格移出白名单**，改走 express_editor 原生路径（有输入流时空格经 gate
   composing 分支放行 → `Editor::Confirm` → `ConfirmCurrentSelection()` 上屏高亮
   候选）。可行性由全码表统计背书：枚举码表全部完整码的 >3 前缀 + 副码形态共
   **14642 个可达输入，判定命中 12982 例的目标下标全部为 0**（高亮默认位），原生
   上屏即目标字；且用户翻页后空格上屏的是翻到的候选，尊重用户的主动选择。
2. **`ba13`+`.` → 「八.」而非「捌」**。根因：`.` 在白名单内，commit「八」后 `.` 在
   空输入流穿透成字面点。修复：**`.` 保留触发但加 peek** —— 预上字状态下先试
   `auto_commit_target(input..".")`：命中（`ba13.`→捌、`ce4u.`→測）则不 commit，
   放 `.` 进输入流重新判定（候选与「预」提示随之刷新）；不命中（`bu44.` 无此码
   形态）则照常上屏目标字，`.` 在空输入流穿透（与既有标点行为一致）。
   注：ime.py 的自动上字是**即时上屏**（`real_time_var` trace 回调判定命中立即
   `replace_content`+清空，ime.py:585-598），`ba13.` 在前端须关自动上字才打得出；
   RIME 的延迟一键语义恰好让「`.` 并入编码」成为可能，此为对前端的刻意增强。
3. **预上字提示**（用户新增需求）：判定命中时目标候选 comment 挂「预」字
   （`build_candidates` 新增第三参 `full_input`＝`env.engine.context.input` 整串，
   在单字模式分支判定——`auto_commit_target` 的守卫天然挡掉人工分段/逐字
   partial 形态）。余码非空显示「预 .」形，空则「预」。

**回归**：用例新增 `ac <输入串>` 形态 19 条（触发 3：`bu44`/`ba13`/`ba13.`；拦截
16：3 码 `bu4`、补码引导 `gs34`/`mo24`/`ne47`、多字态 `buce` 类、人工引号
`bu44'ba13`/`'bu44`、前导杂字符 `4bu44`），两通道 **107 例 0 差异**。
「预」标记使 build_candidates 快照恰有 5 例变化（`bu44`/`ba13`/`ba13.`/`ce4u`/
`ce4u.`，差异仅为目标候选多挂「预」，其余 102 例零变化）；另有按键级探针 13 例
（mock key/env，lupa）全 PASS：空格不触发 ×2、`.` peek 命中放行 ×2 / 不命中
commit ×2、字母/数字/分号 commit ×3、release/ctrl/选字键/3 码未满不触发 ×4。
**实机复测（2026-09-12）**：修复后全部通过 —— `bu44`+空格出「不」无多余空格、
`ba13`+`.` 出「捌」（候选带「预」）、`bu44`+`.` 的穿透点行为、连打/翻页/
西文模式不受影响。P4-D 收官。

## 三、已实现功能

| 能力                   | 表现                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------ |
| 单字查询                 | `bu44`→不、`ba13`→八、`ba13.`→捌（补码点号直通）                                                              |
| 自动拆分连续编码             | `bu44ba13`→「不八」链、`yig`→「一个」（白名单链）                                                                |
| 词语候选                 | `ceu`→「测试」+「厕是」、`b;du`→「病毒」+「兵都」                                                                 |
| 优先上词                 | 全码精确命中时词排在字链之前（Lua 多段模式下恒开）                                                                      |
| 人工 `'` 分段 + 词语增强预览   | `b;du'ceu`→「病毒测试」、`b;d'u`→「兵的是」                                                                  |
| 候选余码提示               | comment 列显示剩余编码                                                                                  |
| 逐段子回显                | 按子段产出回显，无候选的段按编码原样留在串里，与前端一致（见 2.8）                                                              |
| 候选页码显示               | 单页不显示；多页时显示 `页N`（不给总页数）：段铺到输入尾 → 挂在应用内编码后（prompt 位），否则挂在候选 comment（余码之后，只挂每页首条）（见 2.9）           |
| 多音字逐条列出              | 同字不同码各自成条（不写 `uniquifier`，见 2.10）；`oo`→7 条含 哦4k/哦2k/哦3k                                          |
| 无候选段                 | `bua`→候选栏清空不产出候选，编码留在行内 preedit（应用内虚线），对齐前端「候选清空、编码原位」语义；空格/Esc 的处置待键盘复测                         |
| 空输入流检入               | 只有小写字母唤起输入，数字/大写/符号直出（gate，已复测）                                                                  |
| 空格上屏 / ↑↓ 翻页         | 空格=首选上屏；↑↓ 经 key_binder 重绑为翻页                                                                    |
| `!@#$%`（Shift+1~5）选字 | `menu/alternative_select_keys` 走原生 selector（2026-09-10 键盘复测 1~5 全通过，见 2.7）                       |
| 多字逐字选择               | 选完一字后只出下一个 part 的候选，Shift+1~5 连续逐字、末字自动上屏（见 2.11，已复测）                                            |
| 逐字定位键 `=` / `-`      | `=` 把光标跳到当前待选段末尾（不用手数 Left 进入逐字）；`-` 等同 Backspace 回退重选（见 2.12，已复测）                               |
| 自动上字                 | >3 码且当前页唯一「非点候选」自动上屏；判定在 Lua（`auto_commit_target`），上屏走 `ctx:select()` 原生链路；触发键=码字符（空格走原生 Confirm，`.` 带 peek，见 2.14）；预上字时目标候选 comment 挂「预」（2026-09-12 已复测） |
| 码内 `0-9 . ;` 输入      | speller 收编，正常参与查字                                                                                |
| 皮肤与外观                | 「宣纸」双配色 + 字体布局 + 页大小/字号/横竖排（`weasel.custom.yaml`；导出以本目录真源为准覆盖）                                   |
| 导出闭环                 | 校验→渲染→逐字节同步→diff 摘要→原子写+备份                                                                       |
| 离线回归                 | 同一份用例与快照双通道：`lua_regress.js`（fengari，Lua 5.3 语义）/ `lua_regress_lupa.py`（lupa，本机可直接跑）             |

### 离线回归用法（改动 Lua 查询层后必跑）

```
# 通道 A（lupa，C 真 Lua）：需 pip install lupa —— 本机已装（见下方环境事实）
python migrate_to_rime\lua_regress_lupa.py            # 比对快照，有差异 exit 1
python migrate_to_rime\lua_regress_lupa.py --update   # 确认行为变更后刷新快照

# 通道 B（fengari，Lua 5.3 语义，与 A 同一份用例与快照）—— 本机现成可用：
npm install fengari                  # 任意 node 工作区（本机装在 WorkBuddy 托管工作区）
set NODE_PATH=<装了 fengari 的 node_modules 绝对路径>
node migrate_to_rime\lua_regress.js
node migrate_to_rime\lua_regress.js --update
```

本机实测可用的两条命令（两条都跑，互为交叉验证）：

```
python migrate_to_rime\lua_regress_lupa.py                    # 通道 A：lupa 2.8 / C 真 Lua

NODE_PATH=C:/Users/yuifsama/.workbuddy/binaries/node/workspace/node_modules \
  node migrate_to_rime/lua_regress.js                         # 通道 B：fengari / Lua 5.3 语义
```

**本机环境事实（2026-09-12 复核）**：本机有**两个** CPython。`D:\python\python.exe`
（3.14.3，`lupa` 2.8 装在它的 user site `%APPDATA%\Python\Python314\site-packages`）；
WorkBuddy 等工具会话的 PATH 里托管解释器（3.13.12，无第三方包）可能排在前面 ——
`python` 解析到谁取决于会话，**跑通道 A 请显式写 `D:\python\python.exe
migrate_to_rime\lua_regress_lupa.py`**（2026-09-12 实测：裸 `python` 解析到托管
3.13.12 时 lupa 报 ModuleNotFoundError）。通道 B 的 fengari 装在 WorkBuddy 托管
node 工作区，`NODE_PATH` 方式不变。两通道共用同一份用例与快照（2026-09-12：
107 例两通道 0 差异）。

脚本用仓库内真源（本目录 `jieshu_query.lua` + `jieshu_nav.lua` + `dict/` 码表）跑用例，不依赖部署结果。
用例行两种写法：

- `#<n> <段串>`（行首带 `#<n> ` 前缀）：`n` = 段的起始偏移（`seg.start`），覆盖 2.11 的逐字模式
  （例：`#4 ba13bu44` = 前面已有 4 字节的已确认段，剩余段是 `ba13bu44`）；不带前缀 = 段从输入头开始。
- `nav <已确认> <输入串>`：覆盖 2.12 的定位逻辑，比对的是 `next_target` 算出的**目标光标位置**；
  `-1` = 没有可跳的目标（已全部确认）。例：`nav 0 bu44ba13bu44` → `4`。
- `ac <输入串>`：覆盖 2.14 的自动上字判定，比对 `auto_commit_target` 的两列输出——
  候选 0-based 页内下标与上屏首字；`-1` + 空 = 不触发。例：`ac bu44` → `0` + `不`、
  `ac ba13` → `0` + `八`（捌. 因余码含点被排除）、`ac gs34` → `-1`（廾.c 补码引导中）。
  fengari 的 `io.open` 未实现，脚本以内存桩喂数据并复刻 Windows 文本模式对 `\r` 的剥离。
  快照中 `|` 之后是 comment 字段：**多段模式的「词/字」标记属 RIME 侧显示层，不来自 Python 真源**，
  单字模式的余码同理；`|` 之前的候选文本仍严格对拍 Python 真源。

---

## 四、尚未实现 / 未开始

| 项                       | 归属阶段  | 说明                                                     |
| ----------------------- | ----- | ------------------------------------------------------ |
| 逐字模式下「字面段」对齐（P4-A2）     | P4 可选 | 2.13 已处理导航侧（字面段跳过、原码并入候选文本）；首个 part 无候选时仍退回整体语义（不产出候选） |
| 简繁切换                    | P4 可选 | 补码繁体/异体已正常入表，可挂 `simplifier`                           |
| 全拼→双拼桥、笔画/部件反查、无数字简码版   | P4 可选 | 增强项，每项独立可弃                                             |
| 导出并入 `main.py` 工具链      | P4 之后 | 因 RIME 路径因人而异，倾向保持独立脚本 + 本 README                      |
| 与 `ime.py` 并行试用期、前端退役决定 | P5    | 按实际手感决定切换/双前端/回滚；`ime.py` 不提前删除                        |

明确**放弃**的映射：内输模式（RIME 系统级候选窗即「外输」且更通用）、形部表悬浮窗、剪贴板同步。

---

## 五、回滚预案

1. 删除 `<RIME 用户资料夹>` 下 `jieshu*.{schema.yaml,dict.yaml}`、`build\jieshu*` 产物、
   `lua\jieshu_*.lua`、`lua\data\jieshu_*.txt`、`weasel.custom.yaml`（若原本没有）；
2. 在「输入法设定」取消勾选解书音形（或还原 `default.custom.yaml`，改动前本机已有备份习惯）；
3. 托盘「重新部署」。其他方案与用户词库全程不受影响，仓库 `dict/` 与工具链零改动。

## 六、已知风险摘要

| #   | 风险                     | 状态与缓解                                                                                      |
| --- | ---------------------- | ------------------------------------------------------------------------------------------ |
| R7  | 码表更新后忘记重导出             | 一条 `rime_export.py` 同时刷新词典与 Lua 数据；整理码表后手动执行                                               |
| R10 | Lua 查询层静默失效            | 三件套：`[jieshu_probe]` 采样日志 + 垫片首条 info（`VERBOSE` 可开明细）+ 离线回归快照；数据缺失时 `log.error` 上报；回滚预案保生产 |
| R11 | 单字母前缀候选量过大（最大桶约 900 条） | 目前实测无感；若出现卡顿，给 `query_by_prefix` 加截断按页供数                                                   |

（R1–R6、R8、R9 已在历轮实测中解除或消解。）
