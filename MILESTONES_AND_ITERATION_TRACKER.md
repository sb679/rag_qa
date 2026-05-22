# Graduation-Project 里程碑与迭代跟踪

## 1. 文档定位

这份文档用于记录“现在做到哪、卡在哪、下一步做什么”。

- 里程碑变化时更新“里程碑总览”。
- 每完成一轮明显改动或一组问题修复后，更新“最近迭代记录”。
- 不在这里重复维护稳定工程事实，事实类内容仍以 [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md) 为准。

## 2. 里程碑总览
| M4 文档治理完善 | 技术事实、运行边界、项目治理、迭代记录形成体系 | 进行中 | 当前正在补齐治理类文档 |
| M5 发布/答辩基线 | 演示路径、验证清单、风险口径稳定 | 进行中 | 已建立开发/测试/发布基线文档，并开始收敛多 Agent 演示链路与接力文档 |

## 3. 当前重点

1. 已完成：评测历史最近两次对比、最新历史记录手动重跑、按登录用户保存的服务端 Agent 连续性。
2. 收敛公众号多 Agent 的演示口径、评测口径与接力文档。
3. 持续执行文档分层同步，避免新窗口只改代码不回写文档。

## 4. 最近迭代记录

### Iteration 2026-04-30

本轮已完成：

- 修复上传接口在向量库不可用时留下对象存储半成品的问题。
- 将 Milvus 纳入一键启动链路。
- 从运行链路、配置模板、Compose 与文档中移除 MySQL/Redis 旧依赖表述。
- 重建 [.vscode/tasks.json](.vscode/tasks.json)，修复任务结构损坏问题。
- 建立 [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md) 为稳定事实主文档。
- 明确 README、运行手册、架构手册、目录导航、专题文档的分层边界。
- 新建项目章程、里程碑跟踪、技术决策记录、开发/测试/发布基线 4 份治理文档。
- 将治理文档接入 [README.md](README.md) 与 [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md) 导航。

本轮遗留：

- Node.js、npm、Docker 最低版本基线仍未在仓库中明确声明。
- 治理类文档刚建立，还未形成持续更新节奏。
- 新开窗口修改时的文档同步规则仍需固化到基线文件中。

### 当前版本总体判断

当前版本已不再处于“仅能演示单点能力”的状态，而是进入“主链路已较完整，但治理与发布口径仍在补齐”的阶段。更准确地说：

- 工程运行基线已成型。
- 知识链路基础版已成型。
- 公众号链路可运行，但仍需要口径继续收敛。
- 文档治理框架已开始成型，但仍需持续执行。

### Iteration 2026-05-08

本轮已完成：

- 将微信公众号链路从“规则驱动的自然语言入口”推进到“有限 ReAct + LLM 规划层 + 确定性工具执行”的当前产品形态。
- 为公众号 Agent 接入可见大脑状态、结构化执行计划、浏览器会话级短期记忆与账号锁定控制。
- 收敛公众号页面的执行反馈口径，使顶部完成结果条和下方阶段日志共用同一份执行摘要事实源。
- 修正 [.vscode/tasks.json](.vscode/tasks.json) 中 `Frontend: Run Vite` 的工作目录，让前端任务从正确的 `rag_qa/web/frontend` 启动。
- 修正 `Project: Verify listening ports` 任务，使其可直接输出真实监听端口与进程名，作为本地联调的可信检查入口。
- 将上述更新同步到主技术文档、专题文档、README 和开发/验证基线。

本轮遗留：

- 公众号 Agent 仍然是领域受限 Agent，尚未扩展为多目标、多工具的通用自治代理。
- 公众号页面的登录态验证仍依赖真实登录流程，浏览器共享页直接打开 `/wechat-annotator` 时仍会被守卫重定向到登录页。
- 更高级的多轮对话记忆摘要、跨轮任务连续性和更强的桌面采集可观察性仍待继续打磨。

### 当前版本总体判断

当前版本的公众号链路已经从“可运行的采集/清洗/标注面板”进入“具备有限 Agent 交互感和可见状态的垂直工作台”阶段。更准确地说：

- 公众号执行链路已可解释，而不是纯黑箱。
- 用户能感知并控制当前短期记忆与账号上下文。
- 前端任务和端口检查任务的联调口径已明显收敛。
- 但通用自治能力、登录态验证和更深的多轮记忆仍未完成。

### Iteration 2026-05-16

本轮已完成：

- 将公众号链路从“有限 ReAct 工作台”进一步推进到“中心编排器 + 采集 Agent + 治理 Agent + 评测优化 Agent”的单服务多 Agent 闭环。
- 在后端为公众号 Agent 补齐 `protocol_version`、`task_type`、`agent_route`、`trace_id` 与统一的 `orchestration` 返回对象。
- 新增知识治理 handoff 与评测优化 handoff；治理成功后会继续自动产出最小版 `evaluation_report`。
- 评测优化 Agent 已能自动挂接本地官方 RAGAS 评测快照，并把正式指标摘要合并进 `evaluation_report`。
- 已修复同步抓取路径在文章链接重复时误报 500 的问题；重复链接现在会显式返回 `all_duplicates`，新文章则会在同步结果里补齐 `created_articles`，供多 Agent 后续 handoff 使用。
- 为公众号 Agent 增加独立的治理与评测调试路由，便于分步验证与答辩演示。
- 在 WechatAnnotatorView.vue 中新增“多 Agent 编排”展示卡片，可直接看到 route、completed agents、治理结果和评测优化结果。
- WechatAnnotatorView.vue 中的评测卡片已能展示 RAGAS 均值、忠实度、上下文精确率、上下文召回率、答案相关性和快照来源。
- 前端入口和页面定位文案已从“获取公众号数据”收敛为“公众号多 Agent / 公众号知识采集与治理”，完成反馈也会显式说明停在采集、清洗、治理还是评测边界。
- 将这轮多 Agent 实现同步回主技术文档，并补齐 API 路由与流式返回事实说明。
- 新增新窗口 handoff 文档，用于记录当前状态、已验证项、下一步入口和高风险误判点。
- WechatAnnotatorView.vue 已新增“判断质量统计”“Handoff 契约诊断”“评测趋势”“结构化失败原因”四块诊断视图，把入口判断依赖、Agent 串联断点、最近评测变化和失败分类直接展示在页面中。
- `evaluation_optimization_agent` 当前会把评测摘要写入本地历史文件，并通过新接口供前端读取最近趋势，不再只能看单次 `evaluation_report`。
- Agent 面板状态和短期记忆恢复已从浏览器会话级提升到本机浏览器级，关闭标签页后仍可恢复最近指令、短期记忆和判断统计。
- 评测趋势卡现已支持最近两次历史对比，并可对最新历史记录执行一次手动重跑。
- Agent 面板状态和短期记忆现已支持按登录用户写入服务端本地状态文件，不再只依赖浏览器本地缓存。
- 公众号多 Agent 协议已经抽成后端统一注册表 [rag_qa/web/backend/routers/wechat_agent_protocol.py](rag_qa/web/backend/routers/wechat_agent_protocol.py)，并通过 `orchestration.protocol` 下发给前端，降低继续扩展 Agent 时的双端硬编码成本。
- 协议注册表中的 `summary_templates` 已开始承载阶段卡默认摘要文案，前端页面不再自己维护三段 Agent 的默认说明文本。
- 协议注册表中的 `metric_templates` 也已开始承载阶段卡指标标签文案，前端页面对“解析源 / 决策 / 风险 / RAGAS / 样本”等标签的硬编码进一步收敛。
- 协议注册表中的 `handoff_templates[*].input_rules` 也已开始承载 handoff 输入满足规则，前端页面对 `required_inputs` 的判断不再依赖字符串分支。
- 前端已新增协议展示子组件 [rag_qa/web/frontend/src/components/wechat/WechatAgentProtocolOverview.vue](rag_qa/web/frontend/src/components/wechat/WechatAgentProtocolOverview.vue)，将 handoff 契约卡与阶段卡从主视图中拆出，作为继续拆分 WechatAnnotatorView 的第一刀。
- 前端已新增最近任务列表子组件 [rag_qa/web/frontend/src/components/wechat/WechatAgentTaskList.vue](rag_qa/web/frontend/src/components/wechat/WechatAgentTaskList.vue)，将最近任务的筛选、列表和快捷操作从主视图中拆出，主视图 CSS 体积也随之回落。
- 前端已新增任务详情弹窗子组件 [rag_qa/web/frontend/src/components/wechat/WechatAgentTaskDetailDialog.vue](rag_qa/web/frontend/src/components/wechat/WechatAgentTaskDetailDialog.vue)，将任务详情、错误摘要、时间线与底部动作从主视图中拆出，并保持构建验证通过。
- 已新增后端标准库测试 [rag_qa/tests/test_wechat_agent_protocol.py](rag_qa/tests/test_wechat_agent_protocol.py)，覆盖 observe / decide / clean / orchestration 四个关键控制点，以及 governance / evaluation 调试入口的路由级返回一致性。
- 前端 Vite 拆包已从粗粒度 vendor 分组收敛为 Vue Runtime / Vue Router / Element Plus Core / Element Plus Icons / Floating UI / Element Plus 组件块细分，最新 `npm run build` 已无大块 warning。
- 已补齐 Node.js、npm、Docker、Docker Compose 的当前联调基线版本，并新增公众号多 Agent 演示脚本文档，固化成功链路、零新增链路和失败降级话术。

本轮遗留：

- `evaluation_optimization_agent` 目前仍不是完整评测平台；当前只是把本地官方 RAGAS 快照挂接进链路，并补齐了最小历史对比与手动重跑，但尚未形成独立评测任务编排和跨版本基线。
- 当前多 Agent 仍是单服务内的协议化编排，不是远程分布式 A2A 网络。
- 当前评测趋势仍以最近记录汇总为主，尚未形成长期趋势分析、自动重跑调度和图表化跨版本对比基线。
- 当前多 Agent 演示脚本已经固化，但现场仍依赖本地账号、样例链接和评测快照这些演示资产存在。
- 当前已具备按登录用户落盘的服务端会话记忆，但跨设备同步与真实多端一致性仍未验证。

### 当前版本总体判断

当前版本的公众号子系统已经从“可解释的单 Agent 工作台”进入“单服务内多 Agent 编排闭环”阶段。更准确地说：

- 采集、治理、评测三段链路已经可执行且可见。
- 后端与前端对编排状态的事实源已经统一到 `orchestration`。
- 文档开始具备跨窗口接力能力，而不是只能依赖聊天记录。
- 但评测深度、演示脚本化程度和长会话稳定性仍未完全收口。

## 5. 当前阻塞与风险

| 类型 | 内容 | 影响 | 应对建议 |
| --- | --- | --- | --- |
| 版本基线缺失 | Node.js、npm、Docker 最低版本未显式声明 | 新环境接入成本高 | 在发布基线文档中补齐 |
| 外部依赖敏感 | MinIO、Milvus、模型目录任一异常都会影响完整能力 | 启动成功不等于功能完整 | 保持运行判定分级 |
| 历史脚本过多 | 根目录实验脚本较多，易被误认为主入口 | 接手成本高 | 继续强化主入口边界说明 |
| 验证口径分散 | 自检任务、smoke test、人工联调路径尚未形成统一发布口径 | 回归效率低 | 收敛到开发/测试/发布基线文档 |
| 跨窗口信息丢失 | 新开聊天窗口修改代码时，容易只改代码不回写文档 | 版本演进不可追踪 | 固化文档同步流程，并要求每轮改动结束时更新相关文档 |
| 多 Agent 术语被写大 | 容易把当前单服务编排误表述成完整分布式多智能体平台 | 答辩与交接口径失真 | 在技术文档和决策文档中明确“协议化单服务编排”边界 |
| 评测能力被误判 | 规则型 evaluation skeleton 容易被误解为完整评测平台 | 演示预期过高 | 在 handoff 与技术文档中强调当前仅为可执行骨架 |

## 6. 下一步建议

建议优先顺序：

1. 明确 Node.js、npm、Docker 最低版本要求。
2. 固化多 Agent 演示流程，包括样例输入、预期卡片状态、失败分支解释和收尾话术。
3. 继续完善公众号 Agent 的多轮记忆摘要与任务连续性，而不是只保留最近一轮上下文。

## 7. 跨窗口同步要求

当在新窗口继续修改项目时，建议把一次修改视为一个最小迭代单元，并至少同步以下信息：

1. 如果改动影响稳定工程事实，更新 [TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)。
2. 如果改动影响当前迭代进度，更新本文件的“最近迭代记录”。
3. 如果改动包含关键取舍，更新 [TECHNICAL_DECISION_RECORD.md](TECHNICAL_DECISION_RECORD.md)。
4. 如果改动影响验证口径、发布口径或开发入口，更新 [DEVELOPMENT_TEST_RELEASE_BASELINE.md](DEVELOPMENT_TEST_RELEASE_BASELINE.md)。

## 8. 更新规则

每次迭代更新时，至少补 3 项：

1. 本轮已完成。
2. 当前遗留。
3. 下一步建议。

如果本轮涉及关键架构取舍或大改方向，额外同步更新 [TECHNICAL_DECISION_RECORD.md](TECHNICAL_DECISION_RECORD.md)。