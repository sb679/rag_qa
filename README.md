[README.md](https://github.com/user-attachments/files/26708484/README.md)
# EduRAG 采矿安全智能问答系统

一个基于 RAG（检索增强生成）技术的采矿安全领域智能问答系统，集成了权限控制、用户反馈、知识库版本管理等工业级功能。

<!-- AI-ONBOARDING:START -->
## 🤖 新窗口 AI 启动指令（复制下面整段给新会话即可）

> 请按顺序读完 PROJECT_CHARTER_AND_SCOPE.md、MILESTONES_AND_ITERATION_TRACKER.md、README.md、TECHNICAL_DOCUMENTATION.md、rag_qa/README.md、rag_qa/项目使用指南.md、TECHNICAL_DECISION_RECORD.md、DEVELOPMENT_TEST_RELEASE_BASELINE.md、rag_qa/文档索引.md，然后用不超过 200 字回报：项目目标、当前迭代阶段、技术栈与启动方式、最近风险/缺口，确认后再等我下一步指令，不要先动代码。

需要更结构化汇报时，使用强化版：要求 AI 读完后按 A 目标边界 / B 迭代风险 / C 技术栈与版本基线 / D 启动方式与端口 / E 发布前检查（是否跑 `Release: Preflight Check`） / F 待确认问题 六段输出，再开始任何修改。
<!-- AI-ONBOARDING:END -->

## 技术文档导航

当前仓库已经有技术文档，但入口分散在根目录和 `rag_qa/` 子项目下。建议按下面顺序阅读：

### 项目治理与执行文档

- [PROJECT_CHARTER_AND_SCOPE.md](PROJECT_CHARTER_AND_SCOPE.md)：项目目标、范围边界、非目标与成功标准
- [MILESTONES_AND_ITERATION_TRACKER.md](MILESTONES_AND_ITERATION_TRACKER.md)：里程碑、迭代进展、当前阻塞与下一步
- [TECHNICAL_DECISION_RECORD.md](TECHNICAL_DECISION_RECORD.md)：关键技术取舍与变更原因
- [DEVELOPMENT_TEST_RELEASE_BASELINE.md](DEVELOPMENT_TEST_RELEASE_BASELINE.md)：开发、测试、发布的最低统一口径

### 工程与技术文档

- [rag_qa/README.md](rag_qa/README.md)：应用层快速开始、环境变量、API 总览
- [rag_qa/项目使用指南.md](rag_qa/%E9%A1%B9%E7%9B%AE%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97.md)：当前工程版运行、联调、配置与排障手册
- [rag_qa/TECHNICAL_HANDBOOK.md](rag_qa/TECHNICAL_HANDBOOK.md)：系统架构、主入口、核心数据流、接手建议
- [rag_qa/SYSTEM_ARCHITECTURE.md](rag_qa/SYSTEM_ARCHITECTURE.md)：面向交接、汇报和答辩的系统架构说明
- [rag_qa/PROJECT_STRUCTURE.md](rag_qa/PROJECT_STRUCTURE.md)：当前真实目录结构与目录职责
- [rag_qa/文档索引.md](rag_qa/%E6%96%87%E6%A1%A3%E7%B4%A2%E5%BC%95.md)：按场景查文档的导航页

文档边界说明：

- 根目录 README 属于“工作区入口层”，负责整个工作区的启动、编排、端口和最小导航。
- `PROJECT_CHARTER_AND_SCOPE.md`、`MILESTONES_AND_ITERATION_TRACKER.md`、`TECHNICAL_DECISION_RECORD.md`、`DEVELOPMENT_TEST_RELEASE_BASELINE.md` 属于“工作区治理与执行文档”，负责范围、计划、决策和最低交付口径。
- `TECHNICAL_DOCUMENTATION.md` 属于“稳定事实基线层”，负责沉淀数据存储位置、服务职责、脚本边界、任务用途、配置映射和运行判定。
- `rag_qa/项目使用指南.md` 属于“运行与排障手册层”，负责当前工程版启动、联调、配置与日常操作。
- `rag_qa/TECHNICAL_HANDBOOK.md` 与 `rag_qa/SYSTEM_ARCHITECTURE.md` 属于“架构与接手层”，分别面向快速接手和汇报/交接说明。
- 目录事实、主入口和脚本边界以 `rag_qa/PROJECT_STRUCTURE.md` 为准；按场景找文档以 `rag_qa/文档索引.md` 为准。

## 🎯 核心功能

### 1. RAG 问答引擎
- 基于向量检索的语义搜索
- 多层级文档处理（PDF、PPT、Word、图片）
- 智能文本分割与段落级引用
- 支持复杂查询分类与策略选择

### 2. 工业级功能（毕业设计新增）
- **权限控制**：主管/普通用户多角色访问控制
- **用户反馈闭环**：点赞、点踩、纠错、反馈统计
- **知识库版本管理**：版本创建、发布、回滚、历史追溯
- **来源引用**：精确到段落和页码的引用追踪

### 3. Web 应用
- FastAPI 后端 REST API
- Vue 3 前端交互界面
- 会话管理与历史记录
- 实时反馈与统计展示

## 🧭 当前前端交互口径（阶段性收口）

- 关键结果优先显示在页面内状态区，不再只依赖瞬时 toast。当前已覆盖登录失败、聊天发送失败、会话创建/删除、反馈提交/撤销、知识文件入库、测试集生成与追加等高价值操作。
- 后台页面已形成统一加载治理：Dashboard、Knowledge、Config、Employee 页面具备 `loadError + retry + skeleton`，关键操作优先通过页面内结果条反馈。
- ChatView 已形成三层状态口径：工作台级 `workspaceActionFeedback`、输入区 `composerNotice`、消息级流式中断标记，避免把所有问题都压缩成同一种弹窗提示。
- WechatAnnotatorView 已对本地账号匹配、桌面 profile / 桌面采集、Agent 执行三组高频动作完成页面内反馈治理；模板已无入口的旧抓取分支已同步清理，代码与实际界面重新对齐。
- 公众号 Agent 当前已把大脑状态、结构化执行计划、短期记忆、账号锁定状态做成页面可见区域；顶部完成反馈也已和阶段日志共用同一份执行摘要事实源，不再出现“上面一句话”和“下面阶段明细”相互不符的情况。
- 公众号多 Agent 工作台代码仍保留在仓库中，但前端入口默认隐藏；只有显式设置环境变量 `VITE_ENABLE_WECHAT_ANNOTATOR=true` 时才会在页面中显示并注册该入口，避免日常启动时加载无关能力。
- 前端工程侧已接入路由懒加载、Element Plus 按需导入与基础 PWA 安装能力，当前更关注真实交互体验的一致性，而不是继续堆叠首屏优化口号。

## 📋 项目结构

当前工作区分为“工作区根目录编排层”和“`rag_qa/` 应用主体层”两部分。完整目录说明见 `rag_qa/PROJECT_STRUCTURE.md`，这里仅保留稳定摘要：

```text
Graduation-Project/
├── README.md
├── start_edurag.bat / start_edurag.ps1
├── docker-compose.yml
├── docker-compose.monitoring.yml
├── docker-compose.prod.yml
├── ops/                     # Prometheus / Grafana 配置
├── scripts/                 # 仓库级环境初始化与自检脚本
├── data/                    # 工作区级数据目录
├── minio-data/              # MinIO 持久化目录
└── rag_qa/                  # 应用主体
	├── web/backend/         # FastAPI 后端
	├── web/frontend/        # Vue 3 + Vite 前端
	├── core/                # RAG / 检索 / 对话核心
	├── edu_document_loaders/# 文档加载与 OCR
	├── edu_text_spliter/    # 文本切分
	├── tests/               # 当前保留的 unittest 测试
	├── models/              # Embedding / reranker 模型目录
	├── rag_main.py          # CLI 主入口
	├── run_wechat_collector.py / run_wechat_cleaner.py / sync_image_annotations.py
	├── build_* / train_* / evaluate_* / analyze_*  # 实验与批处理脚本
	├── ragas_paper_bundle/  # 论文/展示用数据与图表产物
	└── 文档与专题说明
```

说明：

- 当前仓库没有独立的 `rag_qa/scripts/` 分类目录，历史脚本直接分布在 `rag_qa/` 根下。
- `ragas_paper_bundle/` 保存的是自定义实验输出和 RAGAS 格式导出数据，不等于官方 `ragas` 评估运行器。

## 🚀 快速开始

### 工程版启动（推荐）

这是当前最稳妥的启动方式：本地保留后端和前端，MinIO、etcd、Milvus 由 Docker Compose 管理。

1. 确保已安装并启动 Docker Desktop。
2. 在项目根目录双击 `start_edurag.bat`。
3. 脚本会自动先启动 `minio`、`etcd`、`milvus`，然后再启动后端和前端。
4. 启动完成后，浏览器会自动打开前端页面。

默认优先端口：

- 后端：`8000`
- 前端：`5173`
- MinIO：宿主机 `19000/19001`，容器内 `9000/9001`
- Milvus：宿主机 `19530`，容器内 `19530`

如果这些端口被其他项目占用，启动器会继续尝试一组随机高位候选端口，并把实际选中的端口写入 `rag_qa/logs/launcher/launcher-latest.log`。具体候选范围：

| 服务 | 优先端口 | 近邻候选 | 随机回退区间 |
| --- | --- | --- | --- |
| Backend | 8000 | 8001/8002/8003 | 18000–18999（随机 10 个） |
| Frontend | 5173 | 5174–5185 | 24000–24999（随机 10 个） |
| MinIO API | 19000 | — | 29000–29149（随机 12 个） |
| MinIO Console | 19001 | — | 29150–29299（随机 12 个） |
| Milvus | 19530 | — | 29530–29699（随机 12 个） |

> 注意：Milvus 端口被自动改到高位时，本项目会拉起一个**全新的空 Milvus 容器**，不会自动连接占用 19530 的其它实例。如果 19530 上正运行着一个你想复用的外部 Milvus（例如其它项目的 `milvus-standalone`），请改用下面的「复用外部 Milvus」模式。

#### 复用外部 Milvus（可选）

当机器上已有别的项目跑着 Milvus 并且**含有本项目需要的 `itcast/edurag_final` 数据**时，可以让本启动器跳过 Milvus/etcd 的 docker compose 步骤，直接连接外部实例。在 `.env` 中加上：

```env
EDURAG_MILVUS_EXTERNAL_PORT=19530
```

启动器会：

- 跳过 `docker compose up -d milvus etcd`，仅启动 MinIO
- 让 backend 连到 `127.0.0.1:19530` 上的外部 Milvus
- 启动前预检：若该端口没有任何服务监听则立即报错并提示先启动外部 Milvus

想恢复「由本项目自管 Milvus」时，把这一行注释掉即可。

开发联调约定：

- 后端优先占用 `8000`，被占用时会先尝试 `8001` 等近邻端口，再回退到随机高位端口
- 前端开发代理默认指向 `http://127.0.0.1:8000`
- 如果后端没有落在 `8000`，启动器会自动注入正确的 `VITE_API_PROXY_TARGET`
- 登录返回 `401` 时通常是账号或密码错误，返回 `404` 时通常是代理或后端未连通

手动联调时建议按这个顺序：

1. 先启动后端，优先使用 `start_edurag.bat` 或 `start_edurag.ps1`
2. 再启动前端，或直接由启动器接管前端启动
3. 如果你手动运行前端而后端不在 `8000`，先显式设置 `VITE_API_PROXY_TARGET`

```powershell
$env:VITE_API_PROXY_TARGET = 'http://127.0.0.1:8001'
cd rag_qa\web\frontend
npm run dev
```

### 当前支持的运行模式

| 模式 | 入口 | 主要依赖 | 适用场景 |
| --- | --- | --- | --- |
| 工程联调（推荐） | `start_edurag.bat` / `start_edurag.ps1` | 本地 backend/frontend + Compose 管理的 MinIO/etcd/Milvus | 日常开发、联调、演示 |
| 手动 Web 联调 | `uvicorn main:app` + `npm run dev` | 同上 | 精细调试前后端 |
| 独立公众号标注 | `web/backend/wechat_annotator_main.py` | 前端 + 标注路由；不依赖主 RAG 问答栈 | 只做公众号图片标注 |
| CLI / 实验脚本 | `rag_main.py`、`run_wechat_*`、`build_*`、`train_*`、`evaluate_*` | 视脚本而定，常见为 Milvus、模型目录、MinIO | 数据构建、实验、批处理 |
| 容器化验证 | `docker compose up -d minio etcd milvus backend frontend` | Docker Compose | 一体化容器验证 |

### 环境要求
- Python 3.8+
- Node.js 18.x LTS
- npm 9+
- Docker Desktop 4.x+（需可用 `docker compose` v2）
- CUDA 11.0+ (可选，用于 GPU 加速)

版本基线说明：

- Node.js 18.x 与当前前端容器镜像 [rag_qa/web/frontend/Dockerfile](rag_qa/web/frontend/Dockerfile#L1) 保持一致。
- npm 9+ 与当前 [rag_qa/web/frontend/package-lock.json](rag_qa/web/frontend/package-lock.json#L1) 的 `lockfileVersion: 3` 保持一致。
- Docker 口径以 `docker compose` v2 为准，不再以旧版 `docker-compose` 独立命令作为默认要求。

### 安装依赖

```bash
# 创建虚拟环境
cd rag_qa
python -m venv .venv
.venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 环境变量（推荐）

```bash
cp .env.example .env
```

在 `.env` 中填写真实密钥。服务启动时会优先读取 `MINING_QA_*` 环境变量，同时兼容历史 `EDURAG_*` 环境变量。

开发部署安全建议（已支持）：
- `docker-compose.yml` 不再写死 `1234/minioadmin` 这类明文默认凭据。
- 通过 `.env` 注入如下变量：
	- `EDURAG_MINIO_ROOT_USER`
	- `EDURAG_MINIO_ROOT_PASSWORD`
	- `EDURAG_MILVUS_HOST_PORT`
- 示例值见项目根目录 `.env.example`。

可观测性（轻量）建议：
- 默认启用结构化 JSON 日志（`EDURAG_LOG_STRUCTURED=true`）。
- 支持错误阈值告警：在时间窗内达到阈值时输出 `error_alert_triggered` 事件。
	- `EDURAG_LOG_ALERT_ERROR_THRESHOLD`（默认 20）
	- `EDURAG_LOG_ALERT_WINDOW_SEC`（默认 300）

Windows 工程化密钥初始化（推荐）：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
& .\scripts\setup_edurag_env.ps1 -PersistUser
```

说明：
- 脚本会将可用的 `DASHSCOPE_API_KEY` 迁移/对齐到 `MINING_QA_DASHSCOPE_API_KEY`，并同步兼容历史 `EDURAG_DASHSCOPE_API_KEY`。
- `config.ini` 保持 `demo-key-change-me` 占位，不在仓库落地真实密钥。
- `start_edurag.ps1` 已集成该脚本，启动时会自动校验并加载。

### 配置

```bash
# 复制配置模板
cp config.ini.template config.ini

# 编辑 config.ini，填入必要的配置
# - 向量数据库路径
# - 模型路径
# - API 密钥等
```

### 运行

**后端 API 服务：**
```bash
cd rag_qa/web/backend
python -m uvicorn main:app --reload --reload-dir ../../rag_qa/web/backend --reload-dir ../../rag_qa/core --reload-dir ../../rag_qa/base --host 0.0.0.0 --port 8000
```

开发联调如果优先追求稳定，而不是热重载，建议直接使用不带 `--reload` 的稳定模式：

```bash
cd rag_qa/web/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

**前端开发服务：**
```bash
cd rag_qa/web/frontend
npm install
npm run dev
```

**主程序（命令行交互）：**
```bash
python rag_main.py
```

## 📚 API 文档

启动后端服务后，访问 `http://localhost:8000/docs` 查看完整的 Swagger API 文档。

### 核心接口

**认证相关：**
- `POST /api/auth/login` - 用户登录
- `POST /api/auth/logout` - 用户登出
- `GET /api/auth/verify` - 验证 Token

**对话相关：**
- `POST /api/chat/ask` - 提交问题
- `GET /api/chat/history/{session_id}` - 获取对话历史

**反馈相关：**
- `POST /api/feedback/submit` - 提交反馈
- `GET /api/feedback/session/{session_id}` - 获取会话反馈
- `GET /api/feedback/stats` - 获取反馈统计

**版本管理：**
- `GET /api/kb-version/list` - 获取版本列表
- `POST /api/kb-version/create` - 创建新版本
- `POST /api/kb-version/publish` - 发布版本
- `POST /api/kb-version/rollback` - 回滚版本

## 🔐 权限控制

系统支持两种用户角色：

| 角色 | 权限 | 用途 |
|------|------|------|
| 普通用户 | 提问、反馈、查看版本 | 日常使用 |
| 主管 | 所有权限 + 版本管理、反馈统计、审计日志 | 系统管理 |

**演示账号：**
- 主管工号：`9526` / `9527` / `9528`
- 默认演示密码：由 `EDURAG_DEFAULT_SUPERVISOR_PASSWORD` 控制（默认仅演示用）

## 📊 工业化功能说明

### 1. 权限控制与认证
- JWT Token 认证
- 基于角色的访问控制（RBAC）
- 会话管理与超时控制

### 2. 用户反馈闭环
- 支持多种反馈类型：点赞、点踩、部分正确、纠错
- 反馈数据持久化存储
- 主管可查看反馈统计与趋势

### 3. 知识库版本管理
- 版本创建与描述
- 版本发布与激活
- 版本回滚与历史追溯
- 支持多版本并行管理

### 4. 来源引用追踪
- 精确到段落级别的引用
- 支持页码标注
- 引用来源可追溯

详见 `INDUSTRIAL_FEATURES_PLAN.md`

## 📦 完整项目下载

由于项目包含大量模型文件和数据，Git 仓库只保留代码、配置和启动脚本；大模型和大数据建议按需下载或自行补齐。

**网盘链接：** [通过网盘分享的文件：rag-qa](https://pan.baidu.com/s/1T7_l6S4sSv8TMCutPq1eXQ?pwd=7a7b)

**包含内容：**
- 完整源代码
- 预训练模型（BERT、BGE 等）
- 示例数据集
- 配置文件

**下载后操作：**
1. 解压项目
2. 按上述"安装依赖"和"配置"步骤操作
3. 运行后端和前端服务

## 💾 数据存储说明

- 上传 PDF 等原始知识文件默认存储在 MinIO 的 `edurag-knowledge/<source>/<file_id>__<original_name>`；如果切换为 local 存储，则落在 `rag_qa/user_data/knowledge_files/<source>/`。
- 微信抓取产物落在 `data/wechat_collector/wechat_data`，其中清洗文档、媒体索引和图片标注都按公众号账号与文章 ID 组织。
- 分块后的父块、子块以及 `file_id/file_name/file_path/source/timestamp` 元数据写入 Milvus 集合 `edurag_final`。
- 如果更换电脑，需要迁移 Docker volume、重新配置环境变量，或者重新上传文档并重建索引。

## 🔒 生产 Secrets 与 Compose 覆盖

开发环境的 `docker-compose.yml` 已改为从环境变量读取关键凭据，不再硬编码默认密码。

生产建议使用覆盖文件：

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

`docker-compose.prod.yml` 会要求必须提供：

- `EDURAG_MINIO_ROOT_USER`
- `EDURAG_MINIO_ROOT_PASSWORD`

生产模式下会关闭 MinIO 与 Milvus 对宿主机的端口暴露，降低暴露面。

## 📈 Prometheus + Grafana 监控

后端新增 `/metrics` 指标接口，包含：

- `edurag_http_requests_total`
- `edurag_http_request_duration_ms`

启动监控栈：

```bash
docker compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d prometheus grafana
```

访问地址：

- Prometheus: `http://127.0.0.1:19090`
- Grafana: `http://127.0.0.1:13000`

Grafana 默认会自动加载 `ops/grafana/dashboards/edurag-overview.json`。

## 🧰 VS Code 推荐任务

- `Env: Self-check (.venv)`：检查虚拟环境与关键依赖
- `Backend: Run Uvicorn (.venv)`：以收敛版热重载启动后端
- `Backend: Run Uvicorn Stable (.venv)`：以稳定模式启动后端，不启用热重载
- `Frontend: Run Vite`：启动前端开发服务器
- `Project: Run stable local app`：并行拉起稳定版后端和前端，适合本地联调
- `Repo: Self-check`：执行仓库级自检
- `Release: Preflight Check`：发布或阶段提交前串联环境、仓库、文档与关键运行文件检查

开发服务稳定性补充说明：

- 当前后端热重载只监视 `rag_qa/web/backend`、`rag_qa/core`、`rag_qa/base`，不再扫描整个仓库，避免大型数据目录触发 `MemoryError`。
- VS Code 开发任务默认注入 `EDURAG_DEV_FAST_STARTUP=1`，启动时跳过 RAG 预热，优先保证服务先起来。
- 主要 RAG 路由已改为按需加载 `rag_service`，减少每次 reload 时的重型初始化开销。

## 🧪 测试与自检

```bash
# 进入应用目录
cd rag_qa

# 当前保留的基础 smoke test
.venv\Scripts\python.exe -m unittest tests.test_smoke

# 检索策略选择器回归测试
.venv\Scripts\python.exe -m unittest tests.test_strategy_selector
```

说明：

- `rag_qa/tests/` 是当前维护中的 unittest 测试目录。
- 直接放在 `rag_qa/` 根下的 `test_*.py` 多数是历史验证脚本或临时实验脚本，不是统一测试套件。
- 仓库级环境自检优先使用 VS Code 任务 `Env: Self-check (.venv)` 和 `Repo: Self-check`。
- 如果当前改动已经接近阶段提交、演示或发布，额外执行一次 `Release: Preflight Check`，再补人工验证前端页面、登录流程和演示链路。

演示前最低动作：

- 先明确本次演示走主 Web 问答、知识库链路还是公众号标注链路，不临场临时切换主路线。
- 至少提前完整跑通一次本次演示要走的最小路径，例如“登录 -> 提问 -> 返回回答”或“进入标注页 -> 加载样本 -> 提交结果”。
- 若演示依赖检索或知识库统计，先确认 Milvus 可用；若演示依赖文件链路，先确认 MinIO 可用。
- 提前准备一条降级演示路径，避免现场把时间耗在排大故障上。
- 详细清单以 [DEVELOPMENT_TEST_RELEASE_BASELINE.md](DEVELOPMENT_TEST_RELEASE_BASELINE.md#L72) 为准。

## 📝 文档

- `INDUSTRIAL_FEATURES_PLAN.md` - 工业化功能详细方案
- `PROJECT_STRUCTURE.md` - 项目结构与整理说明
- `MODELS_README.md` - 模型文件说明
- `TECHNICAL_HANDBOOK.md` - 入口、主链路与专题边界总览
- `SYSTEM_ARCHITECTURE.md` - 架构、运行拓扑和部署边界
- `文档索引.md` - 按场景查阅文档的导航页

## 🎓 毕业设计相关

本项目是一个毕业设计项目，展示了如何将学术 RAG 系统向工业级应用演进。

**主要创新点：**
1. 多层级文档处理与智能分割
2. 工业级权限与版本管理
3. 完整的用户反馈闭环
4. 精确的来源引用追踪

**答辩演示重点：**
- 系统架构与核心算法
- 工业化功能的实现
- 用户反馈与迭代改进
- 性能指标与优化方向

## 📄 许可证

MIT License

## 👤 作者

[SB679]

## 📧 联系方式

如有问题或建议，欢迎联系：[1427458313lyy@gmail.com]

---

**最后更新：** 2026-04-14
