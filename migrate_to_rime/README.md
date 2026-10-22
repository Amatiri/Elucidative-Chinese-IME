# 解书音形 → RIME 移植（migrate_to_rime）

把本仓库的「解书音形」码表移植为一套 RIME 输入方案（标识 `jieshu`，菜单名「解书音形」），
在 **Windows 小狼毫（Weasel）** 与 **安卓同文（Trime）** 两端可用（安卓端 2026-10-21 起
初始支持，键盘为方案 H 布局，详见第三节）。本目录是 **RIME 侧的全部真源**：
导出脚本、Lua 模块、方案配置、两端皮肤/键盘配置都在这里；
改这里 → 跑导出 → 部署生效。

---

## 一、部署方法

### 前置条件

1. 已安装任一 librime 发行版：Windows 用 [小狼毫 Weasel](https://rime.im/)，安卓用 [同文 Trime](https://github.com/osfans/trime) v3.3.x；
   
   并知道自己的**RIME 用户资料夹**（小狼毫：托盘菜单「用户资料夹」；安卓：APP 菜单→配置→用户文件夹）。

2. 本机有 Python 3（导出脚本只依赖标准库）。

3. 本仓库完整（导出脚本从仓库根 `config.py` 读取码表路径，真源在 `dict/`）。

### Windows · 小狼毫（Weasel）

```
第 1 步  仓库根运行：
            python migrate_to_rime\rime_export.py

第 2 步  小狼毫托盘菜单 →「重新部署」

第 3 步  小狼毫托盘 →「输入法设定」→ 勾选「解书音形」→ 确定（会自动再部署）
```

### Android · 同文（Trime）

导出到预备文件夹，再整体拷进手机：

```
第 1 步  仓库根运行（--target 指向预备文件夹，脚本会自建目录）：
            python migrate_to_rime\rime_export.py --target <预备文件夹>

第 2 步  把预备文件夹里的全部内容复制到手机 RIME 用户文件夹

第 3 步  同文 App 内「重新部署」→ 方案选单切换到「解书音形」
```

**首次运行**会交互式询问 RIME 用户资料夹的绝对路径，并写回仓库根 `config.py` 的
`RIME_USER_DIR`，以后不再询问；输入为空则放弃迁移、不做任何写入。
⚠️ **换了资料夹必须同步修改这一行**，否则导出仍写入旧路径。

### 导出产物

`<RIME 用户资料夹>` 下只会新增以下文件（均以 `jieshu` / `weasel` / `trime` 前缀命名，
不触碰其他方案）：

```
jieshu.schema.yaml              # 方案定义（含两个功能开关）——两端共用
jieshu.dict.yaml                # 方案声明的词典（Trime 部署校验必需）
weasel.custom.yaml              # 小狼毫皮肤（「宣纸」双配色 + 字体布局）
trime.custom.yaml               # 安卓同文键盘（方案 H 布局 + 3 个 preset_keys）
lua\jieshu_query.lua            # 查询层（候选的实际生产者）
lua\jieshu_drop_native.lua      # 原生候选丢弃垫片
lua\jieshu_gate.lua             # 输入流检入门控
lua\jieshu_nav.lua              # 逐字定位（`=` 跳段 / `-` 回退）
lua\jieshu_autocommit.lua       # 自动上字
lua\data\jieshu_single.txt      # 单字真源逐字节拷贝（查询层运行期直读）
lua\data\jieshu_ciyu.txt        # 词表真源逐字节拷贝
```

- 两端皮肤/键盘**默认一并导出**，各端只读自己那份（小狼毫不认 `trime.custom.yaml`，
  Trime 不认 `weasel.custom.yaml`），互不影响；安卓端「导出 → 整份拷进手机」即可。
- `jieshu.dict.yaml` 必须一起部署：Trime 重新布署时会校验方案声明的词典，缺文件直接失败；
  小狼毫不读它。导出始终生成，无需手动处理。
- 导出自带闭环：校验 → 渲染 → 逐字节同步 → diff 摘要 → 原子写 + 备份（`*.bak`）。

### 日常维护

- **码表更新**：在 `main.py` 工具链里整理码表（真源永远是 `dict/`），重跑
  `python migrate_to_rime\rime_export.py` 并「重新部署」——一次刷新词典、Lua 数据与方案配置。
  安卓端同一条命令，`--target` 指向预备文件夹后再整份拷进手机。
- **改方案 / 皮肤 / 键盘**：只改本目录的 `jieshu.schema.yaml` / `weasel.custom.yaml` /
  `trime.custom.yaml`，再跑导出回灌。小狼毫「输入法设定」会回写已部署的 `weasel.custom.yaml`，
  下次导出以本目录真源为准覆盖。
- **其他参数**：`--single`（只出单字）、`--skip-config`（只更新词典与 Lua 数据）、
  `--version <串>`（词典 version 字段）、`--target <路径>`（临时指定资料夹，不写回 config）。

### 发布计划

计划在 **0.6.7 正式发布**时把导出产物（`jieshu.schema.yaml` + `jieshu.dict.yaml` + `lua/` +
`weasel.custom.yaml` + `trime.custom.yaml`）打包进 GitHub Release，用户解压到自己的 RIME
用户资料夹即可生效，无需运行导出脚本（打包时排除 `*.bak`）。

---

## 二、RIME 侧实现与功能

两端共用同一份 `jieshu.schema.yaml` + 5 个 Lua 模块，皮肤与键盘各端一份；
输入行为（编码、门控、逐字选择、自动上字、优先上词）完全一致。

### 2.1 实现概要

1. **真源不变，RIME 侧拉取**：`dict/` 仍是唯一真源，`rime_export.py` 只读真源、只写
   RIME 用户资料夹；Lua 运行期直读 `lua/data/*.txt`（真源的逐字节拷贝），不存在第二真源。
2. **候选整段由 Lua 产出**：RIME 原生通道（词典权重、补全、句构、派生拼写）无法复现
   解书语义，因此 `lua_translator@*jieshu_query` 接管查询，候选序严格按真源行序；
   `enable_user_dict` / `enable_completion` / `enable_sentence` 全关。原生 `table_translator`
   退为遗留组件，其候选全部由垫片丢弃；`jieshu.dict.yaml` 仍必须生成（Trime 校验词典）。
3. **数字选字冲突已消解**：解书编码含 `0-9`，数字被 `speller/alphabet` 收编为码字符，
   选字改用 `!@#$%`（Shift+1~5）。
4. **组件链**：

```
按键 → jieshu_autocommit → jieshu_gate → jieshu_nav
     → ascii_composer / selector / speller
     → lua_translator@*jieshu_query → lua_filter@*jieshu_drop_native
```

组件顺序有硬约束，改配置前先看 2.3。

### 2.2 功能一览

| 能力                 | 表现                                              |
| ------------------ | ----------------------------------------------- |
| 单字查询               | `bu44`→不、`ba13`→八、`ba13.`→捌（补码点号直通）             |
| 自动拆分连续编码           | `bu44ba13`→「不八」链、`yig`→「一个」                     |
| 词语候选               | `ceu`→「测试」+「厕是」、`b;du`→「病毒」+「兵都」                |
| 优先上词（开关，默认开）       | 全码精确命中时词排在字链前；关闭后词仍在，只退到链后（Shift+2 可选）          |
| 人工 `'` 分段 + 词语增强预览 | `b;du'ceu`→「病毒测试」、`b;d'u`→「兵的是」                 |
| 余码提示               | 候选 comment 显示剩余编码；多段模式下的词候选标 `•`                |
| 逐段子回显              | 按子段回显，查不到的段按原码留在串里，与前端一致                        |
| 候选页码               | 多页时显示 `页N`（不给总页数），单页不显示，翻页自动更新                  |
| 多音字逐条列出            | 同字不同码各自成条（如 `oo`→7 条），靠余码区分                     |
| 无候选段               | 候选栏清空、编码留在行内（虚线），与前端「候选清空、编码原位」一致               |
| 空输入流检入             | 只有小写字母唤起输入；数字、大写、符号直接上屏，不进查字                    |
| 空格上屏 / ↑↓ 翻页       | 空格 = 首选上屏；↑↓ 经 key_binder 重绑为翻页                 |
| `!@#$%` 选字         | Shift+1~5 选第 1~5 个候选，走原生 selector               |
| 多字逐字选择             | 选完一字后只出下一段候选，连续 Shift+1~5 逐字选，末字自动上屏            |
| 逐字定位 `=` / `-`     | `=` 把光标跳到待选段末尾（不用手数 Left）；`-` 等同 Backspace 回退重选 |
| 自动上字（开关，默认开）       | >3 码且当前页唯一「非点候选」时自动上屏；预上字时目标候选标「预」              |
| 码内 `0-9 . ;` 输入    | speller 收编，正常参与查字                               |
| 皮肤与外观              | 「宣纸」双配色、字体与横竖排布局（`weasel.custom.yaml`）          |
| 安卓同文键盘             | 方案 H 5 行布局，见第三节                                 |

### 2.3 维护要点（改配置前必看）

- **组件顺序**：`jieshu_autocommit` 必须在 `jieshu_gate` 前（上屏清空输入流后，当前键要由
  gate 按空流规则处置）；`gate` 必须在 `ascii_composer` 前（西文模式下它会吞键并终止链）；
  `jieshu_nav` 必须在 `key_binder` 前（否则 `=` / `-` 被抢成翻页）。
- **不要加 `uniquifier`**：`engine/filters` 只保留 `jieshu_drop_native`。它按 text 去重，
  会吞掉同字不同码的多音字条目。
- **开关默认开必须写 `reset: 1`**（只靠 `states` 顺序无效）；**不要**往
  `default.custom.yaml` 的 `switcher` 登记 `save_options`——`patch` 是整体替换，会顶掉
  `hotkeys` 导致方案选单打不开。
- **`recognizer` 不要 `import_preset: default`**：其 email pattern 会吞 `@`，表现为
  Shift+2 打出 `@` 而非选第 2 候选；只保留自有的 jieshu pattern。
- **`punctuator` 用内联最小符号表**，不 `import_preset: default`，避免定制环境下
  该段缺失导致编译失败。
- **`jieshu.dict.yaml` 始终生成**，别改成可选：Trime 缺它部署失败。
- 改完配置核对 `<用户资料夹>\build\jieshu.schema.yaml`：YAML 重复键会静默覆盖，
  写了也可能没生效。

---

## 三、安卓同文（Trime）键盘

> 键盘真源：`migrate_to_rime/trime.custom.yaml`——补丁模式，只新增
> `preset_keyboards/jieshu` 与 3 个 `preset_keys`（自动上字 / 优先上词 / 清空），
> 不改任何已有域，故回滚只需删文件重新部署。
> 布局取自 `mobile/src/ui/keymap.ts` 的**方案 H**（10 列 × 5 行），5 行形态与 Web 版默认一致。

![同文（Trime）上的解书音形键盘](https://cdn.jsdelivr.net/gh/Amatiri/Elucidative-Chinese-IME@cf88bd4/help/手机键盘.png)

*同文（Trime）上的解书音形键盘：数字行的上滑是 `!@#$%`（选第 1-5 候选）；
末行左起为「大写 / Z / X / C / V / B / N / M / = / 退格」，键顶符号即上滑动作。*

### 3.1 与 mobile/ 方案键盘的差异

| 项          | mobile/（Web 原型）    | 同文（Trime）                        | 说明                                                                      |
| ---------- | ------------------ | -------------------------------- | ----------------------------------------------------------------------- |
| 翻译         | D 键上滑（stub，未实现）    | **未添加**                          | Trime 无内建翻译，暂不做                                                         |
| 形部表（部件表浮层） | Z 键上滑              | **未添加**                          | 裁决 3：暂不实现；Z 的上滑位暂借给英文撇号                                                 |
| 单引号 `'`    | Row5 首键单击          | **Z 键上滑**                        | 原「'」键位改为默认大写键                                                           |
| 大写键        | `'` 键上滑（⇪）         | 原「'」键位 = **大写键**（单击切换锁定，锁定时键位变青） | Trime 的 Shift 锁定必须由真正的 Shift 键承载，否则锁死后无法解锁（机制见 `trime.custom.yaml` 内注释） |
| 候选排列与翻页    | 自绘候选条 + ∨ 翻页键      | **由同文系统接管，解书音形不额外配置**            | 候选栏是键盘上方的独立视图；右上角「∨」展开全量候选浮窗                                            |
| 其它输入行为     | 与 ime.py 对齐 + 少量设置 | **基本与 weasel 对齐**                | 编码、门控、逐字选择、自动上字、优先上词等完全一致（同一份 schema + 5 个 lua）                         |

### 3.2 建议的同文设置

- **候选栏每行候选数改为 5**（设置 → 虚拟键盘 → 候选栏每行候选数，preference key
  `max_span_count`，默认 6）——与解书音形「一页 5 选」的 `menu/page_size: 5` 对齐，
  候选排布即桌面端观感。若该设置项不可见，先把「横向候选样式」
  （`horizontal_candidate_mode`）设为 **AUTO_FILL（均分宽度）**：只有该模式下
  `max_span_count` 才真正决定每行候选数（源码：`CompactCandidateDelegate` + `AppPrefs`）。
- 其余保持默认即可。

### 3.3 其它说明

- 键帽字母统一大写（`label_transform: uppercase`），与 Web 版设计稿一致；西文态自动回落小写。
- 大写锁定期间输入法整体旁路（字母变大写、数字符号原样直通应用），再单击「大写」键即解除。
- 键盘 ID 等于 `schema_id`（`jieshu`），切换到解书方案即自动绑定，无需在设置里选布局。
- 键盘机制与实测结论（Shift 锁定、候选栏形态、5/6 行取舍）详见 `trime.custom.yaml` 的注释。

---

## 四、边界与风险

### 4.1 暂不实现

| 项                          | 归属阶段  | 说明                                |
| -------------------------- | ----- | --------------------------------- |
| 简繁切换                       | P4 可选 | 解书音形通过补码实现，而非切换模式                 |
| 全拼→双拼桥、笔画/部件反查（形部表）、无数字简码版 | P4 可选 | 更接近“工具”内容，而非输入功能                  |
| 导出并入 `main.py` 工具链         | P4 之后 | 因 RIME 路径因人而异，倾向保持独立脚本 + 本 README |
| 与 `ime.py` 并行试用期、前端退役决定    | P5    | 按实际手感决定切换/双前端/回滚；`ime.py` 不提前删除   |

明确**放弃**的映射：内输模式（RIME 系统级候选窗即「外输」且更通用）、形部表悬浮窗、剪贴板同步。

### 4.2 回滚预案

1. 删除 `<RIME 用户资料夹>` 下 `jieshu*.{schema.yaml,dict.yaml}`、`build\jieshu*` 产物、
   `lua\jieshu_*.lua`、`lua\data\jieshu_*.txt`、`weasel.custom.yaml`（若原本没有）；
   安卓端另删 `trime.custom.yaml`；
2. 在「输入法设定」取消勾选解书音形（或还原 `default.custom.yaml`，改动前本机已有备份习惯）；
3. 托盘「重新部署」。其他方案与用户词库全程不受影响，仓库 `dict/` 与工具链零改动。

### 4.3 已知风险摘要

| #   | 风险                                             | 状态与缓解                                                                                      |
| --- | ---------------------------------------------- | ------------------------------------------------------------------------------------------ |
| R7  | 码表更新后忘记重导出                                     | 一条 `rime_export.py` 同时刷新词典、Lua 与方案配置；整理码表后手动执行                                             |
| R10 | Lua 查询层静默失效                                    | 三件套：`[jieshu_probe]` 采样日志 + 垫片首条 info（`VERBOSE` 可开明细）+ 离线回归快照；数据缺失时 `log.error` 上报；回滚预案保生产 |
| R11 | 单字母前缀候选量过大（最大桶约 900 条）                         | 目前实测无感；若出现卡顿，给 `query_by_prefix` 加截断按页供数                                                   |
| R12 | 安卓 Trime 部署要求方案词典存在，缺 `jieshu.dict.yaml` 即部署失败 | 导出默认始终生成该词典；Windows 端行为不受影响（见 2.1、2.3）                                                     |

（R1–R6、R8、R9 已在历轮实测中解除或消解。）