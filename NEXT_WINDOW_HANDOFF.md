# Graduation-Project 新窗口接力说明

## 1. 这份文档的用途

这份文档只回答 4 个问题：

1. 当前项目做到哪一步。
2. 最近一轮改了什么。
3. 哪些结论已经验证过。
4. 新窗口下一步应该从哪里接。

它不是稳定事实总文档。稳定工程事实仍以 [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md) 为准；进度以 [MILESTONES_AND_ITERATION_TRACKER.md](MILESTONES_AND_ITERATION_TRACKER.md) 为准；决策原因以 [TECHNICAL_DECISION_RECORD.md](TECHNICAL_DECISION_RECORD.md) 为准。

## 2. 当前状态快照

当前最重要的进展是：公众号子系统已经形成“单服务中心编排”的三段式多 Agent 闭环。

当前闭环为：

- `knowledge_acquisition_agent`
- `knowledge_governance_agent`
- `evaluation_optimization_agent`

编排器名称固定为：

- `knowledge_orchestrator`

协议版本当前固定为：

- `v1`

要点：

- 这不是分布式 A2A 网络，而是仓库内单服务的协议化多 Agent 编排。
- 后端会在采集成功后自动尝试治理 handoff；治理成功后自动继续评测 handoff。
- 前端已能直接展示编排卡片，不需要再从日志反推执行到哪里。
- 前端现已额外具备四块诊断视图：判断质量统计、Handoff 契约诊断、评测趋势、结构化失败原因。
- Agent 面板状态、短期记忆和判断统计现在可在关闭标签页后继续恢复，并且已支持按登录用户落到服务端本地状态文件，不再只局限于当前浏览器会话。

## 3. 最近一轮已完成内容

### 后端

- 公众号 Agent 的 `parsed` 结果已经包含 `protocol_version`、`task_type`、`agent_route`、`trace_id`。
- 同步与流式入口最终都返回 `orchestration` 对象。
- `orchestration` 现在还会携带 `protocol` 字段，协议单一事实源位于 [rag_qa/web/backend/routers/wechat_agent_protocol.py](rag_qa/web/backend/routers/wechat_agent_protocol.py)。
- `protocol.agents[*].summary_templates` 已开始承担阶段卡默认摘要，页面只保留状态判断和少量动态值拼接。
- `protocol.agents[*].metric_templates` 也已开始承担阶段卡 metrics 标签文案，页面侧硬编码进一步减少。
- `protocol.handoff_templates[*].input_rules` 已开始承担 handoff 的输入满足规则，页面侧不再写死 `governance_report` / `created_articles` / `clean_result` 的判断分支。
- 协议展示层已经抽到 [rag_qa/web/frontend/src/components/wechat/WechatAgentProtocolOverview.vue](rag_qa/web/frontend/src/components/wechat/WechatAgentProtocolOverview.vue)；如果下一窗口继续拆前端，优先拆任务列表和日志面板，不要再回头碰协议卡片。
- 最近任务列表已经抽到 [rag_qa/web/frontend/src/components/wechat/WechatAgentTaskList.vue](rag_qa/web/frontend/src/components/wechat/WechatAgentTaskList.vue)；下一步最自然的拆分目标只剩任务详情弹窗和执行日志面板。
- 任务详情弹窗也已经抽到 [rag_qa/web/frontend/src/components/wechat/WechatAgentTaskDetailDialog.vue](rag_qa/web/frontend/src/components/wechat/WechatAgentTaskDetailDialog.vue)，并已通过前端 build；下一步只需继续拆执行日志面板和当前运行状态区。
- 已新增治理调试入口：`POST /api/wechat-annotator/agent/governance`
- 已新增评测调试入口：`POST /api/wechat-annotator/agent/evaluation`
- governance 与 evaluation 两个调试入口现在都会返回完整 `orchestration`，可直接做路由级一致性校验。
- 已新增自动评测 handoff：治理成功后会生成最小版 `evaluation_report`
- 评测优化 Agent 现已支持自动读取最近的本地官方 RAGAS 评测快照，并把正式指标摘要写入 `evaluation_report`
- 已修复同步抓取路径的两个局部断点：新文章场景会显式返回 `created_articles`，重复链接场景会显式返回 `all_duplicates`，不再误报 500
- 前端阶段卡与 handoff 契约卡已经改为优先读取 `orchestration.protocol`，下一窗口如果继续扩展第 4 个 Agent，应先改协议注册表，再看是否需要补充对应卡片内容文案。
- 后端测试 [rag_qa/tests/test_wechat_agent_protocol.py](rag_qa/tests/test_wechat_agent_protocol.py) 现已覆盖 observe / decide / clean / orchestration 以及 governance/evaluation 两个调试入口的 HTTP 返回一致性。
- 前端 [rag_qa/web/frontend/vite.config.js](rag_qa/web/frontend/vite.config.js) 已把 Vue Router、Vue Runtime 和 Element Plus 细分拆包；当前 build 已消除 500 kB 以上 chunk warning。

关键文件：

- [rag_qa/web/backend/routers/wechat_annotator.py](rag_qa/web/backend/routers/wechat_annotator.py#L660)
- [rag_qa/web/backend/routers/wechat_annotator.py](rag_qa/web/backend/routers/wechat_annotator.py#L926)
- [rag_qa/web/backend/routers/wechat_annotator.py](rag_qa/web/backend/routers/wechat_annotator.py#L1076)
- [rag_qa/web/backend/routers/wechat_annotator.py](rag_qa/web/backend/routers/wechat_annotator.py#L4676)

### 前端

- WechatAnnotator 页面已新增“多 Agent 编排”卡片。
- 页面会展示 `current_agent`、`next_agent`、`route`、`completed_agents`、治理结果和评测结果。
- 页面中的评测结果区域现可展示 RAGAS 均值、忠实度、上下文精确率、上下文召回率、答案相关性与快照来源。
- 前端入口和顶部页面定位已改成多 Agent 工作台口径，完成反馈会补充“当前停在采集 / 清洗入库 / 治理 / 评测哪一层”的边界说明。
- orchestration 状态已纳入页面快照，刷新后可以恢复。
- 完成日志已补充治理摘要与评测摘要。
- 页面当前会把最近几次 `evaluation_report` 压成趋势卡片，支持直接查看最近记录、RAGAS 均值变化、最新就绪度、最近两次历史对比、长时间窗趋势图，以及对最新历史记录执行手动重跑。
- 页面当前会把“重复链接、频率控制、时间窗过滤、页面受限、治理失败、评测失败”等场景拆成结构化失败原因卡，而不是只输出一段混合文案。

关键文件：

- [rag_qa/web/frontend/src/views/WechatAnnotatorView.vue](rag_qa/web/frontend/src/views/WechatAnnotatorView.vue#L137)
- [rag_qa/web/frontend/src/views/WechatAnnotatorView.vue](rag_qa/web/frontend/src/views/WechatAnnotatorView.vue#L1590)
- [rag_qa/web/frontend/src/views/WechatAnnotatorView.vue](rag_qa/web/frontend/src/views/WechatAnnotatorView.vue#L2942)

### 文档

- 主技术文档已补多 Agent 现状、API 路由和 SSE 返回字段。
- 里程碑文档已补 2026-05-16 这一轮迭代。
- 技术决策文档已补“中心编排 + 内部协议”和“soft-fail handoff”两条决策。
- 开发/测试/发布基线已补 Node.js、npm、Docker、Docker Compose 版本线。
- 已新增 [WECHAT_MULTI_AGENT_DEMO_SCRIPT.md](WECHAT_MULTI_AGENT_DEMO_SCRIPT.md) 作为公众号多 Agent 的固定演示脚本。

关键文件：

- [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md#L524)
- [MILESTONES_AND_ITERATION_TRACKER.md](MILESTONES_AND_ITERATION_TRACKER.md)
- [TECHNICAL_DECISION_RECORD.md](TECHNICAL_DECISION_RECORD.md)

## 4. 已验证项

本轮已经实际验证过的事实：

1. [rag_qa/web/frontend/src/views/WechatAnnotatorView.vue](rag_qa/web/frontend/src/views/WechatAnnotatorView.vue) 诊断无错误。
2. [rag_qa/web/backend/routers/wechat_annotator.py](rag_qa/web/backend/routers/wechat_annotator.py) 诊断无错误。
3. 前端 `npm run build` 已通过。
4. 通过 Python 最小调用验证过 `evaluation_optimization_agent` 会返回 `evaluation_report`。
5. 通过 Python 最小调用验证过 orchestration 中会把 `evaluation_optimization_agent` 纳入 `completed_agents`，并把 `evaluation_report` 追加到 artifacts。
6. 通过 Python 最小调用验证过 `evaluation_report` 会自动带出最近的本地官方 RAGAS 快照与正式指标摘要。
7. 通过 Python 最小调用验证过：重复文章链接会返回 `all_duplicates` 而不是 500；新账号下的新文章场景会返回 `created_articles`。
8. 通过 Python 最小调用验证过：`evaluation_optimization_agent` 会把最新结果写入本地评测历史，并能被历史读取函数读回。
9. 前端 `npm run build` 已再次通过，确认新增趋势卡、失败原因卡和本地恢复逻辑未破坏构建。
10. 通过 Python 最小调用验证过：服务端 Agent 状态支持写入、读取和删除。
11. 通过 Python 最小调用验证过：评测历史支持最近两次对比，并可从历史记录触发一次重跑。

## 5. 未验证或不要写大的点

以下内容不能被误写成“已经完整实现”：

1. 当前没有验证过真实远程 A2A 通信，因为系统还不是远程多智能体网络。
2. 当前 `evaluation_optimization_agent` 只是规则驱动骨架，不是完整评测平台。
3. 当前前端虽然能展示编排状态，但还没有专门的演示脚本页或答辩模式切换。
4. 当前长会话下仍可能出现上下文漂移，所以每轮结束后必须同步文档，而不能只依赖聊天窗口历史。

## 6. 新窗口推荐阅读顺序

如果是新窗口继续开发，建议按这个顺序恢复上下文：

1. [PROJECT_CHARTER_AND_SCOPE.md](PROJECT_CHARTER_AND_SCOPE.md)
2. [MILESTONES_AND_ITERATION_TRACKER.md](MILESTONES_AND_ITERATION_TRACKER.md)
3. [TECHNICAL_DECISION_RECORD.md](TECHNICAL_DECISION_RECORD.md)
4. [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md#L524)
5. [rag_qa/web/backend/routers/wechat_annotator.py](rag_qa/web/backend/routers/wechat_annotator.py#L4676)
6. [rag_qa/web/frontend/src/views/WechatAnnotatorView.vue](rag_qa/web/frontend/src/views/WechatAnnotatorView.vue#L137)

## 7. 建议的下一步

优先级建议：

1. 固化答辩/演示流程，写清楚样例输入、预期编排卡片状态、成功和 soft-fail 两种展示口径。
2. 决定是否要把当前“最近两次评测对比”扩展成更长时间窗或图表化正式评测模块。
3. 做真实登录账号联调，确认服务端连续性在多浏览器或跨窗口恢复时的口径稳定性。

## 8. 新窗口最低同步要求

如果下一轮继续修改，至少同步以下文档：

1. 稳定事实改了：更新 [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)
2. 进度变了：更新 [MILESTONES_AND_ITERATION_TRACKER.md](MILESTONES_AND_ITERATION_TRACKER.md)
3. 取舍变了：更新 [TECHNICAL_DECISION_RECORD.md](TECHNICAL_DECISION_RECORD.md)
4. 本文档里的“当前状态快照”“已验证项”“建议的下一步”至少要更新一处