# 解书音形管理工具 · 直接命令参照

## 🖥️ Shell 环境

本机已安装 **PowerShell 7.6.3**，命令统一用 `pwsh` 执行（非 `powershell`）。
`pwsh` 支持 `&&`、`||` 链式操作、`Invoke-RestMethod` 等现代特性，比旧版 Windows PowerShell 更可靠。

---

## ⚠️ 操作方式优先级(重要)

与码表管理交互时，**优先使用 CLI 模式**（`main.py`），其次才是 SendKeys / PTY 模拟交互。

| 方式                          | 适用场景                       | 注意                    |
| --------------------------- | -------------------------- | --------------------- |
| `python main.py --<子命令>`    | **首选**。查询、添加、修改、音区分析、理据、词语 | 详见下方「main.py CLI 参考」节 |
| PTY + SendKeys              | 批量录入、猜测编码、需逐字选择读音/形码的词语录入  | 每次完整操作后会话终止           |
| 管道 `echo \| python main.py` | **不推荐**。仅极简单场景             | 多数功能不适用，易 EOF         |

**关键规则**：能用 `main.py --<子命令>` 完成的就不要走 PTY + SendKeys。

---

## main.py CLI 参考

```powershell
cd D:\USB\Py\输入法

# 查询字码
python main.py --query 解书音形
# → jx3k/uu11/yn1r/x;2m

# 音区分析
python main.py --analyze bc1

# 音区分析（交互模式）
python main.py --analyze

# 整理码表
python main.py --sort

# 添加单字
python main.py --add --char 解 --code jx75
# → [OK] 解 jx75
# 重码则输出「重码，添加失败」

# 修改编码
python main.py --modify --code jx75 --new-code jx76
# → [OK] 解 jx75 → jx76
# 旧编码不存在则输出「旧编码不存在」

# 删除条目
python main.py --modify --code jx75 --new-code x
# → [OK] 已删除 解 jx75

# 添加理据
python main.py --rationale --char 解 --text "角部+刀声"
# → [OK] 解 → 角部+刀声
# 多音字换行用 \n

# 添加词语（默认编码）
python main.py --ciyu --char 世界
# 二字词取两字双拼AB拼接，三字词以上用 generate_default_codes_for_word

# 添加词语（指定编码）
python main.py --ciyu --char 世界 --code "uoj4"
# 重码则输出「词语重码，添加失败」

# 查询词语是否录入（只查不写，无需 --char）
python main.py --ciyu --show 世界
# → 世界 uoj4 x;2m
# → 暂未录入（未录入时）

# 批量查询词语
python main.py --ciyu --show 测试 世界 表达

# 查询汉字理据（只查不写，多音字保留真换行）
python main.py --rationale --show 解
# → 解 xx4:角刀(四码→燮)
# → 暂无理据（无理据时）

# 打开键位图（编码规则/部首表/外输键位汇总）
python main.py --keymap

# 打开查询网页（输入编码查理据）
python main.py --query-web

# 同时打开两个
python main.py --keymap --query-web
```

**仍在交互菜单中的功能**：批量录入、猜测编码。

### 参数一览

| 参数                   | 说明                 | 配套参数                                    |
| -------------------- | ------------------ | --------------------------------------- |
| `--no-ime`           | 不启动输入法前端           | —                                       |
| `--query`            | 查汉字编码              | 直接跟汉字（空格分隔）                             |
| `--sort`             | 整理码表（排序、去重、生成网页数据） | —                                       |
| `--analyze [音码]`     | 分析音区，不传参数则进入交互模式   | —                                       |
| `--add`              | 添加单字               | `--char`(汉字) + `--code`(≥4位编码)          |
| `--modify`           | 编辑修改               | `--code`(旧编码) + `--new-code`(新编码或x)     |
| `--rationale`        | 添加理据               | `--char`(汉字) + `--text`(理据文本)           |
| `--ciyu`             | 添加词语               | `--char`(词语)，可选 `--code`(编码)            |
| `--show`/`--display` | 只查不写:查词语码表/理据      | 配合 `--ciyu` 或 `--rationale`,用位置参数传词语/汉字 |
| `--keymap`           | 打开键位图网页            | —（独立命令）                                 |
| `--query-web`        | 打开查询编码网页           | —（独立命令）                                 |

| 参数            | 打开的文件                     | 用途                                                                    | 相关文档                                                                      |
| ------------- | ------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| `--keymap`    | `help/webpage/键位图.html`   | 一图汇总**编码规则**（rules.md）、**部首表**（radical_table.md）、**外输操作键位**（usage.md） | `references/rules.md`、`references/radical_table.md`、`references/usage.md` |
| `--query-web` | `help/webpage/index.html` | 快速验证**编码与理据**：输入编码或汉字查字典条目、查看 `rationale` 字段（理据添加相关规定）                | `references/tools.md`「理据添加方法」节、`memory/06_其他约定性方法论.md`「理据添加方法」节           |

### 实现细节（无需用户关心，仅供 Agent 排错）

- 参数处理早于 `--no-ime` 检查之后的子命令分支——只要带上 `--keymap` 或 `--query-web` 任一者，就直接打开网页并 `return`，不会进入主菜单。
- 路径解析使用 `main.py` 所在目录的 `os.path.dirname(os.path.abspath(__file__))`，**不依赖 cwd**——从任意目录调用都能正确找到网页。
- `webbrowser.open('file://' + os.path.abspath(path))` 走系统默认浏览器。
- 若文件不存在（极少发生），打印 `警告：文件不存在 - <path>` 但不报错退出。

### 与现有功能的协同

```
理据添加工作流：
  推导编码 → python main.py --query-web
            ↑ 在网页里搜汉字，验证是否有理据、理据是否准确

键位图使用：
  记不清部首码 → python main.py --keymap
              ↑ 打开键位图，对照部首表和主码分类

设计者调试：
  两个网页同时打开 → python main.py --keymap --query-web
                  ↑ 一边看键位/规则，一边查码表/理据
```

---

## 启动输入法

```powershell
python "D:\USB\Py\输入法\ime.py"
```

## 码表录入

**首选 CLI**（同步去重排序）：

```powershell
python main.py --add --char <字> --code <编码>
```

**直接追加**（不排序去重，仅调试用）：

```powershell
Add-Content -Path "D:\USB\Py\输入法\dictionary.txt" -Value "<字> <编码>" -Encoding UTF8
```

## 整理码表

```powershell
python main.py --sort
```

等价于交互菜单选择 5。结果返回 `整理完成！码表条目：{单字}+{词语}`。

## PTY + SendKeys 交互操作规范（2026-06 实测）

> ⚠️ 以下内容适用于**仅支持交互模式**的功能（批量录入、猜测编码），以及需要逐字选择读音/形码的详细词语录入。
> 对于查询、添加、修改、理据等常见操作，**优先用上方 main.py CLI 命令**，无需 PTY。

管理程序 `main.py` 为 TUI 程序，通过 PTY 会话 + SendKeys 模拟人类操作。

### 基础操作模式

每次完整交互（选择一个功能→完成→退出）需重新建立 PTY 会话，流程如下：

1. **启动**：用 `exec` 启动 `python main.py`，指定 `pty: true` + `background: true`
2. **等待就绪**：`poll` 读取初始菜单输出，确认出现 `选项:` 提示
3. **发送按键**：`process send-keys` 发送按键序列
4. **读取结果**：`poll` 读取程序输出，判断是否进入目标功能
5. **循环交互**：按需重复「发送→等待→读取」
6. **会话结束**：操作完成后 PTY 会话自动终止（SIGKILL），重新启动新会话

### SendKeys 用法

```
process send-keys  sessionId=<id>  keys=[<键1>, <键2>, ...]
```

- `keys` 为数组，一次可发送多个按键（如 `["7", "Enter"]`）
- 中文汉字逐字发送（如 `["解", "书", "音", "形"]`），不要合并为单个字符串
- `literal` 参数可将一串字符整体发送（仅适合英文字母/数字）
- **不要**用管道 `echo` 向 PTY 会话输入——会导致 EOF 错误

### 读取程序输出

```
process poll  sessionId=<id>  timeout=<ms>
process log   sessionId=<id>
```

- `poll` 等待指定毫秒后返回当前缓冲内容，适合确认程序已处理
- `log` 获取全部历史内容，用于调试或取结果
- `timeout` 设为 2000-3000ms 足够覆盖大多数交互响应

### 典型交互示例（查询字码）

```
# 1. 启动
python main.py   (pty=true, background=true)

# 2. 等待菜单
poll timeout=2000
→ 应看到 "选项:" 提示

# 3. 选择功能7
send-keys keys=["7", "Enter"]

# 4. 等待提示
poll timeout=2000
→ 应看到 "连续汉字："

# 5. 输入汉字并查询
send-keys keys=["解", "书", "音", "形", "Enter"]

# 6. 读取结果
poll timeout=3000
→ 应返回 "jx3k uu11 yn1r x;2m"

# 会话自动结束，下一轮从头启动
```

### 常见问题处理

| 问题                        | 原因                 | 解决                           |
| ------------------------- | ------------------ | ---------------------------- |
| `No active session found` | PTY 会话已终止（SIGKILL） | 重新 `exec` 启动新会话              |
| 程序无响应                     | 光标未在正确提示处          | 先 `poll` 确认提示出现再发送           |
| 中文输入无回显                   | 中文未进入程序输入缓冲区       | 改用 `keys` 逐字发送，不要用 `literal` |
| 发送 Enter 后无反应             | 前一步输入尚未被程序接收       | 增加 `poll` 等待时间，或先确认输入已被回显    |

### ⚠️ 注意事项

- 每次功能操作需**重新启动 PTY 会话**，不要复用已结束的会话
- PTY 会话在操作完成后自动终止是正常现象，不是错误
- `send-keys` 的 `keys` 数组元素为**单个字符**，多字符汉字须拆成多个元素
- 发送按键后**必须等待**，否则程序来不及处理就发送下一轮输入

---

## 批量录入流程

> 批量录入仅支持交互模式，无 CLI 子命令。使用 SendKeys 或直接终端操作。

1. 发送 `1` + `Enter` → 进入"批量录入"
2. 发送**连续汉字**（如 `瘆`）+ `Enter` → 程序显示音码，等待形码
3. 程序显示 `形码:` 后，发送形码（如 `bs`）+ `Enter` → 录入完成

**⚠️ 注意**：发送菜单数字时，确保光标已在"选项:"提示处。

## 添加新字流程

1. 查码表确认该字不存在
2. 严格按规则推导编码
3. 用户确认编码正确
4. **首选**通过 CLI 录入：`python main.py --add --char <字> --code <编码>`
5. 若需批量逐字交互（含形码确认），用交互菜单功能1（批量录入）

## 日常测试

直接运行 `main.py`,按菜单提示操作。

## 查询码表

**禁止使用 `findstr` 查汉字**：`dictionary.txt` 是 UTF-8 with BOM，而 `findstr` 按系统默认编码（GBK）读取，汉字匹配必定失败。编码字母（ascii）能匹配，但汉字不行。

正确做法：用 PowerShell 的 `Get-Content -Encoding UTF8`。

### 按汉字查编码

**首选 CLI**（适合单个或少量汉字）：

```powershell
python main.py --query 辱
```

**PowerShell 直查**（适合批量/脚本）：

```powershell
(Get-Content "D:\USB\Py\输入法\dictionary.txt" -Encoding UTF8) | Where-Object { $_ -match "^辱" }
```

### 按编码前缀查（如查某前四码的所有字）

```powershell
(Get-Content "D:\USB\Py\输入法\dictionary.txt" -Encoding UTF8) | Where-Object { $_ -match " ru4u" }
```

### 查完整编码是否被占用

**CLI 快速判断**：直接 `--add` 试一次，重码会报「重码，添加失败」。

```powershell
python main.py --add --char 测 --code ce4u
# → 重码，添加失败   （说明已被占用）
```

**精确查证**：

```powershell
(Get-Content "D:\USB\Py\输入法\dictionary.txt" -Encoding UTF8) | Where-Object { $_ -match " ru4uc$" }
```

### 实用技巧

- `Select-String` 同样有编码问题，不推荐。
- 匹配词头时用 `^字`，匹配词尾时用 `编码$`。
- 查大范围时用 `Select-Object -First 10` 限制输出。

## 路径与数据源指南（AI 专用）

**核心规则**：本项目有两套目录，**职责严格分离**——

| 目录                                     | 职责                                          | 不应当做什么                                           |
| -------------------------------------- | ------------------------------------------- | ------------------------------------------------ |
| `D:\USB\Py\输入法\`                       | **项目仓库**，码表数据源（`dictionary.txt`、`ciyu.txt`） | **不应当**当作「与 skills 副本同步的规则文档」查阅——码表本体只在这里        |
| agent工作目录的`\skills\jieshu-yinxing-im\` | **外挂技能包**，规则与操作文档                           | **不应当**当作数据源；`scripts/` 提供 CLI 模拟器，但**码表本体仍在仓库** |

### 访问仓库的正确姿势

1. **绝对路径优先**：所有命令一律用完整路径 `D:\USB\Py\输入法\dictionary.txt`，不要假设 cwd 就在项目根。
2. **环境变量辅助**（脚本场景）：`$env:JIESHU_IME_HOME = "D:\USB\Py\输入法"`（CLI_emulation.py / jd_analyze.py / rationale_add.py 都用此约定）。
3. **汉字文件夹名的现实**：「输入法」是汉字文件夹名。PowerShell 行内写 `$_.Count` 等含美元符的表达式容易被外层 shell 反引号吞掉——**写盘到 .ps1 文件再 `pwsh -File 跑脚本`**，不要尝试行内一次性长字符串。
4. **BOM 注意事项**：`dictionary.txt` 是 UTF-8 with BOM，`findstr` 与未指定 `-Encoding` 的 `Get-Content` 默认按 GBK 读，必定失败。**必须显式 `-Encoding UTF8`**。

### 写码表相关笔记的标注规范

凡在 workspace 笔记、记忆文档、对话中引用码表统计/编码查询结果，**第一条必须标注**：

```
源文件：D:\USB\Py\输入法\dictionary.txt（或 ciyu.txt）
生成方式：Get-Content -Encoding UTF8 + ...（具体命令）
生成日期：YYYY-MM-DD
```

不标注源路径 = 让后续读者无法复现 = 与「不要脑内笔记」原则相悖。

## 统计主码分布（标准做法）

适用场景：评估码表各主码的字数占比、观察常用部首分布、为编码设计决策提供数据依据。

### 一步脚本（写入临时 .ps1 后运行）

```powershell
# 文件路径：count_main_codes.ps1
$lines = Get-Content 'D:\USB\Py\输入法\dictionary.txt' -Encoding UTF8
$entries = $lines | Where-Object { $_ -match '^\S+\s+\S+' }
$main = $entries | ForEach-Object { ($_ -split '\s+')[1].Substring(3,1) }
$stats = $main | Group-Object | Sort-Object Count -Descending
$total = $main.Count
"总条目数：$total"
$stats | Format-Table Name, Count, @{n='Pct%';e={[math]::Round($_.Count / $total * 100, 2)}} -AutoSize
```

运行：

```powershell
pwsh -NoProfile -File count_main_codes.ps1
```

### 字段含义

- `$entries`：跳过空行后所有形如「汉字 编码」的记录行
- `$main`：每个编码的**第四字符**（即主码，对应 `ABCD` 中的 `D`）。前三位是声韵调，第四位是部首码/独体字分类码
- `Name`：主码字符（数字 0-9 = 独体字，字母 b-z = 合体字部首码，**a/e/; 不会出现**）
- `Count`：该主码下的字数
- `Pct%`：占总数百分比

### 解读模板（拿到数据后必做的事）

1. **看头部**：单一主码占比超过 10% 通常意味着部首表里该行集合了多个高产能意旁（如 `u` = 手/水/食/攵）
2. **看数字行**：0-9 主码合计 4-6% 是正常的（独体字少且均匀分摊）；超过 8% 说明合体字判定可能偏严
3. **看 `a/e/;`**：这三字母不应出现；若出现，说明有编码违规或独体/合体判定错误，需要查证
4. **看字母长尾**：l/v/o/p 通常字数最少（66 / 60 / 53 / 48），是「冷辟部首」指示器——输入时极少触发

### 工作流建议

```
推导新编码
    │
    ├─ 1. 查主码分布（本研究）── 看目标字的部首在哪个主码行，与现有字数横向对比
    ├─ 2. 查部首别码（rules.md §3.2）── 别码部首 vs 音托部首的区分
    ├─ 3. 查相关字（memory/05 §编码前查相关字）── 余字编码、同 ABCD 组
    └─ 4. 推导 → 验证（码表查重）→ 录入
```

## 推送新 commit 办法

每次推送新版本时，执行以下流程：

### 1. 获取当前条目数

```powershell
python "D:\USB\Py\输入法\main.py" --sort
# → 整理完成！码表条目：{单字}+{词语}
```

`--sort` 顺带完成排序去重，输出行直接给出「单字数+词语数」，无需再用 PowerShell 逐文件统计。

### 2. 确定版本号

当前版本序列为 `v0.6.6-beta.N`，从 beta.1 开始递增。

### 3. 组合提交信息

**主标题（强制）**：`v0.6.6-beta.{N}, {dict条目数}+{ciyu条目数}`

例：`v0.6.6-beta.1, 7124+1304`

**副标题（可选）**：若有除码表条目增长以外的改动（代码改动、功能新增、bug 修复等），写入 commit message body，不放在主标题中。纯码表条目更新只需主标题。

### 4. 提交并推送

```powershell
cd "D:\USB\Py\输入法"
git add .

# 纯码表更新（无副标题）
git commit -m "v0.6.6-beta.{N}, {条目数}"

# 有代码/功能改动（含副标题）
$body = @"
v0.6.6-beta.{N}, {条目数}

副标题内容（代码改动、功能新增、bug 修复等）
"@
$body | Out-File -Encoding UTF8 C:\Users\yuifsama\AppData\Local\Temp\commit_msg.txt
git commit -F C:\Users\yuifsama\AppData\Local\Temp\commit_msg.txt
```

推送（如遇证书问题加 ssl 参数）：

```powershell
git -c http.sslBackend=schannel -c http.schannelCheckRevoke=false push origin main
```

## 目标路径

所有操作默认在 `D:\USB\Py\输入法\` 下进行。

---

## 理据添加方法

理据存储在 `help/webpage/dictionary-data.js` 的 `rationale` 对象中，JSON 格式，key 为汉字、value 为理据文本。

判定与撰写约定（理据精简原则、`/` 占位规则、格式约定、添加前必查等）参照记忆文档 [06_其他约定性方法论](../memory/06_其他约定性方法论.md)。

### 添加方式

#### 方式一：CLI 快速添加（推荐，2026-08 新增）

```powershell
python main.py  --rationale --char 油 --text "水部+由声"
```

多音字用 `\n` 换行：

```powershell
python main.py --rationale --char 乐 --text "le4：木部+幺\nyue4：五声八音总名"
```

#### 方式二：互动脚本（适合人工逐条添加）

```powershell
$env:JIESHU_IME_HOME = "D:\USB\Py\输入法"
py "jieshu-yinxing-im\scripts\rationale_add.py"
```

然后选模式 `3`（指定汉字），输入汉字 → 输入理据。`\n` 表示换行。

⚠️ 注意：此脚本为交互式终端程序，**不可用管道输入**，否则会 EOF 报错。

#### 方式三：命令行快速添加（适合批量/自动化）

用一段 Python 脚本直写 JSON，避开交互式限制：

```powershell
py -c @"
import json, re, sys
char, rat = sys.argv[1], sys.argv[2]
WEB = r'D:\USB\Py\输入法\help\webpage\dictionary-data.js'
with open(WEB, 'r', encoding='utf-8') as f:
    content = f.read()
m = re.search(r'rationale:\s*(\{)', content)
start = m.start(1)
depth = 0; end = start
for i in range(start, len(content)):
    if content[i] == '{': depth += 1
    elif content[i] == '}':
        depth -= 1
        if depth == 0: end = i + 1; break
r = json.loads(content[start:end])
r[char] = rat
new_json = json.dumps(r, ensure_ascii=False, separators=(',', ':'))
content = content[:start] + 'rationale: ' + new_json + content[end:]
with open(WEB, 'w', encoding='utf-8') as f:
    f.write(content)
print(f'ok: {char} -> {rat} | total: {len(r)}')
"@ -- "油" "水"
```

或者把上述代码存为独立脚本文件，方便复用。

### 验证

添加后用 PowerShell 抽查：

```powershell
$content = Get-Content "D:\USB\Py\输入法\help\webpage\dictionary-data.js" -Encoding UTF8 -Raw
if ($content -match '"油":\s*"([^"]*)"') { Write-Host "油: $($matches[1])" }
```

---

## CLI 模拟器（CLI_emulation.py）

位于技能文件夹的`jieshu-yinxing-im/scripts/CLI_emulation.py` 是一个命令行模拟输入法前端，用于在没有 GUI 的环境中测试编解码逻辑。

### 功能

- 单字 / 多字编码输入
- 词语优先上屏（短语查询）
- 候选选择（`!` `@` `#` `$` `%`）
- 多部件导航（`=` 下一个，`-` 上一个）
- 自动上字（编码长度 > 3 且唯一候选时）
- 交互模式 + 管道模式双支持

### 交互模式

```powershell
python scripts/CLI_emulation.py
```

每行输入一个编码串，末尾自动补空格提交。输入 `exit` 或 `quit` 退出。

```
> yi4r
上屏结果: 亿
> wo3g
上屏结果: 我
> exit
```

### 管道模式

每行一个编码串，输出对应汉字。空行输出空行。

```powershell
# 单行
Get-Content input.txt | python scripts/CLI_emulation.py
```

```powershell
# 批量测试
echo yi4r | python scripts/CLI_emulation.py
```

⚠️ PowerShell 的 `echo` 管道有编码兼容问题，推荐用 Python 管道或 `Get-Content`：

```powershell
"yi4r" | python scripts/CLI_emulation.py
```

### 编码规则速查

| 操作      | 按键                  | 说明          |
| ------- | ------------------- | ----------- |
| 提交      | 空格（末尾自动添加）          | 将当前编码转为汉字上屏 |
| 选候选     | `!` `@` `#` `$` `%` | 对应第1-5个候选   |
| 短语上屏    | `!`（有短语时）           | 优先于候选选择     |
| 多部件-下一个 | `=`                 | 跳到下一个未选部件   |
| 多部件-上一个 | `-`                 | 跳到上一个未选部件   |
| 翻页      | 暂不支持（CLI 仅首页）       | —           |

### 实现说明

- 每次输入创建独立的 `SimulatedIME` 实例（状态不跨行污染）
- 复制了 `ime.py` 的全部核心处理逻辑（`_replace_content`、`_navigate_parts`、`_handle_selection_keys` 等）
- 依赖 `manager/dictionary_frontend.py` 和 `config.py`，通过 `JIESHU_IME_HOME` 环境变量或默认路径定位项目目录
- 多部件选择采用渐进式提交：每选一个部件补全对应编码剩余部分，全部选完后拼接汉字串上屏
- CLI 模拟器与 `ime.py` 共享完全相同的查询链路（`dictionary_frontend.py` + `dictionary.txt`），仅在最终呈现方式上分叉（终端打印 vs GUI 渲染）。这意味着 CLI 的查询结果、候选排序、自动拆分、上屏逻辑与真实前端在逻辑层**等价**

### 验证能力矩阵

| 能力                         | CLI 模拟器     | 真实前端    |
| -------------------------- |:-----------:|:-------:|
| 前缀匹配 / 候选排序                | ✅           | ✅       |
| 自动拆分 (`split_sequence`)    | ✅           | ✅       |
| 自动上字 (`auto_commit`)       | ✅           | ✅       |
| 词语优先 (`query_phrase`)      | ✅           | ✅       |
| 多部件选择 (`=` `-` `!` `@`)    | ✅           | ✅       |
| 候选选择 (`!` `@` `#` `$` `%`) | ✅           | ✅       |
| 管道模式批量回归                   | ✅           | ❌       |
| 副码 a 占空逻辑                  | ✅           | ✅       |
| 显式分隔符 `'`                  | ✅           | ✅       |
| 关闭自动上字                     | ❌（写死 `"1"`） | ✅（设置面板） |
| GUI 渲染 / 半透明窗口             | ❌           | ✅       |
| 内输 / 外输切换                  | ❌           | ✅       |
| 剪贴板同步                      | ❌           | ✅       |
| 部首表 UI 展示                  | ❌           | ✅       |

### 在设计者工作流中的位置

```
1. 推导编码
      │
2. 查重验证（PowerShell Get-Content 查码表）
      │
3. 录入码表（`python main.py --no-ime --add --char <字> --code <编码>`）
      │
4. 前端验证（CLI 模拟器）── 前缀命中深度、候选排序位置
      │
5. 拆分验证 ── 多字编码自动拆分是否正确
      │
6. 简打分析（jd_analyze.py）── 最短编码、空格必要性、词组命中
      │
7. 回归测试（管道模式跑已有用例）
      │
8. 推送 commit
```

第 4-7 步均依赖 CLI 模拟器。设计者无需启动 GUI、无需肉眼逐个判断候选，即可完整验证一条新编码在实际输入场景中的全部表现。

---

## 简打分析器（jd_analyze.py）

位于 `jieshu-yinxing-im/scripts/jd_analyze.py`，专用于分析多字编码串的简打机制。

### 功能

对一段多字编码串执行四项自动化分析：

1. **逐段拆分** — 每个子段对应哪个字、全码、输入码、简打级、省码数
2. **最短性验证** — 逐字缩短一级看首选是否仍是目标字（若 `zf3` 的 3 可省 → 标记「可缩为 zf」）
3. **空格必要性** — 去掉空格后重新拆分，对比正确率，标记粘连点
4. **词组命中** — 检测是否有段通过 `query_phrase` 走词库捷径

### 用法

```powershell
# 分析单句
python jd_analyze.py th3r row xnvsd ujuv3
python jd_analyze.py "wbm4r yibu4v yilmhw qidk3"

# 跑副歌六句全套
python jd_analyze.py --all

# 纯数据输出（不显示表格，适合管道后处理）
python jd_analyze.py -q --all
```

### 输出示例

```
======================================================================
  原文: 我便一步一莲花祈祷
  编码: wbm4r yibu4v yilmhw qidk3
======================================================================

  字      段位         全码       输入         级          省
  ----------------------------------------------------------
  我      w          wo3g     w          一级         3
  便      bm4r       bm4r     bm4r       四码全码       0
  一      yi         yi12     yi         AB二码       2
  步      bu4v       bu4v     bu4v       四码全码       0
  一      yi         yi12     yi         AB二码       2
  莲      lm         lm2c     lm         AB二码       2
  花      hw         hw1c     hw         AB二码       2
  (祈祷)   qidk3      (词组)     qidk3      词语匹配       -
  ----------------------------------------------------------
  计: 22 字符 vs 全码 28 → 省 21%

  字      输入         判定             说明
  ----------------------------------------------------
  我      w          ✓ 已最短          None
  便      bm4r       ✓ 已最短          少一位 bm4 → 釆
  ...
  [(祈祷)] qidk3      (词语匹配)        

  ▸ 空格必要性测试
  无空格拆分: w'bm4ry'i'bu4vy'il'mh'wq'i'dk3
  子段         首选字        状态        
  ----------------------------------
  bm4ry      —          ✗ 无效码    ← 粘连点
  ...
  共 3 段无效，正确 6/9

  ▸ 词组匹配: 1 处
    qidk3 → (祈祷)
```

### 实现说明

- 依赖 `manager/dictionary_frontend.py`（与 CLI 模拟器共享同一查询链路）
- 通过 `JIESHU_IME_HOME` 环境变量定位项目目录（默认 `D:\USB\Py\输入法`）
- `query_by_prefix` 返回候选格式为 `"字剩余编码"`（如 `"若4c"`），脚本取首字符为汉字
- 全码从 `dictionary.txt` 独立查询，词组从 `ciyu.txt` 通过 `query_phrase` 获取
- `--all` 模式下依次分析《半壶纱》副歌六句，可快速回归所有已知简打场景

### 设计原理

脚本的核心逻辑对应《04_前端简打机制》中的四条实战规则：

| 分析维度  | 对应规则          | 实现方式                                  |
| ----- | ------------- | ------------------------------------- |
| 最短性验证 | 每字打到排第一就停     | `try_shorter()` 逐位缩短前缀查首选             |
| 词语匹配  | 词库优先于拆分       | `query_phrase()` 优先于 `split_sequence` |
| 空格必要性 | 四码全码必空格       | 去掉空格对比拆分结果                            |
| 段内连续  | C1/C2 自动切分可行域 | 有空格段的 `split_sequence` 输出             |

### 自动上字模拟（v2 新增第五项分析）

分析器内置 `simulate_typing()` 逐字符模拟前端 `_on_input_change` 的自动上字流程：

- 对每段编码逐字符累加 → `process_input` 过滤 → `split_sequence` 拆分
- 若未拆分（单段）且 `len > 3` 且唯一非点候选 → 触发自动上字，缓冲区清零
- 多段或候选不唯一 → 不触发，继续累加

**关键设计：逐空格段独立模拟**，而非去空格全串模拟。前端收到空格 → `_on_input_change` 上屏 + 清空缓冲区 → 下一段重新开始，分析器完全复现这一行为。

#### 输出示例

```
  ▸ 自动上字模拟（含空格，逐段独立输入）

  段 gp3ugp3uih2 → 滚滚长 （1字不触发）
  触发码          上屏       预期       判定    
  --------------------------------------
  gp3u         滚        滚        ✓
  gp3u         滚        滚        ✓
  (未触发)        —        长        —   len=3，未达4码不触发；空格或打全码 ih24 手动上屏

  段 jd1u → 江 （1字不触发）
  (未触发)        —        江        —   入 jd1u 后 split_sequence 拆为多段，不触发；空格或打全码 jd1u 上屏

  段 dsui4zvuv3 → 东逝水 （3字不触发）
  (未触发)        —        东        —   len=2，未达4码不触发；空格或打全码 ds14 手动上屏
  (未触发)        —        逝        —   入 ui4zv 后 split_sequence 拆为多段，不触发；空格或打全码 ui4zv 上屏
  (未触发)        —        水        —   len=3，未达4码不触发；空格或打全码 uv36 手动上屏

  触发 2 次，全部正确 ✓
```

#### 对比验证：有无空格

| 输入                       | 自动上字行为                                                  |
| ------------------------ | ------------------------------------------------------- |
| `ih2jd1`                 | `ih2j` 唯一候选「常」≠「长」→ ✗ 错误上字                              |
| `ih2 jd1`                | 逐段独立：「长」len=3 不触发、「豇」len=3 不触发 → 无自动上字，安全               |
| `ih2` + 空格 + `jd1`（前端实际） | 空格触发 on_input_change → 手动确认「长」上屏 → jd1 独立输入 → 手动确认「豇」上屏 |

#### 分析逻辑

```python
def simulate_typing(code_str):
    """逐字符模拟，返回 (auto_commit_events, residual_code)"""
    accumulated = ""
    events = []
    for ch in code_str:
        if ch not in CODE_CHARS:
            continue
        accumulated += ch
        processed = process_input(accumulated)
        if len(processed) <= 3:
            continue
        spl = split_sequence(processed)
        if "'" in spl:           # 已拆分 → 不触发
            continue
        cands = query_by_prefix(spl)
        non_dot = [c for c in cands if '.' not in c[1:]]
        if len(non_dot) == 1:    # 唯一候选 → 触发
            events.append((processed, non_dot[0][0]))
            accumulated = ""
    return events, process_input(accumulated)
```

#### 不触发原因分类

| 原因                        | 示例                         | 正确应对                        |
| ------------------------- | -------------------------- | --------------------------- |
| `len < 4`，未达自动上字阈值        | `ds`(2码)、`uv3`(3码)         | 空格或打全四码                     |
| 入 `split_sequence` 后被拆为多段 | `jd1u`(4码但拆)、`ui4zv`(5码但拆) | 空格或打全码（多段时 auto-commit 不生效） |
| 唯一候选 ≠ 目标字（抢断错误）          | `ih2j`→常 而非 长              | 加空格声明边界                     |

---

## 简打编码生成器（generate_jd_codes.py）

位于 `jieshu-yinxing-im/scripts/generate_jd_codes.py`，输入任意汉字串，输出其简打编码方案。是设计者工作流中「6. 简打分析」的升级工具——集成词语匹配、最短编码、空间段划分、CLI 一致性验证于一体，一键生成可立即上机使用的编码串。

### 核心逻辑

```
输入: 汉字串
  │
  ├─ 1. 词语优先匹配 ── 从 ciyu.txt 中查找最长前缀词组，命中则作为整体编码段
  │
  ├─ 2. 单字最短编码 ── 未命中词组的字独立查 dictionary.txt
  │      · 一个汉字可能有多个全码变体（如「看」有 kj1m 和 kj4m）
  │      · 对每个全码单独逐位缩短，取全局最短者
  │      · 只要首位候选仍是目标字，编码就能继续缩短
  │
  ├─ 3. 自动合并相邻段 ── 若相邻段能安全合入同一空格区间
  │      · split_sequence 静态拆分检查
  │      · auto-commit 时间线模拟（逐字符输入，自交截断检测）
  │      · 合并优先级：左优先，先合并短段
  │
  ├─ 4. 空格分配 ── 按 04_前端简打机制 的「无冲突则不加空格」原则
  │      · 去空格后 split_sequence 无法正确拆分 → 空格必要
  │      · 去空格后仍能正确拆分 → 空格可选（默认不加）
  │
  └─ 5. CLI 验证 ── 通过 CLI_emulation.py 管道回灌编码串
         · 逐段独立送入（空格触发缓冲区清空）
         · 对比上屏结果与原文 → [OK] 一致 / [FAIL] + 差异
```

### 用法

```powershell
# 单句生成
py generate_jd_codes.py "滚滚长江东逝水"
py generate_jd_codes.py "倘若我心中的山水"

# 批量生成（多参数逐一处理）
py generate_jd_codes.py "办公自动化" "人工智能" "键盘鼠标"

# 从文件读取（每行一句）
py generate_jd_codes.py -f lyrics.txt

# 静默模式（仅输出编码串，适合管道/批量导出）
py generate_jd_codes.py -q "滚滚长江东逝水"
# → gp3ugp3uih2 jd1u dsui4zvuv3

# 跳过 CLI 验证（离线/快速预览）
py generate_jd_codes.py --no-verify "测试文本"
```

### 输出示例

```
========================================================================
  原文: 滚滚长江东逝水
  简打: gp3ugp3uih2 jd1u dsui4zvuv3
  验证: [OK] 通过
========================================================================

  字/词      编码         全码         省      类型
  ----------------------------------------------------
  滚        gp3u       gp3u       0
  滚        gp3u       gp3u       0
  长        ih2        ih24       1
  江        jd1u       jd1u       0
  东        ds         ds14       2
  逝        ui4zv      ui4zv      0
  水        uv3        uv36       1

  >>  编码段 (3段):
      [滚滚长] -> gp3ugp3uih2
      [江] -> jd1u
      [东逝水] -> dsui4zvuv3

  >>  空格必要性:
      gp3u           -> 滚      OK
      gp3u           -> 滚      OK
      ih2            -> 长      OK
      jd1ud          -> -      INVALID
      s              -> 所      OK
      ui4zv          -> 逝      OK
      uv3            -> 水      OK
      无空格时 1 段无效 -> 空格必要

  >>  统计: 7字 -> 25码 (省4码)
  >>  CLI验证: [OK] 一致
```

### 输出解读

| 区域    | 内容                          | 含义                        |
| ----- | --------------------------- | ------------------------- |
| 字/词表格 | 每个字的最短编码、全码、省码数             | 「省」= 全码长度 − 简打长度          |
| 编码段   | 空格分隔后的各段及其对应汉字              | 展示合并/拆分的最终形态              |
| 空格必要性 | 去掉空格后逐字检查                   | `INVALID` = 粘连破坏拆分，空格必须保留 |
| CLI验证 | 管道回灌 CLI_emulation.py 的上屏结果 | 比对比原文 → OK / FAIL + 差异文本  |

### 与 jd_analyze.py 的关系

| 维度             | jd_analyze.py             | generate_jd_codes.py |
| -------------- | ------------------------- | -------------------- |
| 输入             | 编码串（th3r row xnvsd ujuv3） | 汉字串（倘若我心中的山水）        |
| 输出             | 分析已有编码的合理性                | 生成编码方案 + 验证          |
| 词语匹配           | 检测编码中是否命中词组               | 主动从 ciyu.txt 查找最长前缀词 |
| auto-commit 模拟 | 逐空格段独立模拟                  | 段合并时模拟时间线截断          |
| 用例             | 设计者手写编码后验证                | 输入汉字→直接输出可用编码        |

`generate_jd_codes.py` 是正向生成器——给它汉字，它给你编码。`jd_analyze.py` 是反向审查器——给它编码，它告诉你这段编码是否最优、空格是否必要。两者互补。

### 设计要点

**多全码变体处理**：字典中一个汉字可能有多条记录（如「看」有 `kj1m` 和 `kj4m`），生成器遍历所有变体，独立缩短，取全局最短。这解释了为什么「你眼中都看到」→ `kj4`(3码) 而非 `kj1m`(4码)。

**自交截断模拟**：`_simulate_auto_commit()` 逐字符输入编码串，模拟前端 `_on_input_change` 的自动上字流程——当单段长度 > 3 且唯一非点候选时触发自交，缓冲区清零。这确保 `gp3ugp3uih2` 合并后不会因 `gp3u` 自交截断导致 `ih2j` 被错判。

**词语优先但不高估**：词组编码始终取完整（不缩短），因为词组是整体查询——`qidk3` 不会缩短为 `qidk`，缩短后 `query_phrase` 可能匹配到不同的词。

### 在设计者工作流中的替代

此工具替代原工作流中「6. 简打分析（jd_analyze.py）」的大部分场景：

- **想分析手写编码是否最优** → 继续用 `jd_analyze.py`
- **想为一句话生成简打方案** → 用 `generate_jd_codes.py`，因为它从零生成 + 验证，无需先写出编码再送分析

### 依赖

- `manager/dictionary_frontend.py`（split_sequence / query_by_prefix / query_phrase / process_input）
- `dictionary.txt` / `ciyu.txt`（项目数据，通过 `JIESHU_IME_HOME` 定位）
- `scripts/CLI_emulation.py`（管道模式 CLI 验证，通过 `py` 拉起子进程）

---

#### 与旧版空格必要性测试的区别

空格必要性测试回答：**去掉空格后，split_sequence 拆分是否出错？**（针对 C2 盲区）

自动上字模拟回答：**带空格输入时，每段内部是否触发自动上字？结果是否正确？**（针对 auto-commit 抢断）

两者互补——空格必要性从反面证明空格不能省，自动上字模拟从正面验证空格段内的自动行为是否安全。

---

## ⚠️ Agent 工作纪律 · 文件修改后必回读（2026-07-27 立）

任何对项目文件的**写盘动作**（`edit` / `write` / `apply_patch` / `exec` 走文件操作）之后，必须**立即 read 回读**该文件相关区段**至少 5 行**，确认修改**真的落到了你以为的地方**。

### 为什么需要这条纪律

`edit` 工具的返回 `Successfully replaced N block(s)` 只代表**有 N 处匹配并被替换**——**不代表**匹配的就是你以为的那段。当一次 `edit` 调用内含多个 `edits[]`，且其中一个 `oldText` 实际匹配到了**别的位置**时，工具仍可能返回成功，但你的真实意图并未落地。

事故实例（2026-07-27）：

- Agent 想同时改 §三 引言段 + 3.5 节两条记录
- 实际只 3.5 节那条匹配成功，§三 引言段仍为旧版
- Agent 看到工具返回 "Successfully" 便以为两条都改好，未回读
- 用户再读文件发现 §三 引言段未变，Agent 才发现漏改

### 正确做法（三步走）

```
1. read  →  从目标文件读出真实原文
2. copy  →  把原文片段（必须含 全角/半角 一致的标点）作为 oldText
3. edit  →  写盘
```

写盘之后**必须**：

```
4. read  →  再次读相同区段，至少 5 行
5. verify →  对比修改是否落在正确位置、字符级是否一致
```

### 常见踩坑场景

| 踩坑                            | 原因                             | 正确做法                                     |
| ----------------------------- | ------------------------------ | ---------------------------------------- |
| 凭记忆写 oldText，结果匹配失败           | 实际文件用全角标点（：` `"` ——），Agent 用半角 | read 出来直接 copy，不要在脑子里默写                  |
| 一次 edit 含多条 edits[]，部分未匹配但报成功 | 工具以"匹配成功的条数"回报，Agent 误以为全成     | 每条 edits 单独验证、或拆分多次 edit 调用              |
| BOM 文件开头不可见字符导致首行不匹配          | 文件首 3 字节是 EF BB BF             | 用 read 看首字符是否含 `\ufeff`，构造 oldText 时保持一致 |
| "想必改对了" 主观判断                  | 工具报成功 ≠ 改对                     | **永远 read 回读**——这是纪律不是建议                 |
| 走 Python 旁路脚本绕过 edit 字符匹配     | 临时补丁脚本污染工作目录、触发安全拦截、还要清理       | 不走旁路；老老实实 read+copy+edit                 |

### 与现有工作的衔接

- 本节**不替代** `操作方式优先级` 节里"不要优先使用管道"的纪律——两条都遵守
- 本节**与 `MEMORY.md` 里"不要靠脑内笔记,需要记住的事情直接写入"**是同类：**所有可被工具验证的事情不靠主观判断**
- 本节**适用于 Agent 工作流**——既是提醒 Agent 自己，也方便解书管理员审视 Agent 是否按此执行

### 适用工具清单

| 工具                            | 写盘动作    | 适用本节规则 |
| ----------------------------- |:-------:|:------:|
| `edit`                        | ✅       | ✅      |
| `write`                       | ✅       | ✅      |
| `apply_patch`                 | ✅       | ✅      |
| `exec` 走文件操作（cp/mv/sed 等）     | ✅       | ✅      |
| `cron.add` / `cron.update`    | ❌（不写文件） | ❌（不适用） |
| `message.send` / `tts`        | ❌（不写文件） | ❌（不适用） |
| 纯查询工具（read / search / grep 等） | ❌（只读）   | ❌（不适用） |

---
