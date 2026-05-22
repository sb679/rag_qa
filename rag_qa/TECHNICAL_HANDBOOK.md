# EduRAG 技术总览手册（面向 AI 快速接手）

本文档目标：让新开窗口的 AI 在不通读全部代码的前提下，先建立正确的系统认知，再按需进入具体文件。

## 1. 项目定位

EduRAG 是一个采矿安全领域的 RAG 问答系统，包含：
- RAG 检索问答（专业回答）
- 通用知识直答模型 + 专业 RAG 主回答模型的模型级分流
- 通用 LLM 对比回答（按需触发，可分离模型配置）
- Web 前后端（FastAPI + Vue3 + Element Plus）
- 知识库、会话、用户、反馈、版本管理
- 微信公众号采集与图片标注链路

## 2. 文档角色

这份文档属于“架构与接手层”，目标是让人或 AI 在 10 到 20 分钟内建立正确心智模型。

它适合回答：
- 主入口在哪里
- 系统由哪些层组成
- 问答流、知识库流、公众号流怎么串起来
- 接下来该读哪些文件

它不负责维护以下内容的最终事实基线：
- 端口、启动命令、运行判定
- 数据落盘位置总表
- 配置项完整映射

这些应以 [../TECHNICAL_DOCUMENTATION.md](../TECHNICAL_DOCUMENTATION.md) 和 [../README.md](../README.md) 为准。

## 3. 技术栈与运行形态

- 后端：FastAPI
- 前端：Vue 3 + Vite + Element Plus
- 向量库：Milvus
- 对象存储：MinIO
- 元数据协调：etcd
- Python 环境：rag_qa/.venv（推荐唯一环境）
- 启动脚本：项目根目录 start_edurag.ps1 / start_edurag.bat
- 轻量标注入口：web/backend/wechat_annotator_main.py
- 监控覆盖：docker-compose.monitoring.yml
- 容器化验证：docker-compose.yml 中也提供 backend/frontend 容器定义，但日常开发仍推荐本地 hybrid 模式

默认端口约定（本地）：
- Backend: 8000（冲突时回退 8001）
- Frontend: 5173（冲突时回退 5174）
- MinIO: 19000/19001（容器内 9000/9001）
- Milvus: 19530（容器内 19530）

## 4. 当前系统主入口

- 后端入口：web/backend/main.py
- 公众号标注轻量入口：web/backend/wechat_annotator_main.py
- 前端入口：web/frontend/src/main.js（由 Vite 启动）
- 启动编排：../start_edurag.ps1
- CLI 主入口：rag_main.py
- 公众号链路：run_wechat_collector.py / run_wechat_cleaner.py / sync_image_annotations.py
- 代表性实验入口：evaluate_strategy_selector.py / build_metallurgy_dataset_experiments.py

后端路由注册（main.py）：
- /api/users
- /api/auth
- /api/feedback
- /api/kb-version
- /api/chat
- /api/sessions
- /api/knowledge
- /api/dataset
- /api/testgen
- /api/wechat-annotator

## 5. 前端核心页面

位于 web/frontend/src/views：
- LoginView.vue：登录页
- DashboardView.vue：驾驶舱
- ChatView.vue：问答页（流式消息、来源展示、公众号 Agent 入口）
- KnowledgeView.vue：知识库概览页
- WechatAnnotatorView.vue：公众号采集与图片标注工作台（代码保留，前端入口默认隐藏，需 `VITE_ENABLE_WECHAT_ANNOTATOR=true` 才显示）
- ConfigView.vue：系统配置
- EmployeeManageView.vue：员工管理

## 6. 后端关键模块职责

- web/backend/rag_service.py
  - 聊天主流程、流式输出、查询类型后置纠偏、模型级分流
  - 专业检索证据状态汇总（如父块重排命中、弱子块证据）
  - LLM 熔断器与依赖状态对外暴露

- web/backend/routers/knowledge.py
  - 知识库状态接口（前端 KnowledgeView 依赖）

- core/vector_store.py
  - 向量检索、统计与知识概览聚合
  - 需要注意 Milvus 查询窗口限制（见“常见问题”）

- web/backend/routers/wechat_annotator.py
  - 公众号文章列表、文章详情、图片标注保存、自动预填、导出

- run_wechat_collector.py
  - 公众号文章采集（支持 history_urls 与 article_urls）
  - 账号级采集锁、已产物文章跳过（断点续跑）

- run_wechat_cleaner.py
  - 清洗采集结果，产出 cleaned/media 文档

- sync_image_annotations.py
  - 将人工标注同步为可检索索引文档

### 5.1 实验与评估目录边界

- `ragas_paper_bundle/`：论文/展示用数据集、结果摘要、图表和策略选择器实验目录，其中包含 RAGAS 格式导出数据，但不等于官方 `ragas` 评估运行器源码。
- `rag_assesment/`：历史生成数据集和中间产物目录。
- `tests/`：当前维护中的 unittest 测试目录。
- `rag_qa/` 根下的 `test_*.py`：多为临时验证脚本或历史实验脚本，不应默认当成正式测试套件。

## 7. 微信链路（采集 -> 清洗 -> 标注 -> 检索）

推荐最小闭环：
1. run_wechat_collector.py 采集文章与图片信息
2. run_wechat_cleaner.py 生成 cleaned.md / media_index.md
3. 前端 WechatAnnotatorView 做人工标注与导出
4. sync_image_annotations.py 将标注写回检索材料
5. 触发入库后在 Chat / Knowledge 侧可检索

注意：
- history_urls 用于“按历史页自动扩展链接”；article_urls 用于“手工详情页直抓”。
- 采集器当前有账号级锁，避免同账号并发重复采集。
- 对已完成文章会做产物存在判断，支持中断后续跑。

## 8. 当前问答路由心智模型

如果只记一件事，当前链路不是“所有问题都先检索，再统一交给一个模型回答”，而是：

1. 先做“通用知识 / 专业咨询”二分类。
2. 再由 `rag_service.py` 用硬规则、边界负样本和检索证据做后置修正。
3. 通用知识主回答直接走通用直答模型；专业咨询才进入检索和专业回答模型。
4. 右侧面板展示的是“命中证据”，不是“答案可信度”。高 rerank 只表示父块主题相关，不自动等于证据充分。

当前最容易误解的两个点：

- “命中文档”不等于“足以给出高风险现场方案”。如果只有父块重排命中，没有稳定子块证据，前后端都会把这件事显式说出来。
- “对比回答”不是默认链路。只有用户显式点击时，系统才会再调用通用 LLM 生成第二路回答用于对比。

## 9. 知识库统计与 Milvus 窗口限制

问题现象：
- 知识库页提示“内部服务错误”或统计降级。
- 后端日志可能出现 Milvus invalid max query result window。

原因：
- Milvus 对 offset + limit 有窗口上限（常见 16384）。
- 若代码一次性查询超过窗口，会抛异常。

当前处理策略：
- 统计逻辑应避免超窗查询，必要时做限制/降级。
- 前端 KnowledgeView 需要展示错误态和空态，不应白屏。

## 9. 配置与安全约定

- 配置来源优先级：EDURAG_* 环境变量优先于 config.ini
- 严禁把真实 API Key 写入仓库
- .env 仅本地使用，仓库提交 .env.example
- 启动脚本会注入本地联调环境变量（MinIO/Milvus 等）

## 10. 给新窗口 AI 的阅读顺序（10-20 分钟）

第 1 轮（先看文档）：
1. 本文件 TECHNICAL_HANDBOOK.md
2. README.md（项目根 + rag_qa/README.md）
3. 项目使用指南.md
4. PROJECT_STRUCTURE.md
5. 微信采集说明：微信公众号采集agent说明.md

第 2 轮（再看入口代码）：
1. web/backend/main.py
2. web/backend/rag_service.py
3. web/frontend/src/views/ChatView.vue
4. web/frontend/src/views/KnowledgeView.vue
5. web/frontend/src/views/WechatAnnotatorView.vue

第 3 轮（按问题深入）：
- 知识库统计：core/vector_store.py + routers/knowledge.py
- 采集问题：run_wechat_collector.py + run_wechat_cleaner.py
- 标注问题：routers/wechat_annotator.py + sync_image_annotations.py

## 11. AI 接手时建议输入模板

可直接复制给新窗口 AI：

"""
请先阅读以下文档并以其为事实基线：
1) rag_qa/TECHNICAL_HANDBOOK.md
2) rag_qa/README.md
3) rag_qa/微信公众号采集agent说明.md

然后只阅读这些入口代码：
- rag_qa/web/backend/main.py
- rag_qa/web/backend/rag_service.py
- rag_qa/web/frontend/src/views/ChatView.vue
- rag_qa/web/frontend/src/views/KnowledgeView.vue
- rag_qa/web/frontend/src/views/WechatAnnotatorView.vue

输出：
- 系统关键数据流（问答流、知识库流、公众号流）
- 当前风险点（配置、统计、并发、错误处理）
- 你要修改的最小文件集合
"""

## 12. 文档边界声明

这份手册用于“快速建立共识”，不是 API 逐字段手册。

遇到以下场景必须回到代码核对：
- 路由字段细节、响应结构
- 最近刚修复的 bug 行为
- 与部署环境强相关的配置覆盖
- 任何报错链路定位

结论：
- 仅看旧文档，不足以完整理解项目。
- 看本手册 + 入口代码，可以覆盖 80% 以上问题定位。
- 高风险改动前，仍需做针对性代码阅读与本地验证。
