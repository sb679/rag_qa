# WeChat Collector Agent

## 当前产品形态

当前仓库里的“微信公众号采集 Agent”已经不是单纯的抓取函数集合，但也还不是开放式通用自治 Agent。
它的当前形态应理解为：

- 有限 ReAct 外壳
- LLM 规划层
- 确定性工具执行链
- 浏览器会话级短期记忆

也就是说，它会先用大模型判断“这条自然语言指令是否属于公众号采集能力域、应该走哪条工具链、计划步骤如何表述”，但真正执行仍然落到既有的账号匹配、历史页抓取、桌面采集回退、清洗、入库、标注等确定性工具上。

当前能力边界只覆盖：

- 匹配或搜索本地公众号账号
- 抓取公众号详情页或历史页
- 决定是否需要桌面微信辅助采集
- 清洗已抓取的公众号文章
- 将清洗结果入库用于检索
- 进入或继续公众号标注工作流

超出这个边界的通用闲聊、通用代码生成、系统管理、主 RAG 问答等请求，当前都会被判定为 unsupported，而不是强行执行。

## 当前前后端落点

当前公众号 Agent 的主要实现落点如下：

- 后端主路由：`rag_qa/web/backend/routers/wechat_annotator.py`
- 轻量标注入口：`rag_qa/web/backend/wechat_annotator_main.py`
- 前端页面：`rag_qa/web/frontend/src/views/WechatAnnotatorView.vue`
- 前端 API 封装：`rag_qa/web/frontend/src/api/index.js`

其中：

- 后端负责自然语言解析、LLM 规划、观察、推理、抓取、桌面回退、清洗、入库、SSE 输出。
- 前端负责大脑状态展示、结构化计划展示、短期记忆展示、锁定/清空控制、阶段日志和完成反馈。

## 当前 SSE 事件契约

`POST /api/wechat-annotator/agent/stream` 是当前推荐的流式入口，`POST /api/wechat-annotator/agent/command/stream` 作为兼容别名继续保留。两者当前都使用 SSE 推送统一事件流，事件类型固定为：

- `loading`
- `parsed`
- `step_start`
- `step_done`
- `done`
- `error`

其中最关键的是：

- `parsed`：返回 `brain_source`、`intent_label`、`capability_supported`、`capability_message`、`plan_outline` 和标准化后的 `session_memory`
- `step_done`：返回每个阶段的真实执行结果，前端阶段日志应以这里为准
- `done`：返回统一 `data` 结构，包含 `parsed`、`steps`、`annotation_entry`、`refreshed`

当前页面上的顶部 Agent 完成结果条和下方阶段日志，应该共同引用 `done.data.steps` 这份事实，而不是各自再推导一套原因。

## 可见大脑状态

为了让这个系统更像 Agent，而不是黑箱脚本，前端现在已经把下列内容直接显示给用户：

- 大脑来源：当前是 LLM 规划还是规则回退
- 意图判断：本轮更像 collect、clean、ingest、desktop_collect、review 等哪一类动作
- 能力边界说明：若 unsupported，会明确说明为什么当前不执行
- 结构化执行计划：`plan_outline` / `plan_steps`

这部分的目标不是装饰，而是把“它为什么这么做”从内部状态变成用户可见状态。

## 短期记忆与账号锁定

当前 Agent 已接入浏览器会话级短期记忆，并支持用户可控。

当前会记录的典型上下文包括：

- `recent_account_id`
- `recent_display_name`
- `recent_history_url`
- `recent_urls`
- `recent_article_title`
- `recent_failure_reason`
- `recent_decision`
- `pinned_account_id`
- `pinned_display_name`
- `account_locked`

当前前端支持：

- 锁定当前账号上下文
- 解除账号锁定
- 清空短期记忆

锁定后，用户再说“继续刚才那个账号”“那篇文章”“上次那个公众号”这类省略表达时，解析阶段会优先落到被锁定账号，而不是重新猜一个账号。

页面上也不再只用文字前缀提示锁定态，而是会显示显式“账号已锁定”徽标和高亮 banner。

## 本地账号沉淀与页面行为

当前 Agent 相关页面不只是“执行一次抓取”，还会持续沉淀本地公众号账号上下文：

- 抓取过的公众号会沉淀到本地账号总览
- 详情页链接会尽量推导出历史页链接
- 历史页、本地账号搜索和桌面采集 profile 会共同参与后续补爬

这意味着当前页面既是一个执行面板，也是一个持续积累公众号资产的工作台。

## 完成反馈的当前口径

此前一个典型问题是：

- 顶部 Agent 完成 banner 会单独猜测“为什么没新增文章”
- 下方阶段日志展示的却是另一套真实执行事实

这会导致用户看到“上面说时间窗过滤”，下面却写着“检查了 1 条链接、清洗 0 篇、入库 0 块”，观感上像是两个不同系统在说话。

当前前端已经修正为：

- 顶部完成反馈先展示和阶段日志一致的执行摘要
- 若本轮零新增，再把“原因判断”作为附加说明拼接在后面

也就是说，完成反馈现在是“先说实际发生了什么，再说为什么”，而不是只给一个猜测原因。

## 当前开发验证入口

和公众号 Agent 直接相关的开发验证入口，当前建议优先使用：

- VS Code 任务 `Frontend: Run Vite`
- VS Code 任务 `Backend: Run Uvicorn (.venv)`
- VS Code 任务 `Backend: Run Uvicorn Stable (.venv)`
- VS Code 任务 `Project: Run stable local app`
- VS Code 任务 `Project: Verify listening ports`

补充说明：

- `Frontend: Run Vite` 当前已经修正为从 `rag_qa/web/frontend` 作为 cwd 启动。
- `Backend: Run Uvicorn (.venv)` 当前只监视 `rag_qa/web/backend`、`rag_qa/core`、`rag_qa/base`，并默认开启 `EDURAG_DEV_FAST_STARTUP=1`。
- `Backend: Run Uvicorn Stable (.venv)` 适合验证登录、账号总览、SSE 事件流等稳定性问题。
- 若 5173 被占用，Vite 会自动顺延到 5174、5175 等可用端口，这属于正常行为。
- `Project: Verify listening ports` 当前已修正为可直接输出真实监听端口与进程名，适合联调前快速确认本地端口状态。

兼容性修复说明：

- 旧流式入口 `/api/wechat-annotator/agent/command/stream` 之前在清洗步骤里可能触发 `free variable 'account_id' referenced before assignment in enclosing scope`。
- 当前已通过显式区分初始账号与运行中账号状态修复，旧入口和新入口都会复用同一套修正后的执行链路。

## Scope

This agent is designed for self-owned WeChat official accounts and local execution.
It collects article data into markdown/json for your current RAG pipeline.

## Supported Fields

- title
- published_at
- author
- body_text
- image OCR text
- video metadata
- tags
- source link
- engagement metrics (read/like/share/comment count when publicly exposed)
- comments placeholder (reserved for authorized source)

## Hybrid Pipeline (Recommended)

This project supports a practical hybrid pipeline:

- OCR: local first (`PaddleOCR` preferred, `RapidOCR` fallback)
- Image understanding: rules + OCR first, then optional API fallback for difficult images
- Text structure extraction: optional API-based JSON extraction
- Video indexing: metadata + manual one-line annotation template

Generated artifacts per article:

- `docs/<article_id>.md`: article body and OCR text
- `docs/<article_id>.html`: visual preview
- `docs/<article_id>.images.md`: indexable image list
- `docs/<article_id>.video_notes.md`: manual video notes template
- `meta/<article_id>.json`: full metadata
- `meta/<article_id>.image_index.json`: image index with `image_id/indexable/decorative_candidate`

## Do I Need Manual Copy For Every Article?

No. You can provide either:

- `article_urls`: direct article links (manual list)
- `history_urls`: account history page links (auto extraction)

If `history_urls` is provided, the collector will automatically extract article links from the history page and then crawl each article.
If you accidentally place a history-page link in `article_urls`, the collector will now detect it and expand it the same way.

## Quick Start

1. Edit source config:

- file: `samples/wechat_accounts.sample.json`
- copy this file to your own local file (recommended), for example: `data/wechat_collector/accounts.json`
- fill account_id, frequency_days, and one of `article_urls` / `history_urls`

Example account config:

```json
{
	"account_id": "my_wechat_account",
	"display_name": "My WeChat Official Account",
	"enabled": true,
	"frequency_days": 30,
	"window_days": 365,
	"max_links_from_history": 200,
	"history_urls": [
		"https://mp.weixin.qq.com/mp/profile_ext?action=home&__biz=替换成你的biz"
	],
	"article_urls": []
}
```

2. Configure `config.ini`:

- section: `[wechat_collector]`
- `source_file` points to your local accounts json
- default monthly crawl: `default_frequency_days = 30`

3. Run collector:

```powershell
cd rag_qa
python run_wechat_collector.py --source-file data/wechat_collector/accounts.json
```

4. Optional vector ingestion:

```powershell
cd rag_qa
python run_wechat_collector.py --source-file data/wechat_collector/accounts.json --ingest
```

5. Generate and inspect effect report (enabled by default):

```powershell
cd rag_qa
python run_wechat_collector.py --source-file data/wechat_collector/accounts.json --report-dir data/wechat_collector/reports
```

## History Page Login Session

If a history page returns a verification page, export the logged-in browser cookie and convert it into `cookies.jar` before crawling.

Fast path:

```powershell
cd rag_qa
python convert_wechat_cookie_to_jar.py
```

The script will try the clipboard first. If nothing is found, paste the `Cookie` header string from DevTools and press Enter.

Output:

- `cookies.jar` in the project root by default
- reusable by `run_wechat_collector.py` when `history_urls` is present

The run result json will include:

- `report_json`: detailed machine-readable report path
- `report_md`: human-readable report path

Report contains:

- account-level crawl stats
- failed URL and error reason
- time-window filtered counts
- body pass rate and OCR pass rate
- sampled article preview (title/url/body length/image/video/ocr score)

## Per-Account Frequency

Each account supports custom `frequency_days` in source json.
Examples:

- monthly: `30`
- weekly: `7`
- daily: `1`

This is per-account and can be mixed in the same source file.

## Output Layout

Default output path: `data/wechat_collector/wechat_data`

- account-level docs: `data/wechat_collector/wechat_data/<account_id>/docs/*.md`
- account-level metadata: `data/wechat_collector/wechat_data/<account_id>/meta/*.json`
- downloaded images: `data/wechat_collector/wechat_data/<account_id>/images/`
- run state: `data/wechat_collector/collector_state.json`

## Cleaning Agent (Post-crawl)

After crawling, run the cleaning agent to normalize text and build media metadata docs for retrieval.

```powershell
cd rag_qa
python run_wechat_cleaner.py --account-id my_wechat_account
```

Optional ingestion to vector store (reuses existing RAG chunking + indexing pipeline):

```powershell
cd rag_qa
python run_wechat_cleaner.py --account-id my_wechat_account --ingest
```

Generated files per article:

- `docs/<article_id>.cleaned.md`: cleaned text for chunking/retrieval
- `docs/<article_id>.media_index.md`: image/video metadata, tags, notes for retrieval

## Notes

- Comments details and some engagement metrics are often not fully exposed on public article pages.
- The agent stores placeholders for those fields and keeps schema stable.
- OCR quality is highly related to image quality and text density.

## Key Config Options

Under `[wechat_collector]`:

- `ocr_engine = auto|paddle|rapid`
- `paddle_ocr_enable = true|false`
- `enable_image_api_fallback = true|false`
- `image_api_model = qwen-vl-max` (or your compatible VLM)
- `text_struct_enable = true|false`
- `text_struct_model = qwen-plus`
- `video_manual_template_enable = true|false`
