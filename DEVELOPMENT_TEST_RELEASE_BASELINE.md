# Graduation-Project 开发、测试与发布基线

## 1. 文档定位

这份文档用于统一 3 个口径：

1. 日常开发最低要求是什么。
2. 代码或配置改动后最低验证要求是什么。

### 2.1 环境基线

- Python 环境默认使用 `rag_qa/.venv`。
- 前端开发默认使用 `rag_qa/web/frontend` 下的 Node 依赖。
- 基础设施默认以 MinIO、etcd、Milvus 为当前主依赖。
- 配置读取遵循“环境变量 > config.ini > 代码默认值”。
- 当前联调验证通过版本：Node.js `v20.17.0`、npm `10.8.2`、Docker `29.0.1`、Docker Compose `2.40.3`。
- 当前建议不要低于上述主版本线，至少在答辩机和新接手机器上保持同一大版本，避免前端构建、Compose 行为和本地代理结果出现额外漂移。

### 2.2 开发入口基线

3. [rag_qa/web/backend/main.py](rag_qa/web/backend/main.py#L1) 与 [rag_qa/web/frontend/src/main.js](rag_qa/web/frontend/src/main.js#L1)

不建议把大量 `build_*`、`analyze_*`、`generate_*`、`test_*.py` 脚本当作主开发入口。
每次在新窗口或新一轮会话里改项目时，不应只改代码而不改文档。最低同步规则如下：

| 改动类型 | 必须同步的文档 |
| 关键技术取舍或架构理由变化 | [TECHNICAL_DECISION_RECORD.md](TECHNICAL_DECISION_RECORD.md) |
| 开发入口、验证口径、发布前检查项变化 | 本文件 |
| 项目目标、范围、非目标、成功标准变化 | [PROJECT_CHARTER_AND_SCOPE.md](PROJECT_CHARTER_AND_SCOPE.md) |

1. 先改代码或配置。
2. 立刻判断这次改动影响的是“事实、进度、原因、还是验收口径”。
4. 在结束本轮修改前，补一条验证结果。

## 3. 测试基线

### 3.1 最小验证原则

改动后优先执行范围最小、最能否定当前假设的验证，不默认跑全仓库。

### 3.2 当前推荐验证入口

| 类型 | 入口 | 适用场景 |
| --- | --- | --- |
| 环境自检 | VS Code 任务 Env: Self-check (.venv) | 环境、依赖、入口导入是否正常 |
| 仓库自检 | VS Code 任务 Repo: Self-check | Compose、ignore、依赖文件基线检查 |
| 发布前自检 | VS Code 任务 Release: Preflight Check | 发布/阶段提交前串联环境、仓库、文档和关键文件检查 |
| 后端联调 | VS Code 任务 Backend: Run Uvicorn (.venv) | 收敛版热重载后端行为验证 |
| 后端稳定联调 | VS Code 任务 Backend: Run Uvicorn Stable (.venv) | 不启用热重载的稳定后端验证 |
| 前端联调 | VS Code 任务 Frontend: Run Vite | 前端页面与代理联调；任务当前从 `rag_qa/web/frontend` 目录启动，若 5173 被占用会自动顺延到下一个可用端口 |
| 稳定联调总入口 | VS Code 任务 Project: Run stable local app | 并行拉起稳定版后端与前端，用于登录、SSE、页面状态等本地联调 |
| Smoke 测试 | [rag_qa/tests/test_smoke.py](rag_qa/tests/test_smoke.py#L1) | 配置与最小常量基线 |
| 策略回归 | [rag_qa/tests/test_strategy_selector.py](rag_qa/tests/test_strategy_selector.py#L1) | 策略分类相关改动 |

补充说明：

- 联调公众号 Agent 页面时，可直接使用 `Project: Verify listening ports` 核对 8000、5173、5174、5175、19530 等端口当前由哪个进程占用，不需要再手工拼接额外命令。
- 若改动落在 WechatAnnotatorView 或公众号 Agent 的完成反馈区，除了检查静态错误外，至少应确认“顶部完成结果条”和“阶段日志”引用的是同一份执行事实，不允许一个区域展示推断文案、另一个区域展示真实执行明细而互相冲突。

### 3.3 改动类型与最低验证要求

| 改动类型 | 最低要求 |
| --- | --- |
| 仅文档改动 | 检查文档导航与内容边界是否一致 |
| 配置映射 / 启动编排 | 至少跑 Env: Self-check (.venv) 或 Repo: Self-check |
| 后端接口 / 服务逻辑 | 至少启动后端并验证健康检查或受影响接口 |
| 前端页面 / 代理配置 | 至少启动前端并验证页面渲染或代理目标 |
| 检索 / 策略相关 | 至少跑对应 unittest 或受影响链路 smoke 验证 |
| 文档治理 / 分层调整 | 至少检查 README、主技术文档、治理文档之间的导航与边界是否一致 |

## 4. 发布或阶段提交基线

### 4.1 发布前最低检查项

可执行统一入口：

- 优先运行 VS Code 任务 Release: Preflight Check，或直接执行 [scripts/release_precheck.ps1](scripts/release_precheck.ps1#L1)。
- 这条检查会串联环境自检、仓库自检、治理/入口/事实文档存在性检查，以及关键运行文件存在性检查。
- 脚本结尾会输出 `PASS / WARN / MANUAL` 汇总，便于快速区分“自动检查已通过项”“非阻断提醒”和“仍需人工确认的演示动作”。


- [ ] 根目录 README 与主技术文档未与当前运行事实冲突。
- [ ] 4 份治理文档中的当前阶段信息未明显过期。

### 4.3 演示验收清单

推荐同时参考 [WECHAT_MULTI_AGENT_DEMO_SCRIPT.md](WECHAT_MULTI_AGENT_DEMO_SCRIPT.md)，该文档已经把公众号多 Agent 的成功链路、零新增链路和失败降级话术收敛成可直接照读的演示脚本。

演示前不只检查“服务是否启动”，还要明确本次演示走哪条链路、失败时如何降级、现场如何快速确认状态。最低建议按下面清单执行：

#### A. 演示入口确认

- [ ] 已明确本次演示入口：主 Web 问答、知识库管理、公众号标注，或其他专项链路。
- [ ] 已明确演示使用的账号、角色和最小进入路径。
- [ ] 已确认浏览器打开地址与当前前端实际端口一致。

#### B. 演示链路确认

- [ ] 若演示主 Web 问答：至少提前跑通一次“登录 -> 提问 -> 返回回答”。
- [ ] 若演示知识库链路：至少提前跑通一次“进入知识库页面 -> 查看列表或统计 -> 触发一次可见操作”。
- [ ] 若演示公众号标注链路：至少提前跑通一次“进入标注页面 -> 加载样本 -> 提交或保存一次结果”。
- [ ] 已明确本次演示的主链路和备选链路，不临场临时决定。

#### C. 基础设施确认

- [ ] 若演示依赖知识检索或知识库统计，Milvus 已正常可用。
- [ ] 若演示依赖文件上传、对象访问或文件链路，MinIO 已正常可用。
- [ ] 后端健康检查已确认可访问，且当前前端代理目标指向正确后端端口。

#### D. 失败降级准备

- [ ] 已准备至少一个可替代的演示路径，例如从完整知识检索降级为登录 + 页面进入 + 公众号标注。
- [ ] 已知道当前启动日志位置，出现异常时可优先查看 `rag_qa/logs/launcher/launcher-latest.log` 或后端输出。
- [ ] 已确认如果某条链路现场失败，优先切换演示路径而不是现场排大故障。

#### E. 演示结果留痕

- [ ] 演示前记录本次使用的端口、入口和关键依赖状态。
- [ ] 演示后如发现问题，至少补一条到当前迭代或相关文档，不把现场问题留在口头结论里。

### 4.2 演示前最低检查项

- [ ] 登录或最小进入路径可用。
- [ ] 至少有一条可演示的知识链路或公众号链路。
- [ ] 若需要演示知识检索，Milvus 已正常可用。
- [ ] 若需要演示文件链路，MinIO 已正常可用。

## 5. 当前已知缺口

- 当前多 Agent 仍是单服务内协议化编排，不包含远程 Agent 注册、发现和跨服务调度；答辩或对外交付时不要写大成“已完成分布式 A2A 平台”。
- `evaluation_optimization_agent` 已支持历史趋势最小版，但仍没有独立重跑任务编排、长期趋势看板和跨版本对比基线，不应表述为完整评测平台。
- WechatAnnotator 页面当前已把 Agent 面板状态和判断统计升级为 `localStorage` 级恢复，但跨设备、多用户同步和服务端会话记忆仍未实现。
- 当前演示脚本已经固化，但仍依赖本地账号、历史文章和官方 RAGAS 快照这些现场资产存在；演示前仍需要按本文件第 4 节逐项确认。


## 6. 维护规则

下列情况出现时，应同步更新本文件：

1. 启动方式或验证入口发生变化。
2. 新增或移除关键测试入口。
3. 发布前检查口径发生变化。
4. 新增稳定使用的开发任务或校验脚本。

## 7. 新窗口协作规则

如果你在新窗口继续改这个项目，建议把下面这段作为固定工作流：

1. 先读 [README.md](README.md)、[TECHNICAL_DOCUMENTATION.md](TECHNICAL_DOCUMENTATION.md)、[MILESTONES_AND_ITERATION_TRACKER.md](MILESTONES_AND_ITERATION_TRACKER.md)。
2. 做改动前，先判断会影响哪一类文档。
3. 做改动后，在同一轮里补齐对应文档更新，不把文档同步留到“以后再说”。
4. 至少记录一条验证结果，哪怕只是“自检任务通过”或“仅文档改动，无可执行验证”。

可直接复制给新窗口的要求模板：

“请在完成代码修改后，同步检查是否需要更新以下文档：
- 稳定工程事实：TECHNICAL_DOCUMENTATION.md
- 当前迭代进展：MILESTONES_AND_ITERATION_TRACKER.md
- 关键技术决策：TECHNICAL_DECISION_RECORD.md
- 开发/测试/发布口径：DEVELOPMENT_TEST_RELEASE_BASELINE.md
- 项目范围与目标：PROJECT_CHARTER_AND_SCOPE.md

如果本轮改动影响其中任一项，请直接更新对应文档，不要只改代码。”