# Graduation-Project 关键技术决策记录

## 1. 文档定位

这份文档用于回答“为什么这样做，而不是那样做”。

适用场景：

- 关键架构取舍
- 依赖替换或移除
- 运行模式调整
- 对后续维护影响较大的工程决策

文档层级：工作区治理文档。

维护规则：

- 每条重要决策都应记录背景、结论、影响。
- 不需要长篇论文，但必须能让后来者读懂原因。

## 2. 记录模板

后续新增决策时，建议按下面结构追加：

### ADR-XXXX 标题

- 日期：YYYY-MM-DD
- 状态：拟议 / 采纳 / 废弃 / 被替代
- 背景：
- 决策：
- 影响：
- 相关文档：

## 3. 当前已记录决策

### ADR-2026-04-30-01 采用“工作区根目录治理 + rag_qa 应用主体”双层结构

- 日期：2026-04-30
- 状态：采纳
- 背景：仓库同时承担启动编排、Compose、VS Code 任务、应用代码、实验脚本和专题文档，单层组织会让工作区级事实与应用级事实混杂。
- 决策：将工作区根目录作为启动编排与治理层，将 [rag_qa](rag_qa) 作为应用主体层进行说明和维护。
- 影响：README、启动器、Compose、VS Code 任务留在根目录；应用入口与专题文档留在 rag_qa 下。
- 相关文档：[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)、[rag_qa/PROJECT_STRUCTURE.md](rag_qa/PROJECT_STRUCTURE.md)

### ADR-2026-04-30-02 采用“本地 backend/frontend + Compose 基础设施”的默认开发模式

- 日期：2026-04-30
- 状态：采纳
- 背景：纯容器化开发虽然统一，但调试效率较低；纯本地方式又不利于基础设施一致性。
- 决策：默认开发模式采用本地 backend/frontend，加上 Docker Compose 管理 MinIO、etcd、Milvus。
- 影响：保留一键启动与 VS Code 任务，兼顾本地调试效率和基础设施一致性。
- 相关文档：[README.md](README.md)、[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)

### ADR-2026-04-30-03 将 Milvus 纳入一键启动链路

- 日期：2026-04-30
- 状态：采纳
- 背景：知识入库、知识库统计与 RAG 检索高度依赖 Milvus；若不纳入默认启动链路，会导致“项目启动成功但核心能力不可用”的认知偏差。
- 决策：通过启动器和 Compose 将 Milvus 与其依赖 etcd 纳入默认基础设施启动范围。
- 影响：完整能力更接近默认可用，运行判定也更清晰。
- 相关文档：[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)、[start_edurag.ps1](start_edurag.ps1#L1)、[docker-compose.yml](docker-compose.yml#L1)

### ADR-2026-04-30-04 从当前运行链路移除 MySQL 与 Redis

- 日期：2026-04-30
- 状态：采纳
- 背景：当前业务实现里，用户、会话、反馈、知识版本等状态实际主要落在本地 JSON 文件中，MySQL/Redis 配置与编排残留会误导维护者。
- 决策：从 Compose、配置模板、启动器和主文档中移除 MySQL/Redis 的当前依赖地位。
- 影响：文档与实际运行链路一致，减少错误依赖认知。
- 相关文档：[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)、[rag_qa/base/config.py](rag_qa/base/config.py#L1)、[docker-compose.yml](docker-compose.yml#L1)

### ADR-2026-04-30-05 建立分层文档治理模型

- 日期：2026-04-30
- 状态：采纳
- 背景：项目规模扩大后，README、技术文档、架构文档、运行手册、专题文档容易相互覆盖，导致事实漂移。
- 决策：将文档分为入口层、稳定事实层、运行手册层、架构接手层、目录导航层、专题深挖层。
- 影响：不同信息写到不同文档，降低重复维护和冲突风险。
- 相关文档：[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md#L58)、[README.md](README.md)、[rag_qa/文档索引.md](rag_qa/%E6%96%87%E6%A1%A3%E7%B4%A2%E5%BC%95.md)

### ADR-2026-04-30-06 上传链路在对象存储写入前先检查向量库可用性

- 日期：2026-04-30
- 状态：采纳
- 背景：原实现中，上传接口可能先把文件写入对象存储，再发现向量库不可用，从而留下半成品数据。
- 决策：将向量库就绪检查提前到对象存储写入之前，只有在可入库条件满足时才继续上传链路。
- 影响：减少无效文件残留，使上传行为与完整能力预期更一致。
- 相关文档：[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)、[rag_qa/web/backend/routers/dataset.py](rag_qa/web/backend/routers/dataset.py#L1)

### ADR-2026-04-30-07 当前业务状态继续以本地 JSON 为主，而非强行重建关系库

- 日期：2026-04-30
- 状态：采纳
- 背景：当前用户、会话、反馈、知识版本等状态已经稳定落在本地 JSON 文件；若在当前阶段强行恢复关系库，会显著扩大范围。
- 决策：在当前阶段保留本地 JSON 为主的数据状态实现，并在主技术文档中明确这一事实。
- 影响：运行链路更贴近代码现状，范围控制更清晰，但也意味着未来若走正式产品化，需要再单独规划状态存储演进。
- 相关文档：[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md#L519)、[PROJECT_CHARTER_AND_SCOPE.md](PROJECT_CHARTER_AND_SCOPE.md)

### ADR-2026-04-30-08 使用“治理文档 + 稳定事实文档”双轨同步机制

- 日期：2026-04-30
- 状态：采纳
- 背景：仅维护技术细节文档，会丢失版本迭代与决策原因；仅维护迭代记录，又会丢失稳定工程事实。
- 决策：技术细节进入 [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)，进度进入 [MILESTONES_AND_ITERATION_TRACKER.md](MILESTONES_AND_ITERATION_TRACKER.md)，关键原因进入本文件，验证口径进入 [DEVELOPMENT_TEST_RELEASE_BASELINE.md](DEVELOPMENT_TEST_RELEASE_BASELINE.md)。
- 影响：新窗口或后续接手时可以按“事实、进度、原因、验收”四条线恢复上下文。
- 相关文档：[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)、[MILESTONES_AND_ITERATION_TRACKER.md](MILESTONES_AND_ITERATION_TRACKER.md)、[DEVELOPMENT_TEST_RELEASE_BASELINE.md](DEVELOPMENT_TEST_RELEASE_BASELINE.md)

### ADR-2026-05-08-01 公众号链路采用“有限 ReAct + LLM 规划 + 可见短期记忆”而非开放式通用自治 Agent

- 日期：2026-05-08
- 状态：采纳
- 背景：公众号采集链路既需要自然语言入口和“像 Agent 一样”的规划解释能力，又不能放弃当前已经稳定的账号匹配、历史页抓取、桌面回退、清洗、入库、标注工具链。如果直接切到开放式通用自治 Agent，会显著扩大能力边界、可控性风险和排障成本。
- 决策：保持公众号链路以有限 ReAct 工作流为骨架，用 LLM 负责能力边界判断、意图分类、结构化计划生成和省略表达补全；执行仍落在确定性工具链。同时把大脑状态、计划步骤、短期记忆、账号锁定状态做成前端可见状态，而不是保留在黑箱内部。
- 影响：公众号 Agent 当前更可解释、更可控，用户能直接看到“为什么这样执行”；代价是它仍然是领域受限 Agent，而不是通用任务代理。完成反馈和阶段日志也被要求共用同一份执行事实源，避免 UI 层各自猜因造成认知分裂。
- 相关文档：[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)、[rag_qa/微信公众号采集agent说明.md](rag_qa/%E5%BE%AE%E4%BF%A1%E5%85%AC%E4%BC%97%E5%8F%B7%E9%87%87%E9%9B%86agent%E8%AF%B4%E6%98%8E.md)、[README.md](README.md)、[DEVELOPMENT_TEST_RELEASE_BASELINE.md](DEVELOPMENT_TEST_RELEASE_BASELINE.md)

### ADR-2026-05-16-01 公众号多 Agent 采用“单服务中心编排 + 内部协议兼容 A2A 方向”而非直接上分布式多智能体

- 日期：2026-05-16
- 状态：采纳
- 背景：项目需要把公众号链路从“像 Agent 一样的工作台”推进到更有说服力的多 Agent 形态，但当前系统仍然集中在单仓库、单后端服务和本地工具链中。如果直接引入远程 Agent 注册、发现和跨服务通信，会显著扩大实现范围与排障面，同时削弱当前演示和迭代效率。
- 决策：保持后端以 `knowledge_orchestrator` 为中心编排器，在单服务内部按 `knowledge_acquisition_agent` -> `knowledge_governance_agent` -> `evaluation_optimization_agent` route 执行，并通过统一的 `orchestration` 对象表达 `task`、`shared_context`、`artifacts`、`review`、`handoffs`、`completed_agents` 和 `next_agent`。协议字段设计保留 A2A 兼容方向，但当前不把它表述成完整的远程多智能体网络。
- 影响：实现范围可控，前后端可以快速形成可演示的三段闭环；同时也要求文档和答辩口径明确说明“这是协议化单服务编排，不是分布式多 Agent 平台”。
- 相关文档：[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md#L524)、[MILESTONES_AND_ITERATION_TRACKER.md](MILESTONES_AND_ITERATION_TRACKER.md)、[rag_qa/web/backend/routers/wechat_annotator.py](rag_qa/web/backend/routers/wechat_annotator.py#L660)

### ADR-2026-05-16-02 治理与评测 handoff 采用 soft-fail，不回滚已完成采集结果

- 日期：2026-05-16
- 状态：采纳
- 背景：公众号链路在采集成功后，治理和评测阶段可能因为本地文章不存在、规则未命中或后续数据不完整而失败。如果把治理或评测失败直接等同于整轮失败，会掩盖“知识资产已成功创建”的真实结果，也会让 orchestration 状态对用户和答辩观众产生误导。
- 决策：采集成功后，治理和评测作为后续 handoff 执行；若治理或评测失败，保留已完成采集结果，并通过失败步骤、`partial_success`、artifact 缺失和 `review.summary` 表达失败位置，而不回滚采集阶段的成果。
- 影响：系统状态更贴近真实执行结果，用户能看到“采集成功但后续治理/评测失败”的细分结论；代价是前后端和文档都必须明确区分 completed、partial_success 与 failed，不允许把这几类状态混写。
- 相关文档：[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md#L533)、[rag_qa/web/backend/routers/wechat_annotator.py](rag_qa/web/backend/routers/wechat_annotator.py#L660)、[rag_qa/web/frontend/src/views/WechatAnnotatorView.vue](rag_qa/web/frontend/src/views/WechatAnnotatorView.vue#L137)

## 4. 待补充决策

- [待补充] 是否需要定义答辩演示模式与长期维护模式的差异。
- [待补充] 是否需要引入统一的发布前自动校验入口。
- [待补充] 是否需要把评测优化 Agent 从规则骨架升级为可回看历史趋势的正式评测模块。