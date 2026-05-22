# EduRAG 采矿安全智能问答系统

一个基于 RAG（检索增强生成）技术的采矿安全领域智能问答系统，集成了权限控制、用户反馈、知识库版本管理等工业级功能。

## 技术文档导航

如果你是第一次进入 `rag_qa/`，建议先按下面顺序看文档：

- [../PROJECT_CHARTER_AND_SCOPE.md](../PROJECT_CHARTER_AND_SCOPE.md)：项目目标、范围边界、非目标与成功标准
- [../MILESTONES_AND_ITERATION_TRACKER.md](../MILESTONES_AND_ITERATION_TRACKER.md)：当前迭代、阶段进展、风险与下一步
- [../TECHNICAL_DECISION_RECORD.md](../TECHNICAL_DECISION_RECORD.md)：关键技术取舍与变更原因
- [../DEVELOPMENT_TEST_RELEASE_BASELINE.md](../DEVELOPMENT_TEST_RELEASE_BASELINE.md)：开发、测试、发布与跨窗口文档同步规则
- [../README.md](../README.md)：工作区级启动方式、Docker Compose、Windows 启动器
- [../TECHNICAL_DOCUMENTATION.md](../TECHNICAL_DOCUMENTATION.md)：稳定工程事实基线，如数据落盘、脚本职责、配置映射、运行判定
- [项目使用指南.md](%E9%A1%B9%E7%9B%AE%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97.md)：当前工程版运行、联调、配置与排障手册
- [TECHNICAL_HANDBOOK.md](TECHNICAL_HANDBOOK.md)：系统架构、后端路由、前端核心页面、阅读顺序
- [SYSTEM_ARCHITECTURE.md](SYSTEM_ARCHITECTURE.md)：面向交接、汇报和答辩的系统架构说明
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md)：当前真实目录结构与各目录职责
- [文档索引.md](%E6%96%87%E6%A1%A3%E7%B4%A2%E5%BC%95.md)：所有技术文档的导航页

文档边界说明：

- 本文件属于“应用入口层”，只负责 `rag_qa/` 应用本体的快速开始、入口速览和最少必要说明。
- 工作区级启动、端口、编排和根目录治理入口，以 [../README.md](../README.md) 为准。
- 稳定工程事实，如数据落盘位置、服务职责、脚本边界、任务用途、配置映射、运行判定，以 [../TECHNICAL_DOCUMENTATION.md](../TECHNICAL_DOCUMENTATION.md) 为准。
- 项目范围、里程碑、技术决策、开发/测试/发布口径，以根目录 4 份治理文档为准。
- `项目使用指南.md` 是当前工程版运行与联调手册。
- `TECHNICAL_HANDBOOK.md` 用于快速建立架构共识。
- `SYSTEM_ARCHITECTURE.md` 适合交接、答辩和高层说明。
- 目录事实和脚本边界以 `PROJECT_STRUCTURE.md` 为准，本文件只维护应用层稳定摘要。

### 本文件应回答的问题

1. 进入 `rag_qa/` 后，应用主体怎么理解。
2. 当前应用层有哪些主要入口。
3. 最小开发与联调路径是什么。

### 本文件不负责维护的内容

1. 版本迭代状态与里程碑。
2. 技术决策原因与变更记录。
3. 运行判定、数据落盘、脚本职责等稳定工程事实明细。
4. 全量排障手册。

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

## 当前前端交互治理摘要

- 登录、聊天、知识库与员工管理等主页面已从“toast 兜底”逐步收敛为“页面内状态优先”，关键失败和关键结果会优先保留在当前视图内，便于回看与重试。
- ChatView 当前采用分层反馈：工作台操作结果走 `workspaceActionFeedback`，输入区发送失败走 `composerNotice`，流式回答中断保留在消息级状态里，避免同一问题被多处重复提示。
- WechatAnnotatorView 当前把高频动作分为本地账号匹配、桌面采集、Agent 执行三组页面内反馈；模板已无入口的旧抓取分支已清理，当前界面事实与代码入口保持一致。
- 前端工程侧已稳定接入路由懒加载、Element Plus 按需导入与基础 PWA 能力；更细的运行时口径以 [../TECHNICAL_DOCUMENTATION.md](../TECHNICAL_DOCUMENTATION.md) 的“前端运行时口径更新”章节为准。

## 📋 项目结构

完整目录说明见 `PROJECT_STRUCTURE.md`，这里保留应用主体摘要：

```text
rag_qa/
├── base/ / core/ / edu_document_loaders/ / edu_text_spliter/
├── web/backend/                       # FastAPI 后端入口与路由
├── web/frontend/                      # Vue 3 + Vite 前端
├── tests/                             # 当前维护中的 unittest 测试
├── models/                            # Embedding / reranker 模型目录
├── macbert_query_classifier_v2/       # 当前默认查询分类模型目录
├── bert_query_classifier_new/         # 旧版查询分类模型目录（回退保留）
├── bert_strategy_classifier*/         # 检索策略分类模型目录
├── nlp_bert_document-segmentation_chinese-base/
├── conversations/ / feedback_data/ / knowledge_versions/ / logs/
├── ragas_paper_bundle/ / rag_assesment/
├── rag_main.py                        # CLI 主入口
├── run_wechat_collector.py
├── run_wechat_cleaner.py
├── sync_image_annotations.py
└── build_* / train_* / evaluate_* / analyze_* 等实验脚本
```

说明：

- 当前没有独立的 `scripts/` 分类目录，实验脚本直接放在 `rag_qa/` 根下。
- `ragas_paper_bundle/` 是论文/展示用数据与图表目录，不是官方 `ragas` 评估运行器源码目录。
- 查询分类器当前优先加载 `macbert_query_classifier_v2/`；如新模型目录不存在，运行时才会回退到 `bert_query_classifier_new/`。

## 查询分类器现状

- 当前线上优先模型：`macbert_query_classifier_v2/`
- 当前基础模型基座：`models/chinese-macbert-base/`
- 回退模型：`bert_query_classifier_new/`
- 最新测试集：`classify_data/query_classifier_test_v2.jsonl`（100 条）
- 最新测试结果：MacBERT 版本准确率 100%（100/100），旧 BERT 版本准确率 70%（70/100）
- 关键改进：旧模型会把大量“采矿语境下的通用问题”误判为“专业咨询”；新模型在该测试集上的 30 个旧错样本上全部修正，且没有新增回归样本

## 🚀 快速开始

### 环境要求
- Python 3.8+
- Node.js 18.x LTS
- npm 9+
- Docker Desktop 4.x+（需可用 `docker compose` v2）
- CUDA 11.0+ (可选，用于 GPU 加速)

补充说明：

- Node.js 18.x 的依据是当前前端容器镜像使用 `node:18-alpine`，本地开发建议与容器保持一致。
- npm 9+ 的依据是当前前端 [web/frontend/package-lock.json](web/frontend/package-lock.json#L1) 使用 `lockfileVersion: 3`。
- Docker 口径以 `docker compose` v2 为准；如果本机只有旧版 `docker-compose` 命令，不视为当前默认开发环境达标。
- 当前推荐 Python 环境仍为 `rag_qa/.venv`，不建议把其他解释器作为默认环境。

### 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 环境变量（强烈推荐）

```bash
# 在项目根目录执行
cp ../.env.example ../.env
# 或在 rag_qa 目录下
cp .env.example .env
```

填入真实密钥后，再启动服务。代码会优先读取 `EDURAG_*` 环境变量。

### 环境约定（推荐）

本项目默认使用 `rag_qa/.venv` 作为唯一 Python 运行环境。

- VS Code 解释器应指向：`rag_qa/.venv/Scripts/python.exe`（Windows）
- 后端启动与脚本运行都在该环境下执行
- 若已存在 conda 环境，建议仅保留为备用，不作为默认开发环境

快速自检当前是否在正确环境：

```bash
python -c "import sys; print(sys.executable)"
```

输出路径包含 `rag_qa/.venv` 即为正确。

VS Code 一键自检（推荐）：

- 任务名：`Env: Self-check (.venv)`
- 作用：输出当前解释器路径、关键依赖状态、后端入口导入状态
- 脚本位置：`../.vscode/check_env.ps1`

### 运行模式速览

| 场景 | 入口 | 依赖 | 说明 |
| --- | --- | --- | --- |
| 工程联调 | `../start_edurag.bat` / `../start_edurag.ps1` | 本地 backend/frontend + Compose 管理的 MinIO/etcd/Milvus | 当前推荐方式 |
| 手动前后端联调 | `web/backend/main.py` + `web/frontend/` | 同上 | 适合单独调试前后端 |
| 独立公众号标注 | `web/backend/wechat_annotator_main.py` | 前端 + 标注路由；不依赖主 RAG 栈 | 适合只做图片标注 |
| CLI / 实验脚本 | `rag_main.py`、`run_wechat_*`、`build_*`、`train_*`、`evaluate_*` | 视脚本而定 | 适合批处理、实验和数据构建 |

说明：

- 如果你关心“哪些入口属于稳定主链路、哪些只是实验脚本”，请直接看 [../TECHNICAL_DOCUMENTATION.md](../TECHNICAL_DOCUMENTATION.md) 中的工程入口、脚本边界和任务用途章节。
- 如果你在新窗口中继续修改项目，请同时遵守 [../DEVELOPMENT_TEST_RELEASE_BASELINE.md](../DEVELOPMENT_TEST_RELEASE_BASELINE.md) 中的文档同步规则。

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

**Windows 双击启动整个项目：**
```text
在项目根目录双击 start_edurag.bat
```

它会自动：
- 检查 `rag_qa/.venv`
- 如有需要先执行前端依赖安装
- 启动后端和前端
- 等待前端就绪后自动打开浏览器

启动日志会写入 `rag_qa/logs/launcher/`

**后端 API 服务：**
```bash
cd web/backend
python -m uvicorn main:app --reload --reload-dir ../../web/backend --reload-dir ../../core --reload-dir ../../base --host 0.0.0.0 --port 8000
```

也可使用 VS Code 任务：`Backend: Run Uvicorn (.venv)`（会先自动执行环境自检）。

若当前目标是稳定联调而不是热重载，建议改用：

```bash
cd web/backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

或直接使用 VS Code 任务：`Backend: Run Uvicorn Stable (.venv)`。

**前端开发服务：**
```bash
cd web/frontend
npm install
npm run dev
```

**独立公众号标注服务：**
```bash
cd web/backend
python -m uvicorn wechat_annotator_main:app --reload --host 0.0.0.0 --port 8001
```

这个轻量入口只暴露 `/api/wechat-annotator` 和 `/api/health`，不导入聊天、知识库和会话主栈。

### 本地联调流程

如果你在 VS Code 里手动联调，建议按下面顺序：

1. 先启动后端，优先使用 `start_edurag.bat` 或 `start_edurag.ps1`。
2. 后端默认优先占用 `8000`，如果被占用，启动器会先尝试相邻候选端口，再回退到随机高位端口。
3. 前端默认把 `/api` 代理到 `http://127.0.0.1:8000`；如果后端最终落在其他端口，启动器会自动注入正确的代理目标。
4. 登录报错时先看状态码：`401` 通常是工号或密码错误，`404` 通常是代理配置或后端未连通。

开发服务稳定性补充：

- 启动器和 VS Code 后端任务当前都会开启 `EDURAG_DEV_FAST_STARTUP=1`，开发态默认跳过 RAG 预热。
- 当前热重载已收窄到代码目录，不再递归监视整个仓库。
- 如需最稳的本地联调入口，可直接运行 VS Code 任务：`Project: Run stable local app`。

手动启动前端时，如果后端不在 `8000`，请显式设置代理目标：

```powershell
$env:VITE_API_PROXY_TARGET = 'http://127.0.0.1:8001'
cd web/frontend
npm run dev
```

**主程序（命令行交互）：**
```bash
python rag_main.py
```

**微信公众号历史页抓取前的登录态转换：**
```powershell
cd rag_qa
python convert_wechat_cookie_to_jar.py
```

脚本会优先读取剪贴板；如果没有内容，就把 DevTools 里复制出来的 `Cookie` 字符串粘贴进去，生成的 `cookies.jar` 可直接被公众号采集器复用。

## 📚 API 文档

启动后端服务后，访问 `http://localhost:8000/docs` 查看完整的 Swagger API 文档。

### 核心接口

说明：本节只保留应用层最常用接口速览，不承担完整 API 事实基线。完整接口列表以 [../TECHNICAL_DOCUMENTATION.md](../TECHNICAL_DOCUMENTATION.md) 的 API 接口规范章节和实际后端路由为准。

**认证相关：**
- `POST /api/auth/login` - 用户登录
- `POST /api/auth/logout` - 用户登出
- `GET /api/auth/verify` - 验证 Token

**对话相关：**
- `POST /api/chat/send` - 提交对话请求
- `GET /api/chat/examples` - 获取示例问题
- `GET /api/chat/source-detail` - 获取来源详情

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
- 默认演示密码：通过 `EDURAG_DEFAULT_SUPERVISOR_PASSWORD` 配置（默认仅为演示值，务必自行修改）

## 📊 工业化功能说明

说明：这一节保留能力摘要，不再承担当前版本范围、阶段状态或验收标准的维护职责；这些内容分别以根目录治理文档为准。

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

由于项目包含大量模型文件和数据，Git 仓库只保留“代码 + 配置 + 启动/生成脚本”，大文件通过脚本或网盘补齐。

### 仓库中保留的内容
- 核心代码：`core/`、`base/`、`edu_document_loaders/`、`edu_text_spliter/`
- Web 应用：`web/backend/`、`web/frontend/`
- 启动与工具脚本：`start_edurag.bat`、`start_edurag.ps1`、`download_models.py`、`generate_pdf_docs.py`、`generate_training_data.py`
- 项目级 VS Code 配置：`.vscode/check_env.ps1`、`.vscode/settings.json`、`.vscode/tasks.json`
- 小型示例数据：`samples/` 中用于首次运行验证和演示的少量示例文件
- 说明文档：`README.md`、`MODELS_README.md`、`PROJECT_STRUCTURE.md`、`INDUSTRIAL_FEATURES_PLAN.md`

### 仓库外保留的内容
- 模型文件：`models/`、`macbert_query_classifier_v2/`、`bert_query_classifier_new/`、`bert_strategy_classifier/`、`nlp_bert_document-segmentation_chinese-base/`
- 运行数据：`data/`、`conversations/`、`knowledge_versions/`、`feedback_data/`、`audit_logs/`、`samples/`
- 缓存和日志：`logs/`、`tmp_trainer/`、`*.log`

### 别人拉取项目后的恢复流程
1. 拉取代码仓库
2. 复制 `.env.example` 为 `.env` 并填写真实密钥
3. 复制 `config.ini.template` 为 `config.ini`
4. 安装依赖：`pip install -r requirements.txt`
5. 运行模型下载脚本：`python download_models.py`
6. 如果需要构建数据集或文档，再执行对应生成脚本
7. 启动后端和前端，或直接双击 `start_edurag.bat`

### 如果需要完整离线包
完整模型和示例数据可以单独放在网盘或离线包里，再按目录结构解压回项目根目录。

**网盘链接：** [百度网盘链接]

**下载后操作：**
1. 解压到项目根目录
2. 按上面的“恢复流程”执行
3. 运行后端和前端服务

## 🧪 测试

```bash
# 基础 smoke test
.venv\Scripts\python.exe -m unittest tests.test_smoke

# 检索策略选择器回归测试
.venv\Scripts\python.exe -m unittest tests.test_strategy_selector
```

说明：

- `tests/` 是当前维护中的测试目录。
- `rag_qa/` 根下的 `test_*.py` 主要是历史验证脚本或临时实验脚本，不等于统一测试套件。

## 📝 文档

- `INDUSTRIAL_FEATURES_PLAN.md` - 工业化功能详细方案
- `PROJECT_STRUCTURE.md` - 项目结构与整理说明
- `MODELS_README.md` - 模型文件说明

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

请以工作区根目录 `README.md` 中的项目信息为准。

## 📧 联系方式

如有问题或建议，请以工作区根目录 `README.md` 中的联系方式为准。

---

**最后更新：** 2026-04-14
