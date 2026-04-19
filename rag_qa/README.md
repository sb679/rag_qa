# EduRAG 采矿安全智能问答系统

一个基于 RAG（检索增强生成）技术的采矿安全领域智能问答系统，集成了权限控制、用户反馈、知识库版本管理等工业级功能。

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

## 📋 项目结构

```
rag_qa/
├── core/                              # 核心业务逻辑
│   ├── rag_system.py                 # RAG 系统主体
│   ├── query_classifier.py           # 查询分类器
│   ├── strategy_selector.py          # 策略选择器
│   ├── conversation_manager.py       # 会话管理
│   ├── auth_manager.py               # 权限控制（新增）
│   ├── feedback_manager.py           # 反馈管理（新增）
│   ├── citation_manager.py           # 引用管理（新增）
│   └── knowledge_version_manager.py  # 版本管理（新增）
│
├── base/                              # 基础模块
│   ├── config.py                     # 配置管理
│   └── logger.py                     # 日志系统
│
├── edu_document_loaders/              # 文档加载器
│   ├── edu_pdfloader.py
│   ├── edu_pptloader.py
│   ├── edu_docloader.py
│   ├── edu_imgloader.py
│   └── edu_ocr.py
│
├── edu_text_spliter/                  # 文本分割器
│   ├── edu_chinese_recursive_text_splitter.py
│   └── edu_model_text_spliter.py
│
├── web/                               # Web 应用
│   ├── backend/                       # FastAPI 后端
│   │   ├── main.py                   # 主入口
│   │   └── routers/                  # API 路由
│   │       ├── chat.py               # 对话接口
│   │       ├── sessions.py           # 会话接口
│   │       ├── knowledge.py          # 知识库接口
│   │       ├── auth.py               # 认证接口（新增）
│   │       ├── feedback.py           # 反馈接口（新增）
│   │       └── kb_version.py         # 版本接口（新增）
│   └── frontend/                      # Vue 前端
│       └── src/
│           ├── views/                # 页面组件
│           ├── api/                  # API 调用
│           └── router/               # 路由配置
│
├── scripts/                           # 一次性脚本（按功能分类）
│   ├── data_analysis/                # 数据分析
│   ├── dataset_build/                # 数据集构建
│   ├── data_generation/              # 数据生成
│   ├── model_training/               # 模型训练
│   ├── testing/                      # 测试脚本
│   └── tools/                        # 工具脚本
│
├── bert_query_classifier_new/         # 查询分类模型
├── bert_strategy_classifier/          # 策略分类模型
├── nlp_bert_document-segmentation_chinese-base/  # 文档分割模型
│
├── examples/                          # 示例代码
├── config.ini.template               # 配置模板
├── rag_main.py                       # 主程序入口
├── INDUSTRIAL_FEATURES_PLAN.md       # 工业化功能方案
└── PROJECT_STRUCTURE.md              # 项目结构说明
```

## 🚀 快速开始

### 环境要求
- Python 3.8+
- CUDA 11.0+ (可选，用于 GPU 加速)

### 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirments.txt
```

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
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

也可使用 VS Code 任务：`Backend: Run Uvicorn (.venv)`（会先自动执行环境自检）。

**前端开发服务：**
```bash
cd web/frontend
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

**默认账号：**
- 普通用户：`user` / `password123`
- 主管：`admin` / `admin123`

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

由于项目包含大量模型文件和数据，Git 仓库只保留“代码 + 配置 + 启动/生成脚本”，大文件通过脚本或网盘补齐。

### 仓库中保留的内容
- 核心代码：`core/`、`base/`、`edu_document_loaders/`、`edu_text_spliter/`
- Web 应用：`web/backend/`、`web/frontend/`
- 启动与工具脚本：`start_edurag.bat`、`start_edurag.ps1`、`download_models.py`、`generate_pdf_docs.py`、`generate_training_data.py`
- 项目级 VS Code 配置：`.vscode/check_env.ps1`、`.vscode/settings.json`、`.vscode/tasks.json`
- 小型示例数据：`samples/` 中用于首次运行验证和演示的少量示例文件
- 说明文档：`README.md`、`MODELS_README.md`、`PROJECT_STRUCTURE.md`、`INDUSTRIAL_FEATURES_PLAN.md`

### 仓库外保留的内容
- 模型文件：`models/`、`bert_query_classifier_new/`、`bert_strategy_classifier/`、`nlp_bert_document-segmentation_chinese-base/`
- 运行数据：`data/`、`conversations/`、`knowledge_versions/`、`feedback_data/`、`audit_logs/`、`samples/`
- 缓存和日志：`logs/`、`tmp_trainer/`、`*.log`

### 别人拉取项目后的恢复流程
1. 拉取代码仓库
2. 复制 `config.ini.template` 为 `config.ini`
3. 安装依赖：`pip install -r requirments.txt`
4. 运行模型下载脚本：`python download_models.py`
5. 如果需要构建数据集或文档，再执行对应生成脚本
6. 启动后端和前端，或直接双击 `start_edurag.bat`

### 如果需要完整离线包
完整模型和示例数据可以单独放在网盘或离线包里，再按目录结构解压回项目根目录。

**网盘链接：** [百度网盘链接]

**下载后操作：**
1. 解压到项目根目录
2. 按上面的“恢复流程”执行
3. 运行后端和前端服务

## 🧪 测试

```bash
# 运行测试脚本
python scripts/testing/test_integration.py

# 运行特定测试
python scripts/testing/test_mining_rag.py
```

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

[你的名字]

## 📧 联系方式

如有问题或建议，欢迎联系：[你的邮箱]

---

**最后更新：** 2026-04-14
