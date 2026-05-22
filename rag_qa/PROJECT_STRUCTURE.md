# EduRAG 当前项目结构说明

> 本文档描述的是当前仓库里的真实结构与职责边界。目录事实、主入口和脚本边界以本文件为准，README 只保留摘要。

## 1. 总体分层

当前工作区可以理解为两层：

- 工作区根目录：负责启动编排、Docker Compose 基础设施、VS Code 任务、运维脚本和共享数据目录。
- `rag_qa/`：应用主体代码仓，包含后端、前端、RAG 核心逻辑、模型、实验脚本、运行时数据和专题文档。

## 2. 工作区根目录

```text
Graduation-Project/
├── README.md
├── start_edurag.bat
├── start_edurag.ps1
├── docker-compose.yml
├── docker-compose.monitoring.yml
├── docker-compose.prod.yml
├── .vscode/
├── ops/
├── scripts/
├── data/
├── minio-data/
└── rag_qa/
```

### 2.1 根目录关键职责

| 路径 | 作用 |
| --- | --- |
| `README.md` | 整个工作区的主入口文档，说明工程版启动、端口约定和联调方式 |
| `start_edurag.bat` / `start_edurag.ps1` | Windows 下一键启动入口；优先启动本地后端和前端，并结合 Compose 启动 MinIO / etcd / Milvus |
| `docker-compose.yml` | 开发/验证用基础编排，同时包含 minio/etcd/milvus/backend/frontend 定义 |
| `docker-compose.monitoring.yml` | Prometheus / Grafana 监控叠加编排 |
| `docker-compose.prod.yml` | 生产环境覆盖编排，要求通过环境变量提供敏感凭据 |
| `.vscode/` | 工作区任务、自检脚本和 VS Code 设置 |
| `ops/` | Grafana、Prometheus 等运维配置 |
| `scripts/` | 根目录级辅助脚本，如仓库自检、环境变量初始化 |
| `data/`、`minio-data/` | 工作区级数据与对象存储持久化目录 |
| `rag_qa/` | 应用主体源码、文档、模型目录、实验脚本和运行时数据 |

## 3. rag_qa 应用主体

```text
rag_qa/
├── README.md / 项目使用指南.md / TECHNICAL_HANDBOOK.md / SYSTEM_ARCHITECTURE.md / 文档索引.md
├── base/                         # 配置、日志、公共基础能力
├── core/                         # RAG / 检索 / 对话核心逻辑
├── edu_document_loaders/         # PDF、PPT、Word、图片等加载与 OCR
├── edu_text_spliter/             # 中文文本切分与分块策略
├── web/
│   ├── backend/                  # FastAPI 后端、轻量标注入口、路由、schema
│   └── frontend/                 # Vue 3 + Vite 前端、API、路由、页面
├── tests/                        # 当前维护中的 unittest 测试
├── examples/                     # 示例脚本
├── models/                       # Embedding / reranker 模型目录
├── macbert_query_classifier_v2/
├── bert_query_classifier_new/
├── bert_strategy_classifier/
├── bert_strategy_classifier_v2/
├── nlp_bert_document-segmentation_chinese-base/
├── data/ / samples/ / classify_data/
├── conversations/ / knowledge_versions/ / feedback_data/ / audit_logs/ / user_data/ / logs/
├── ragas_paper_bundle/ / rag_assesment/
├── rag_main.py
├── run_wechat_collector.py / run_wechat_cleaner.py / sync_image_annotations.py
├── build_* / generate_* / train_* / evaluate_* / analyze_* / check_* / test_*.py
└── 其他专题文档与实验产物目录
```

### 3.1 核心代码目录

| 路径 | 作用 |
| --- | --- |
| `base/` | 配置读取、结构化日志、公共基础能力 |
| `core/` | RAG 检索、向量存储、问答链路、分类器、策略选择器 |
| `edu_document_loaders/` | PDF、PPT、Word、图片等文档加载与 OCR 入口 |
| `edu_text_spliter/` | 中文文本切分与分块策略 |
| `web/backend/` | FastAPI 后端接口、轻量标注入口、路由、服务装配 |
| `web/frontend/` | Vue 3 + Vite 前端页面、路由、API 调用 |
| `tests/` | 当前维护中的 unittest 测试，包含 smoke test 和策略选择器回归测试 |
| `examples/` | 面向演示和验证的示例脚本 |

### 3.2 模型与分类器目录

| 路径 | 作用 |
| --- | --- |
| `models/` | BGE embedding、reranker 等通用模型目录 |
| `macbert_query_classifier_v2/` | 当前默认查询分类模型目录（MacBERT 微调产物） |
| `bert_query_classifier_new/` | 旧版查询分类模型目录（运行时回退保留） |
| `bert_strategy_classifier/` | 旧版策略分类模型目录 |
| `bert_strategy_classifier_v2/` | 新版策略分类模型目录与产物 |
| `nlp_bert_document-segmentation_chinese-base/` | 文档分割相关模型目录 |

补充说明：

- 查询分类器运行时优先解析 `macbert_query_classifier_v2/`，仅在该目录无效或缺失时回退到 `bert_query_classifier_new/`。
- 最新 `query_classifier_test_v2.jsonl` 测试中，MacBERT 查询分类器为 100/100，旧 BERT 查询分类器为 70/100。

### 3.3 运行时数据与产物目录

| 路径 | 作用 |
| --- | --- |
| `conversations/` | 会话历史与相关持久化数据 |
| `knowledge_versions/` | 知识库版本信息 |
| `feedback_data/` | 用户反馈数据 |
| `audit_logs/` | 审计日志数据 |
| `user_data/` | 用户上传或对象化业务数据 |
| `logs/` | 应用日志和启动器日志 |
| `data/`、`samples/`、`classify_data/` | 内部样本数据、分类数据和演示素材 |
| `ragas_paper_bundle/` | 论文/展示用数据集、结果 JSON、图表和策略选择器实验目录 |
| `rag_assesment/` | 历史评估数据集生成目录和中间产物 |
| `tmp_trainer/`、`test_conversations/` | 临时训练产物和测试数据目录 |

## 4. 当前主入口文件

| 文件 | 作用 |
| --- | --- |
| `../start_edurag.ps1` | 工作区级启动编排，负责环境检查、端口探测、Compose 基础设施和前后端启动 |
| `../scripts/setup_edurag_env.ps1` | Windows 环境变量初始化与密钥对齐 |
| `../.vscode/tasks.json` | VS Code 常用任务定义 |
| `web/backend/main.py` | FastAPI 主应用入口，注册所有主路由、中间件、健康检查和 metrics |
| `web/backend/wechat_annotator_main.py` | 轻量公众号标注入口，只注册标注路由 |
| `web/frontend/src/main.js` | Vue 前端入口 |
| `rag_main.py` | 命令行模式下的 RAG 主入口 |
| `run_wechat_collector.py` | 公众号采集主入口 |
| `run_wechat_cleaner.py` | 公众号采集结果清洗入口 |
| `sync_image_annotations.py` | 图片标注结果同步回检索材料 |
| `evaluate_strategy_selector.py` | 检索策略选择器诊断基准脚本 |
| `build_metallurgy_dataset_experiments.py` | 论文/展示用实验数据、结果摘要和图表生成脚本 |

## 5. 根下大量 Python 脚本的实际分类

`rag_qa/` 根下保留了较多前缀脚本，它们当前主要承担如下职责：

| 脚本前缀 / 文件 | 主要职责 |
| --- | --- |
| `analyze_*` | 数据分析、问题诊断、结果复盘 |
| `build_*` | 数据集构建、实验样本整理、结果包生成 |
| `generate_*` | 数据、报告、图表、说明文档生成 |
| `train_*` | 分类器训练与训练报告 |
| `evaluate_*` | 诊断评估、实验打分、策略对比 |
| `check_*` | 环境、数据库、OCR、文档内容检查 |
| `test_*.py`（根目录） | 历史验证脚本、临时实验脚本，不是统一测试套件 |
| `run_wechat_*` / `sync_*` | 公众号链路采集、清洗、标注同步 |

说明：

- 当前仓库没有单独的 `rag_qa/scripts/` 目录，脚本就是直接分布在 `rag_qa/` 根下。
- Web 应用主入口仍然是 `start_edurag.ps1`、`web/backend/main.py` 和 `web/frontend/src/main.js`，不要让实验脚本替代工程入口。

## 6. 关于评估与实验目录的边界

- `ragas_paper_bundle/`：保存论文/展示用数据集、结果 JSON、图表和策略选择器实验产物；其中包含 RAGAS 格式导出数据，但不代表仓库内存在官方 `ragas` 评估运行器。
- `rag_assesment/`：保存历史生成数据集和中间产物，主要用于实验数据准备。
- `tests/`：当前维护中的测试目录，应优先用这里的测试作为回归基线。
- `rag_qa/` 根下的 `test_*.py`：多为临时验证脚本，是否可直接运行需要结合脚本头部说明和当前环境判断。

## 7. 阅读建议

- 想跑起项目：先看 [../README.md](../README.md) 和 [项目使用指南.md](%E9%A1%B9%E7%9B%AE%E4%BD%BF%E7%94%A8%E6%8C%87%E5%8D%97.md)。
- 想理解后端和前端主链路：看 [TECHNICAL_HANDBOOK.md](TECHNICAL_HANDBOOK.md)。
- 想区分主系统与实验脚本：先看本文件的第 5、6 节。
- 想找专题说明：回到 [文档索引.md](%E6%96%87%E6%A1%A3%E7%B4%A2%E5%BC%95.md)。
