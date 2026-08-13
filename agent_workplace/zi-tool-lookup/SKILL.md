---
name: zi-tool-lookup
description: |
  字统网（zi.tools）汉字查询技能。主引擎：Crawl4AI（Playwright 渲染 + Markdown 文本提取）。辅助：xbrowser（截图，仅用于视觉内容如字形演化图、书法）。
  当用户要求查字、查汉字、查询汉字信息，或提到"字统网"、"zi.tools"、"查一下这个字"时使用此技能。
  支持功能：汉字基本信息（笔画、部首、结构）、读音（普通话/粤语/日语/韩语/越南语等）、
  字义与字源释义、音韵学资料（韵书反切拟音上古音）、异体字、方言读音、用字对比。
install_method: upload
---

# 字统网查字技能（Crawl4AI 版）

> **主引擎：Crawl4AI**（Playwright 渲染 + Markdown 提取），**辅助：xbrowser**（视觉内容截图）。

## 环境变量

```bash
# Crawl4AI Python 路径
PYTHON = D:\python\python.exe

# xbrowser（仅视觉内容时使用）
NODE="${QCLAW_CLI_NODE_BINARY:-node}"
XB="C:\Users\yuifsama\.qclaw\skills\xbrowser\scripts\xb.cjs"
```

## 核心工作流

### 标准查字流程（3 步）

**Step 1 — 用 Crawl4AI 抓取页面的 Markdown 文本**

编写并执行临时 Python 脚本（写入 workspace 如 `zi_crawl.py`，用完可删），核心逻辑：

```python
import asyncio, json, io, sys
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# ★ 把下面这个 URL 替换为实际的字统网 URL
TARGET_URL = "https://zi.tools/zi/{URL_ENCODED_CHAR}"
OUTPUT_FILE = r"C:\Users\yuifsama\.qclaw\workspace\zi_result.json"

async def main():
    from crawl4ai import AsyncWebCrawler, CrawlerRunConfig, CacheMode

    config = CrawlerRunConfig(
        cache_mode=CacheMode.BYPASS,
        wait_until="networkidle",
        page_timeout=30000,
        excluded_tags=["script", "style", "nav", "footer"],
        only_text=False,
        word_count_threshold=1,
    )

    async with AsyncWebCrawler() as crawler:
        result = await crawler.arun(url=TARGET_URL, config=config)

        with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                "success": result.success,
                "markdown": result.markdown or "",
                "length": len(result.markdown or ""),
                "error": str(result.error_message) if not result.success else None
            }, f, ensure_ascii=False, indent=2)

        print(f"DONE: success={result.success}, chars={len(result.markdown or '')}")

asyncio.run(main())
```

执行：`& "$PYTHON" "C:\Users\yuifsama\.qclaw\workspace\zi_crawl.py"`，超时 60 秒。

读取 `zi_result.json` 的 `markdown` 字段获得全文。

**Step 2 — 解析 Markdown 并结构化输出**

从 markdown 中提取以下板块，按需呈现：

| 板块   | Markdown 中的识别特征                         | 内容               |
| ---- | --------------------------------------- | ---------------- |
| 基本信息 | `U+XXXX`、`X部X畫`、`共X畫`、`⿰` 结构描述          | Unicode、部首、笔画、结构 |
| 读音   | `官話`、`粵語`、`日語`、`韓語`、`越南`                | 各语言方言读音          |
| 字义   | `Meaning 字義`                            | 主要义项列表           |
| 字源   | `Origin 字源諸說`                           | 《字源》等来源          |
| 音韵   | `Phonology 音韻`、`廣韻`、`集韻`、韵书标注           | 韵书、反切、拟音         |
| 上古音  | `上古音`、`高本漢`、`王力`、`鄭張尚芳`、`Baxter-Sagart` | 各家拟音             |
| 方言   | `Dialects 方言`                           | 各地方言读音（数据量极大）    |
| 异体字  | `Kinship`、`異體字圖譜`                       | 异体字列表            |
| 用字对比 | `Comparison 用字對比`、陆/港/台/日/韓             | 繁简地区对比           |

**Markdown 中的读音识别：**

| 语言  | 标记                       | 示例         |
| --- | ------------------------ | ---------- |
| 官话  | `ce4(測)`                 | 拼音+声调数字    |
| 粤语  | `cak1`、`caak1`           | 粤拼+声调数字    |
| 日语  | `ソク(測)`、`ショク(測)`、`シキ(測)` | 片假名(+对应汉字) |
| 韩语  | `측`                      | 谚文         |
| 越南  | `trắc(測)`                | 国语字(+对应汉字) |
| 广韵  | `初/職開/入(測)`              | 声母/韵母/声调   |

**韵书信息识别：**

- 格式：每行包含 `韵书名称 + 声母 + 韵母 + 开合 + 声调 + 反切 + 拟音 + 释义`
- 常见韵书：廣韻、集韻、刊謬補缺切韻、禮部韻略、增韻、五音集韵、洪武正韻、古今韻會舉要、蒙古字韻、音韻闡微、中原音韻、韻略易通、中州音韻、中華新韻、東國正韻、戚林八音、分韻撮要

**Step 3（可选）— 需要视觉内容时用 xbrowser 截图**

仅当用户明确想看**字形演化图、书法作品、康熙字典扫描**等视觉内容时才用 xbrowser。

```bash
# 初始化
"$NODE" "$XB" init

# 打开页面
"$NODE" "$XB" run --browser default open 'https://zi.tools/zi/{URL_ENCODED}'

# 等待加载
"$NODE" "$XB" run --browser default wait --load networkidle

# 截图
"$NODE" "$XB" run --browser default screenshot

# 复制截图到 workspace
# 然后 image 工具分析

# 清理
"$NODE" "$XB" cleanup
```

截图文件路径在返回的 `data.result.data.path` 中。

> ⚠️ xbrowser 的 `snapshot -i` 和 `get text` 对 zi.tools **无效**（页面 DOM 太重导致连接超时 os error 10060），**禁止使用**。

## 查字结果输出格式

查到字后，以结构化摘要呈现：

1. **基础信息**：Unicode、部首、笔画、结构（IDS 分解）
2. **读音**：普通话拼音 + 粤拼 + 其他常用语言
3. **字义**：简要表述主要义项
4. **字源与异体**：字源说 + 简化/异体关系
5. **韵书与上古音**（如用户要求深入）：选摘关键韵书 + 主要学者拟音
6. **同部首相关字**（如用户感兴趣）：从结构树链接提取

保持简洁，不堆砌字符集索引细节。方言读音默认不列（数据量极大），除非用户明确要求。

## Crawl4AI vs xbrowser 分工

| 任务                   | 用 Crawl4AI | 用 xbrowser       |
| -------------------- |:----------:|:----------------:|
| 查字文本（读音/字义/音韵/方言/异体） | ✅ 主引擎      | ❌ snapshot 超时不可用 |
| 字形演化图（图片）            | ❌          | ✅ 截图             |
| 书法作品（图片）             | ❌          | ✅ 截图             |
| 康熙字典扫描               | ❌          | ✅ 截图             |
| 页面正常渲染确认             | ❌          | ✅ 截图             |

## 常见陷阱

1. **不要用 xbrowser snapshot/get text** — zi.tools 的 DOM 过重，这两个操作必然超时（连接超时 os error 10060）
2. **汉字必须 URL 编码** — 如「测」→ `%E6%B5%8B`
3. **Python 输出必须 UTF-8** — 脚本内第一行必须是 `sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')`，否则含 IDS 字符（如 `⿰`）会触发 GBK 编码错误
4. **结果写入文件而非 stdout** — 避免编码问题，用 JSON 文件传递数据
5. **Crawl4AI 首次运行会下载 Playwright 浏览器** — 已就绪，无需额外安装（当前：Crawl4AI 0.9.0，位于 `D:\python\Lib\site-packages`）

## 任务结束

- Crawl4AI：脚本执行完后自动清理，`with` 块退出即关闭浏览器
- xbrowser（如使用）：运行 `"$NODE" "$XB" cleanup`
- 清理临时 Python 脚本（可选）

### **注：技能修改权限：**

- **本技能为用户自定义技能，可以任意修改和更新，无权限限制**
- 用户可以根据需要调整输出格式、添加新的操作方案、修改相关逻辑等
- 所有修改都是安全的，不会影响系统其他部分
