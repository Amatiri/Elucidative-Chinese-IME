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
按键 → lua_processor: jieshu_gate（链首检入）
     → ascii_composer / selector / speller（alphabet 收编码字符，' 作分段符）
     → translator 链: lua_translator@*jieshu_query（产出全部候选）
                      table_translator（仅作音节图宿主，供分段判定）
     → filters: lua_filter@*jieshu_drop_native（丢弃原生候选）+ uniquifier
```

组件引用一律写 `@*名字`（本资料夹无 `rime.lua` 注册表时，`@*` 按路径直载 `lua\名字.lua`）。

### 2.3 查询层：为什么整段由 Lua 接管

最初期望用 RIME 原生通道（词典权重、补全、句构、派生拼写）复现解书语义，被实测与源码
逐一证伪，四条死路如下（保留记录避免重复踩坑）：

| 尝试                       | 失败点                                            | 证据                      |
| ------------------------ | ---------------------------------------------- | ----------------------- |
| 词典 comment 列携带余码         | 编译期只保留 text/code/weight/stem，第 4 列不进 table.bin | `entry_collector.cc`    |
| `sort: by_weight` 约束补全页序 | 补全跨音节合并按**音节字典序**，权重只管同页                       | 实测                      |
| stabledb 独立词表            | 不参与编译；`schema/dependencies` 指向方案而非词典           | 实测 + `dict_compiler.cc` |
| 原生表出候选、靠队列顺序压后           | 同段候选由首个产出非空的 translator 独占，且句构 DP 会造非白名单链      | 实测                      |

结论：`lua_translator@*jieshu_query` 整段接管查询，原生 `table_translator` 降为
**音节图宿主**（prism 供 `matcher`/`abc_segmentor` 判定合法编码段），其泄漏候选由
`jieshu_drop_native` 丢弃。查询层是 `manager/dictionary_frontend.py` 六函数的 1:1 移植：

- **`split_sequence`（自动拆分连续编码）**：按码长/形态选切分模式（五条件优先级 1→5，
  每轮只取一个命中），不是「找音节边界」。例如 `yig` = `yi`+`g` 各取首候选 → 「一个」，
  而 `yi` 不是任何字的完整码——原生全枚举做不到，必须移植。
- **`query_by_prefix`（前缀查字）**：含补码隐藏规则（点在前 6 字符内的码，短前缀不可见），
  副码 `;` 占位、补码 `.X` 简打容错一并 1:1 移植。
- **`query_phrase`（词语）**：词码整串全等匹配、不音节化，天然满足「优先上词 =
  完全匹配优先、不被前缀捕获」。
- **`get_phrase_segments`（人工 `'` 分段预览）**：逐个人工段各查一次词后拼接。
  可行性依据：librime 中分隔符同样 `PushInput` 进 input 且不打断分段
  （`speller.cc` / `abc_segmentor.cc`），Lua 收到的是带引号完整串。
- **余码注释**：原生通道物理不可达（见上表），由 Lua 写在候选 comment 上。

词典侧仍按纪律渲染（全码 + 全部**可见**前缀 + 词全码，权重
`q × 10^len`，`q` 内嵌逆源行序且 ≤ 1），保证音节图宿主词典保持「码表顺序即优先级」形态，
日后回退原生通道时行为不退化。

### 2.4 输入流检入（`jieshu_gate` lua_processor）

对齐前端规则：**输入流为空时，只有 26 个小写字母能唤起输入**（出现候选框）；
大写字母、数字、其他符号直接上屏不进查字。按序决策：

| 条件                             | 处置                           |
| ------------------------------ | ---------------------------- |
| release / ctrl / alt / super 键 | 放行（继续链）                      |
| `ascii_mode` 为真（西文模式）          | 放行——整体交给 ascii_composer 直通   |
| 输入流非空（已在打编码）                   | 放行——码内数字/`;`/`.`/人工 `'` 照常输入 |
| 功能键 / 修饰键 / 方向键                | 放行                           |
| `a-z`                          | 放行——交给 speller 进入查字          |
| 其余可打印字符（空流下的大写、数字、符号）          | 拦截——按键穿透到应用原样上屏              |

**gate 必须排在处理链最前**：`ascii_composer` 在西文模式下会直接 `PushInput` 并终止链，
排它身后的 processor 收不到按键（返工两轮的根因）。

### 2.5 `jieshu.schema.yaml` 关键配置及原因

| 配置                                                                      | 值                                                        | 原因                                                                        |
| ----------------------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------- |
| `engine/translators`                                                    | lua 排在 `table_translator` 前                              | 同段候选由首个产出非空的 translator 独占；lua 有候选时独占，无候选时不产出（真源无该前缀码，table 也空，整段落 raw）                                          |
| `engine/filters`                                                        | 丢弃垫片 + `uniquifier`                                      | 丢弃泄漏的原生 table 候选                                                          |
| `speller/alphabet`                                                      | = `CODE_CHARS` 去掉 `'`                                    | 数字/`;`/`.` 收编为码字符；`.` 必须收（数百条补码）                                          |
| `speller/delimiter`                                                     | `'`                                                      | 真源 0 条码含 `'`，只作人工分段                                                       |
| `speller/initials`                                                      | 仅小写字母                                                    | 段首准入的纵深防御，与 gate 互补（见 2.4）                                                |
| `ascii_composer/switch_key`                                             | Shift_L: inline_ascii 等                                  | Shift 单击切西文（官方默认），gate 让位不冲突                                              |
| `speller/algebra`                                                       | 不设                                                       | 派生拼写引入跨音节合并并按字典序排，已废弃                                                     |
| `translator/enable_completion` / `enable_sentence` / `enable_user_dict` | 全 `false`                                                | 2.1 纪律红线                                                                  |
| `menu/page_size`                                                        | `5`                                                      | 对齐原前端 5 选                                                                 |
| `menu/alternative_select_keys`  | `!@#$%`  | 选字键 = Shift+1~5，见 2.7  |
| `punctuator`                                                            | 内联最小符号表                                                  | 不写 `import_preset: default`——定制环境下 default.yaml 可能没有 punctuator 段，照抄会编译失败 |
| `key_binder`                                                            | `import_preset: default` + `Up/Down → Page_Up/Page_Down` | 原生 ↑↓ 是移高亮，翻页需重绑                                                          |
| `recognizer/patterns.jieshu`                                            | 含 `'` 的码集正则                                              | 人工分段后整段仍带 jieshu tag                                                      |

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

---

### 2.7 选字键 `!@#$%`（Shift+1~5）

原前端用 `!@#$%` 选第 1~5 个候选（`ime.py:419`）。RIME 侧数字 1-9 已被 `speller/alphabet`
收编为编码字符：speller 先 `PushInput` 再以 kAccepted 终止链，**selector 收不到数字键**
（`speller.cc`：`!is_initial && !expecting_an_initial` 时直接 PushInput），数字选字在本方案里
物理不可用。改用官方为「编码占用数字键」准备的开关：

```yaml
menu:
  alternative_select_keys: "!@#$%"
```

- **源码依据**：`selector.cc` 中 `schema()->select_keys()` 非空时只按该串取 index，不再走数字
  分支；该值由 `Schema::FetchUsefulConfigItems()` 从 **`menu/alternative_select_keys`** 读取
  （不是顶层 `select_keys`）。官方 bopomofo 方案即为此写法。
- **keycode**：小狼毫下 Shift+数字传入的是符号本身的 keycode（exclam/at/numbersign/dollar/
  percent），依据万象 `default.yaml` 注释「小狼毫 Control+Shift+dollar 生效」。这些符号不属于
  `speller/alphabet`，speller 放行，最终落到 selector。若实测发现传的是数字+shift，
  则改走 Lua 兜底（在 gate 内换算成 `ctx:select()`）。
- **punctuator 让位**：`punctuator` 排在 selector 之前，故已把 `!` `$` 两条映射从标点表移除，
  否则 composing 时按键会被标点抢先上屏「！」「￥」。空流下符号由 gate 拦截后原样半角穿透，不受影响。
- **Recognizer 会抢键（实测踩坑）**：`recognizer.cc` 在按键时试探 `input + ch`，命中 pattern 就
  `ctx->PushInput(ch)` 并 `return kAccepted` —— 而 Recognizer 排在 selector **之前**，命中即吞键终止链。
  万象 `default.yaml` 的 `email: "^[A-Za-z][-_.0-9A-Za-z]*@.*$"` 因此吞掉 `@`，
  实测表现为「Shift+1/3/4/5 正常选字，唯独 Shift+2 打出 @ 不选字」（`!` `#` `$` `%` 无 pattern 故不受影响）。
  同段的 `url` / `underscore` 还会威胁 `.` `_` `:` `/`。
  → 本方案 **不写** `recognizer: import_preset: default`，只保留自有的 `jieshu` pattern。
- **附带结论**：由于 `jieshu` pattern 覆盖了全部编码字符，Recognizer 会先于 speller 接管所有编码字符
  输入并终止链，speller 实际上不参与本方案的按键处理（源码推断，未单独实测；与「数字必然进 input」的
  现象一致，此前归因于 speller.cc 的 PushInput，两条路径结果相同）。
- **候选标记「词」**：多段模式下，词候选 comment 标点号 `•`（字链 comment 为空），
  对齐 ime.py 用括号 `(病毒)` 标词的显示语义。RIME 侧**不能**把括号写进 `text`
  （`text` 即上屏内容，会污染输出），只能放 comment（不参与上屏）。
  本方案为单行横向拼接候选，仅靠位置无法分辨两者性质，故此标记是必要的。
  注：回归快照格式是 `text|comment`（`lua_regress.js:101`），改 comment 会触发差异，需 `--update` 刷新。
- **未实现**：多字模式下的「取候选首字 + 余码补回输入串 + 跳下一段」（`ime.py:450-492`）。
  它与 `=`/`-` 逐字导航是同一套机制，随 P4 一起做。

## 三、已实现功能（键盘实测验收）

| 能力                 | 表现                                                                   |
| ------------------ | -------------------------------------------------------------------- |
| 单字查询               | `bu44`→不、`ba13`→八、`ba13.`→捌（补码点号直通）                                  |
| 自动拆分连续编码           | `bu44ba13`→「不八」链、`yig`→「一个」（白名单链）                                    |
| 词语候选               | `ceu`→「测试」+「厕是」、`b;du`→「病毒」+「兵都」                                     |
| 优先上词               | 全码精确命中时词排在字链之前（Lua 多段模式下恒开）                                          |
| 人工 `'` 分段 + 词语增强预览 | `b;du'ceu`→「病毒测试」、`b;d'u`→「兵的是」                                      |
| 候选余码提示             | comment 列显示剩余编码                                                      |
| 无候选段             | `bua`→候选栏清空不产出候选，编码留在行内 preedit（应用内虚线），对齐前端「候选清空、编码原位」语义；空格/Esc 的处置待键盘复测        |
| 空输入流检入             | 只有小写字母唤起输入，数字/大写/符号直出（gate，已复测）                                      |
| 空格上屏 / ↑↓ 翻页       | 空格=首选上屏；↑↓ 经 key_binder 重绑为翻页                                        |
| `!@#$%`（Shift+1~5）选字  | `menu/alternative_select_keys` 走原生 selector（已部署，待键盘复测） |
| 码内 `0-9 . ;` 输入    | speller 收编，正常参与查字                                                    |
| 多音字多码并存            | 真源天然一条码一字                                                            |
| 皮肤                 | 「宣纸」双配色 + 字体布局（`weasel.custom.yaml`）                                 |
| 导出闭环               | 校验→渲染→逐字节同步→diff 摘要→原子写+备份                                           |
| 离线回归               | 同一份用例与快照双通道：`lua_regress.js`（fengari，Lua 5.3 语义）/ `lua_regress_lupa.py`（lupa，本机可直接跑） |

### 离线回归用法（改动 Lua 查询层后必跑）

```
# 通道 A（lupa，本机已装，推荐）：
python migrate_to_rime\lua_regress_lupa.py            # 比对快照，有差异 exit 1
python migrate_to_rime\lua_regress_lupa.py --update   # 确认行为变更后刷新快照

# 通道 B（fengari，Lua 5.3 语义，与 A 同一份用例与快照）：
npm install fengari                  # 任意 node 工作区
node migrate_to_rime\lua_regress.js
node migrate_to_rime\lua_regress.js --update
```

脚本用仓库内真源（本目录 `jieshu_query.lua` + `dict/` 码表）跑用例，不依赖部署结果。
fengari 的 `io.open` 未实现，脚本以内存桩喂数据并复刻 Windows 文本模式对 `\r` 的剥离。
快照中 `|` 之后是 comment 字段：**多段模式的「词/字」标记属 RIME 侧显示层，不来自 Python 真源**，
单字模式的余码同理；`|` 之前的候选文本仍严格对拍 Python 真源。

---

## 四、尚未实现 / 未开始

| 项                       | 归属阶段  | 说明                                      |
| ----------------------- | ----- | --------------------------------------- |
| 多字模式「取候选首字 + 余码补回输入串 + 跳下一段」 | P4 决策 | 单字模式的 `!@#$%` 选字已落地（见 2.7）；它与 `=`/`-` 逐字导航共用一套机制，一并实现 |
| 逐段子回显                   | P3    | 无候选时整段不产出（preedit 保留全部编码）；前端可对子段回显        |
| 外输窗口外观细节                | P3    | 页大小/字号/横竖排微调（皮肤共用，注意别影响其他方案）            |
| `=`/`-` 逐字切换            | P4 决策 | 对应前端 `navigate_parts`；RIME 侧可用移动光标做近似实现 |
| 自动上字（>3 码且唯一候选自动上屏）     | P4 决策 | RIME 无原生等价物；若做则走 Lua processor          |
| 简繁切换                    | P4 可选 | 补码繁体/异体已正常入表，可挂 `simplifier`            |
| 全拼→双拼桥、笔画/部件反查、无数字简码版   | P4 可选 | 增强项，每项独立可弃                              |
| 导出并入 `main.py` 工具链      | P4 之后 | 因 RIME 路径因人而异，倾向保持独立脚本 + 本 README       |
| 与 `ime.py` 并行试用期、前端退役决定 | P5    | 按实际手感决定切换/双前端/回滚；`ime.py` 不提前删除         |

明确**放弃**的映射：内输模式（RIME 系统级候选窗即「外输」且更通用）、形部表悬浮窗、剪贴板同步。

---

## 五、回滚预案

1. 删除 `<RIME 用户资料夹>` 下 `jieshu*.{schema.yaml,dict.yaml}`、`build\jieshu*` 产物、
   `lua\jieshu_*.lua`、`lua\data\jieshu_*.txt`、`weasel.custom.yaml`（若原本没有）；
2. 在「输入法设定」取消勾选解书音形（或还原 `default.custom.yaml`，改动前本机已有备份习惯）；
3. 托盘「重新部署」。其他方案与用户词库全程不受影响，仓库 `dict/` 与工具链零改动。

## 六、已知风险摘要

| #   | 风险                     | 状态与缓解                                                                    |
| --- | ---------------------- | ------------------------------------------------------------------------ |
| R7  | 码表更新后忘记重导出             | 一条 `rime_export.py` 同时刷新词典与 Lua 数据；整理码表后手动执行                             |
| R10 | Lua 查询层静默失效            | 三件套：`[jieshu_probe]` 采样日志 + 垫片丢弃计数 + 离线回归快照；数据缺失时 `log.error` 上报；回滚预案保生产 |
| R11 | 单字母前缀候选量过大（最大桶约 900 条） | 目前实测无感；若出现卡顿，给 `query_by_prefix` 加截断按页供数                                 |

（R1–R6、R8、R9 已在历轮实测中解除或消解。）
