<template>
  <div class="wechat-annotator-page">
    <div class="page-shell" :class="{ 'agent-only': !showReviewWorkspace, 'review-only': showReviewWorkspace }">
      <aside v-if="!showReviewWorkspace" class="sidebar card-glass">
        <div class="sidebar-header">
          <div>
            <div class="kicker">Wechat Multi-Agent</div>
            <h1>公众号知识采集与治理</h1>
            <p>通过自然语言统一执行文章入口识别、知识采集、治理检查、评测汇总和标注衔接。</p>
          </div>
          <el-tag type="success" effect="light">本地文件</el-tag>
        </div>

        <div class="workspace-overview-card">
          <div class="workspace-overview-head">
            <div>
              <div class="agent-summary-title">多 Agent 主视图</div>
              <div class="agent-summary-text">页面只保留三块核心信息：当前输入、三个 Agent 的阶段状态、必要时才展开的人工介入工具。</div>
            </div>
            <div class="workspace-overview-actions">
              <el-button size="small" plain :loading="localAccountOverviewLoading" @click="loadLocalAccountOverview">刷新账号</el-button>
              <el-button size="small" text @click="showAdvancedTools = !showAdvancedTools">{{ showAdvancedTools ? '收起调试区' : '展开调试区' }}</el-button>
            </div>
          </div>
          <div class="agent-summary-stats">
            <span>本地账号 {{ localAccountOverviewStats.accountCount }} 个</span>
            <span>历史文章 {{ localAccountOverviewStats.articleCount }} 篇</span>
            <span>{{ agentBrainState.source === 'llm' ? '当前由 LLM 判断' : '当前为规则回退' }}</span>
            <span>{{ agentRunning ? '当前有执行任务' : '等待新指令' }}</span>
          </div>
          <div v-if="compactLocalAccountOverview.length" class="workspace-overview-account-row">
            <button
              v-for="item in compactLocalAccountOverview"
              :key="`overview:${item.overview_key || `${item.account_id}:${getOverviewDisplayName(item)}`}`"
              type="button"
              class="workspace-overview-account-chip"
              @click="openLocalAccountOverviewItem(item)"
            >
              <span class="workspace-overview-account-name">{{ getOverviewDisplayName(item) }}</span>
              <span class="workspace-overview-account-meta">{{ item.account_id }} · {{ item.existing_article_count || 0 }} 篇</span>
            </button>
          </div>
          <div v-else class="local-account-overview-collapsed-tip">当前还没有可展示的本地账号。只要抓取过一次公众号，后续会自动沉淀到这里。</div>
        </div>

        <div v-if="brainDiagnosticStats.visible" class="brain-stats-card">
          <div class="brain-stats-head">
            <div>
              <div class="agent-summary-title">判断质量统计</div>
              <div class="review-entry-text">只统计当前浏览器会话内最近几次指令，直接看出当前是否还在依赖最简规则方案。</div>
            </div>
            <el-button size="small" text @click="clearBrainDiagnosticHistory">清空统计</el-button>
          </div>
          <div class="brain-stats-grid">
            <article class="brain-stats-metric-card" data-tone="success">
              <div class="brain-stats-metric-label">模型主判</div>
              <div class="brain-stats-metric-value">{{ brainDiagnosticStats.llmWins }}</div>
              <div class="brain-stats-metric-note">最近 {{ brainDiagnosticStats.total }} 次里由模型直接完成判断</div>
            </article>
            <article class="brain-stats-metric-card" :data-tone="brainDiagnosticStats.ruleFallbacks ? 'warning' : 'idle'">
              <div class="brain-stats-metric-label">规则回退</div>
              <div class="brain-stats-metric-value">{{ brainDiagnosticStats.ruleFallbacks }}</div>
              <div class="brain-stats-metric-note">包含未配置、请求失败、空响应和强制规则继续</div>
            </article>
            <article class="brain-stats-metric-card" :data-tone="brainDiagnosticStats.highDependencyRuns ? 'danger' : 'success'">
              <div class="brain-stats-metric-label">高依赖轮次</div>
              <div class="brain-stats-metric-value">{{ brainDiagnosticStats.highDependencyRuns }}</div>
              <div class="brain-stats-metric-note">最简方案依赖等级为“高”的轮次</div>
            </article>
          </div>
          <div v-if="brainDiagnosticStats.reasonItems.length" class="brain-stats-reason-row">
            <span v-for="item in brainDiagnosticStats.reasonItems" :key="`brain-reason:${item.label}`" class="brain-stats-reason-chip">
              {{ item.label }} {{ item.count }} 次
            </span>
          </div>
        </div>

        <div class="evaluation-trend-card">
          <div class="evaluation-trend-head">
            <div>
              <div class="agent-summary-title">评测趋势</div>
              <div class="review-entry-text">把最近几次评测结果压成趋势视图，避免每次都只看单次 evaluation_report。</div>
            </div>
            <div class="evaluation-trend-actions">
              <el-button size="small" plain :loading="evaluationTrendLoading" @click="loadEvaluationTrendHistory">刷新趋势</el-button>
              <el-button size="small" plain type="success" :loading="evaluationRerunHistoryId === (evaluationTrendSummary.latest?.history_id || '')" :disabled="!evaluationTrendSummary.latest?.history_id" @click="rerunLatestEvaluationHistory">重跑最新评测</el-button>
            </div>
          </div>
          <div v-if="evaluationTrendSummary.visible" class="evaluation-trend-grid">
            <article class="evaluation-trend-metric-card" data-tone="success">
              <div class="evaluation-trend-metric-label">最近就绪度</div>
              <div class="evaluation-trend-metric-value">{{ evaluationTrendSummary.latest?.readiness || 'unknown' }}</div>
              <div class="evaluation-trend-metric-note">最新一轮质量/覆盖率/RAGAS 汇总结果</div>
            </article>
            <article class="evaluation-trend-metric-card" :data-tone="evaluationTrendSummary.latest?.ragas_average >= 0.8 ? 'success' : (evaluationTrendSummary.latest?.ragas_average ? 'warning' : 'idle')">
              <div class="evaluation-trend-metric-label">最新 RAGAS</div>
              <div class="evaluation-trend-metric-value">{{ evaluationTrendSummary.latest?.ragas_average !== null && evaluationTrendSummary.latest?.ragas_average !== undefined ? formatAgentMetricScore(evaluationTrendSummary.latest?.ragas_average) : '--' }}</div>
              <div class="evaluation-trend-metric-note">近 {{ evaluationTrendSummary.total }} 次评测平均值 {{ evaluationTrendSummary.avgRagas !== null ? formatAgentMetricScore(evaluationTrendSummary.avgRagas) : '--' }}</div>
            </article>
            <article class="evaluation-trend-metric-card" :data-tone="evaluationTrendSummary.delta === null ? 'idle' : (evaluationTrendSummary.delta >= 0 ? 'success' : 'danger')">
              <div class="evaluation-trend-metric-label">趋势变化</div>
              <div class="evaluation-trend-metric-value">{{ evaluationTrendSummary.delta === null ? '--' : `${evaluationTrendSummary.delta >= 0 ? '+' : ''}${formatAgentMetricScore(evaluationTrendSummary.delta)}` }}</div>
              <div class="evaluation-trend-metric-note">与上一轮相比的 RAGAS 变化</div>
            </article>
          </div>
          <div v-if="evaluationCompareSummary.visible" class="evaluation-compare-row">
            <span>对比账号 {{ evaluationCompareSummary.latest?.account_id || 'unknown' }}</span>
            <span v-if="evaluationCompareSummary.delta?.quality_score !== null && evaluationCompareSummary.delta?.quality_score !== undefined">质量变化 {{ evaluationCompareSummary.delta.quality_score >= 0 ? '+' : '' }}{{ evaluationCompareSummary.delta.quality_score }}</span>
            <span v-if="evaluationCompareSummary.delta?.coverage_score !== null && evaluationCompareSummary.delta?.coverage_score !== undefined">覆盖变化 {{ evaluationCompareSummary.delta.coverage_score >= 0 ? '+' : '' }}{{ evaluationCompareSummary.delta.coverage_score }}</span>
            <span v-if="evaluationCompareSummary.delta?.ragas_average !== null && evaluationCompareSummary.delta?.ragas_average !== undefined">RAGAS 变化 {{ evaluationCompareSummary.delta.ragas_average >= 0 ? '+' : '' }}{{ formatAgentMetricScore(evaluationCompareSummary.delta.ragas_average) }}</span>
          </div>
          <div v-if="evaluationTrendChart.visible" class="evaluation-trend-chart-card">
            <div class="evaluation-trend-chart-head">
              <div class="evaluation-trend-chart-title">长时间窗走势</div>
              <div class="evaluation-trend-chart-window">{{ evaluationTrendChart.windowLabel }}</div>
            </div>
            <svg class="evaluation-trend-chart" viewBox="0 0 480 136" preserveAspectRatio="none" aria-label="RAGAS 趋势图">
              <line
                v-for="tick in evaluationTrendChart.yTicks"
                :key="`eval-tick:${tick.value}`"
                class="evaluation-trend-chart-grid-line"
                :x1="tick.x1"
                :y1="tick.y"
                :x2="tick.x2"
                :y2="tick.y"
              />
              <polyline
                v-if="evaluationTrendChart.linePoints"
                class="evaluation-trend-chart-line"
                :points="evaluationTrendChart.linePoints"
              />
              <circle
                v-for="point in evaluationTrendChart.points"
                :key="`eval-point:${point.key}`"
                class="evaluation-trend-chart-point"
                :cx="point.x"
                :cy="point.y"
                :r="point.radius"
                :data-tone="point.tone"
              />
            </svg>
            <div class="evaluation-trend-chart-labels">
              <span>{{ evaluationTrendChart.startLabel }}</span>
              <span>{{ evaluationTrendChart.endLabel }}</span>
            </div>
            <div class="evaluation-trend-chart-caption">
              近 {{ evaluationTrendChart.sampleCount }} 条有效评测记录。最高 {{ evaluationTrendChart.maxLabel }}，最低 {{ evaluationTrendChart.minLabel }}。
            </div>
          </div>
          <div v-if="evaluationTrendSummary.visible" class="evaluation-trend-list">
            <article v-for="item in evaluationTrendSummary.items" :key="`eval-trend:${item.recorded_at}:${item.account_id}:${item.summary}`" class="evaluation-trend-item">
              <div class="evaluation-trend-item-head">
                <div class="evaluation-trend-item-title">{{ item.account_id || 'unknown_account' }}</div>
                <div class="evaluation-trend-item-time">{{ formatAgentTaskTime(item.recorded_at) || item.recorded_at }}</div>
              </div>
              <div class="evaluation-trend-item-meta">
                <span>就绪度 {{ item.readiness || 'unknown' }}</span>
                <span>质量 {{ item.quality_score || 0 }}</span>
                <span>覆盖 {{ item.coverage_score || 0 }}</span>
                <span v-if="item.ragas_average !== null && item.ragas_average !== undefined">RAGAS {{ formatAgentMetricScore(item.ragas_average) }}</span>
              </div>
              <div v-if="item.snapshot_label || item.summary" class="evaluation-trend-item-summary">{{ item.snapshot_label || item.summary }}</div>
            </article>
          </div>
          <div v-else class="local-account-overview-collapsed-tip">当前还没有评测历史。只要治理链路后续成功进入 evaluation_optimization_agent，这里就会开始累积趋势。</div>
        </div>

        <WechatAgentProtocolOverview
          :handoff-contract-cards="handoffContractCards"
          :agent-stage-cards="agentStageCards"
        />

        <div class="crawl-panel card-glass">
          <div class="crawl-panel-header compact">
            <div>
              <div class="crawl-panel-title">统一指令</div>
              <div class="crawl-panel-tip">默认只输入一句话。账号总览、人工匹配和桌面采集都下沉到折叠区，优先把主视图留给多 Agent 状态对比。</div>
            </div>
            <div class="crawl-panel-inline-meta">
              <span v-if="selectedAccountDisplayName || crawlAccountId">当前账号：{{ selectedAccountDisplayName || crawlAccountId }}</span>
              <span v-if="selectedHistoryUrl">已挂靠历史页</span>
            </div>
          </div>
          <el-input
            v-model="agentCommand"
            type="textarea"
            :rows="4"
            resize="none"
            placeholder="请输入公众号采集执行指令，例如：匹配本地账号 武术协会；抓取这条公众号链接并归到当前账号 https://mp.weixin.qq.com/mp/profile_ext?...；或清洗并入库当前账号。这里不是普通闲聊窗口。"
          />
          <div v-if="agentRestoreNotice.visible" class="agent-restore-banner" :data-tone="agentRestoreNotice.tone || 'info'">
            <div class="agent-restore-banner-title">{{ agentRestoreNotice.title }}</div>
            <div v-if="agentRestoreNotice.message" class="agent-restore-banner-message">{{ agentRestoreNotice.message }}</div>
            <div v-if="agentRestoreNotice.command" class="agent-restore-banner-command">{{ agentRestoreNotice.command }}</div>
            <div class="agent-restore-banner-actions">
              <el-button v-if="agentSessionMemory.taskMemory?.command" size="small" @click="restorePreviousAgentCommand">恢复最近任务指令</el-button>
              <el-button size="small" text @click="dismissAgentRestoreNotice">关闭</el-button>
            </div>
          </div>
          <div v-if="agentBrainState.visible" class="agent-brain-banner" :data-tone="agentBrainState.tone || 'info'">
            <div class="agent-brain-banner-title">{{ agentBrainState.title }}</div>
            <div class="agent-brain-banner-meta">
              <span>解析源：{{ agentBrainState.sourceLabel }}</span>
              <span>意图：{{ agentBrainState.intentLabel }}</span>
            </div>
            <div v-if="agentBrainState.message" class="agent-restore-banner-message">{{ agentBrainState.message }}</div>
            <div v-if="agentBrainState.diagnostics.visible" class="agent-brain-diagnostics">
              <div class="agent-brain-diagnostics-title">入口判断诊断</div>
              <div class="agent-brain-diagnostics-summary">{{ agentBrainState.diagnostics.summary }}</div>
              <div v-if="agentBrainState.diagnostics.chips.length" class="agent-brain-diagnostics-chips">
                <span v-for="item in agentBrainState.diagnostics.chips" :key="`${agentBrainState.intent || 'brain'}:${item}`">{{ item }}</span>
              </div>
              <div v-if="agentBrainState.diagnostics.cards.length" class="agent-brain-diagnostics-grid">
                <article
                  v-for="item in agentBrainState.diagnostics.cards"
                  :key="`${agentBrainState.intent || 'brain'}:${item.title}`"
                  class="agent-brain-diagnostics-card"
                  :data-tone="item.tone"
                >
                  <div class="agent-brain-diagnostics-card-title">{{ item.title }}</div>
                  <div class="agent-brain-diagnostics-card-value">{{ item.value }}</div>
                  <div class="agent-brain-diagnostics-card-note">{{ item.note }}</div>
                </article>
              </div>
              <div v-if="agentBrainState.diagnostics.detail" class="agent-brain-diagnostics-detail">{{ agentBrainState.diagnostics.detail }}</div>
              <div v-if="agentBrainState.diagnostics.suggestions.length" class="agent-brain-diagnostics-suggestions">
                <div class="agent-brain-diagnostics-suggestions-title">强化建议</div>
                <div v-for="item in agentBrainState.diagnostics.suggestions" :key="`${agentBrainState.intent || 'brain'}:${item}`" class="agent-brain-diagnostics-suggestion">{{ item }}</div>
              </div>
            </div>
            <div v-if="agentBrainState.planSteps?.length" class="agent-brain-plan">
              <div class="agent-brain-plan-title">{{ agentBrainState.planTitle || '待执行计划' }}</div>
              <div v-for="(step, index) in agentBrainState.planSteps" :key="`${agentBrainState.intent || 'plan'}:${index}`" class="agent-brain-plan-step">
                {{ index + 1 }}. {{ step }}
              </div>
            </div>
          </div>
          <details v-if="agentOrchestration?.task?.taskId" class="agent-inline-details">
            <summary>
              <span>查看编排细节</span>
              <span class="agent-advanced-summary">route、当前 Agent、治理与评测摘要都挂在这里</span>
            </summary>
            <div class="agent-inline-details-body">
              <div class="agent-orchestration-card" :data-status="agentOrchestration.task.status || 'unknown'">
                <div class="agent-orchestration-head">
                  <div>
                    <div class="agent-orchestration-kicker">多 Agent 编排</div>
                    <div class="agent-orchestration-title">{{ agentOrchestration.task.goal || '知识任务编排' }}</div>
                  </div>
                  <div class="agent-orchestration-status">{{ formatAgentOrchestrationStatus(agentOrchestration.task.status) }}</div>
                </div>
                <div class="agent-orchestration-meta">
                  <span>当前 Agent：{{ formatAgentRoleName(agentOrchestration.task.currentAgent) }}</span>
                  <span v-if="agentOrchestration.nextAgent">下一跳：{{ formatAgentRoleName(agentOrchestration.nextAgent) }}</span>
                  <span>Trace：{{ agentOrchestration.task.traceId }}</span>
                </div>
                <div v-if="agentOrchestration.route.length" class="agent-orchestration-route">
                  <span v-for="item in agentOrchestration.route" :key="`route:${item}`" class="agent-orchestration-chip">{{ formatAgentRoleName(item) }}</span>
                </div>
                <div v-if="agentOrchestration.completedAgents.length" class="agent-orchestration-meta">
                  <span>已完成：{{ agentOrchestration.completedAgents.map(formatAgentRoleName).join(' -> ') }}</span>
                </div>
                <div v-if="agentOrchestration.review?.summary" class="agent-orchestration-summary">{{ agentOrchestration.review.summary }}</div>
                <div v-if="agentOrchestration.governance" class="agent-orchestration-governance">
                  <div class="agent-orchestration-section-title">治理结果</div>
                  <div class="agent-orchestration-meta">
                    <span>状态：{{ formatAgentOrchestrationStatus(agentOrchestration.governance.status) }}</span>
                    <span v-if="agentOrchestration.governance.riskLevel">风险：{{ agentOrchestration.governance.riskLevel }}</span>
                  </div>
                  <div v-if="agentOrchestration.governance.summary" class="agent-orchestration-summary">{{ agentOrchestration.governance.summary }}</div>
                </div>
                <div v-if="agentOrchestration.evaluation" class="agent-orchestration-governance">
                  <div class="agent-orchestration-section-title">评测优化结果</div>
                  <div class="agent-orchestration-meta">
                    <span v-if="agentOrchestration.evaluation.readiness">就绪度：{{ agentOrchestration.evaluation.readiness }}</span>
                    <span v-if="agentOrchestration.evaluation.qualityScore">质量分：{{ agentOrchestration.evaluation.qualityScore }}</span>
                    <span v-if="agentOrchestration.evaluation.coverageScore">覆盖率：{{ agentOrchestration.evaluation.coverageScore }}</span>
                  </div>
                  <div v-if="agentOrchestration.evaluation.ragasAverage !== null || agentOrchestration.evaluation.sampleCount" class="agent-orchestration-meta">
                    <span v-if="agentOrchestration.evaluation.ragasAverage !== null">RAGAS 均值：{{ formatAgentMetricScore(agentOrchestration.evaluation.ragasAverage) }}</span>
                    <span v-if="agentOrchestration.evaluation.sampleCount">样本数：{{ agentOrchestration.evaluation.sampleCount }}</span>
                  </div>
                  <div v-if="agentOrchestration.evaluation.faithfulness !== null || agentOrchestration.evaluation.contextPrecision !== null || agentOrchestration.evaluation.contextRecall !== null || agentOrchestration.evaluation.responseRelevancy !== null" class="agent-orchestration-meta">
                    <span v-if="agentOrchestration.evaluation.faithfulness !== null">忠实度：{{ formatAgentMetricScore(agentOrchestration.evaluation.faithfulness) }}</span>
                    <span v-if="agentOrchestration.evaluation.contextPrecision !== null">上下文精确率：{{ formatAgentMetricScore(agentOrchestration.evaluation.contextPrecision) }}</span>
                    <span v-if="agentOrchestration.evaluation.contextRecall !== null">上下文召回率：{{ formatAgentMetricScore(agentOrchestration.evaluation.contextRecall) }}</span>
                    <span v-if="agentOrchestration.evaluation.responseRelevancy !== null">答案相关性：{{ formatAgentMetricScore(agentOrchestration.evaluation.responseRelevancy) }}</span>
                  </div>
                  <div v-if="agentOrchestration.evaluation.snapshotLabel" class="agent-orchestration-summary">评测快照：{{ agentOrchestration.evaluation.snapshotLabel }}</div>
                  <div v-if="agentOrchestration.evaluation.summary" class="agent-orchestration-summary">{{ agentOrchestration.evaluation.summary }}</div>
                </div>
              </div>
            </div>
          </details>
          <div v-if="agentMemorySummary.length" class="agent-memory-banner" :data-locked="agentSessionMemory.accountLocked ? 'true' : 'false'">
            <div class="agent-memory-banner-header">
              <div class="agent-memory-banner-title">当前短期记忆</div>
              <div v-if="agentSessionMemory.accountLocked" class="agent-memory-lock-badge">账号已锁定</div>
            </div>
            <div v-for="(item, index) in agentMemorySummary" :key="`memory:${index}`" class="agent-memory-banner-item">{{ item }}</div>
            <div class="agent-memory-banner-actions">
              <el-button size="small" text @click="toggleAgentAccountLock">{{ agentSessionMemory.accountLocked ? '解除账号锁定' : '锁定当前账号上下文' }}</el-button>
              <el-button size="small" text @click="clearAgentSessionMemory">清空短期记忆</el-button>
            </div>
          </div>
          <div class="crawl-actions">
            <el-button type="primary" @click="runAgentCommand">执行指令</el-button>
            <el-button v-if="agentRunning" type="danger" plain @click="stopAgentCommand">{{ agentActiveRunCount > 1 ? '停止最近任务' : '停止执行' }}</el-button>
            <el-button @click="runQuickIngest">清洗并入库当前账号</el-button>
            <el-button @click="openAnnotatorEntry">进入标注工作台</el-button>
            <el-button plain :disabled="!agentLogs.length && !agentStatusText && !agentActionFeedback && !agentTaskCard && !agentTaskList.length" @click="clearAgentPanelState">清空记录</el-button>
          </div>
          <details class="agent-advanced-panel" :open="showAdvancedTools" @toggle="showAdvancedTools = $event.target.open">
            <summary>
              <span>展开高级调试与人工介入</span>
              <span class="agent-advanced-summary">账号匹配、桌面采集与调参，仅在直抓不足或调试时使用</span>
            </summary>
            <div class="agent-advanced-content">
              <div class="local-account-overview-card compact">
                <div class="local-account-overview-head">
                  <div>
                    <div class="agent-summary-title">本地账号总览</div>
                    <div class="review-entry-text">账号列表下沉到这里，避免占用主视图区。</div>
                  </div>
                  <div class="local-account-overview-head-actions">
                    <el-button size="small" text @click="toggleLocalAccountOverview">
                      {{ showLocalAccountOverview ? '收起' : '展开' }}
                    </el-button>
                  </div>
                </div>
                <div v-if="!showLocalAccountOverview" class="local-account-overview-collapsed-tip">
                  当前共 {{ localAccountOverviewStats.accountCount }} 个账号，{{ localAccountOverviewStats.articleCount }} 篇历史文章。
                </div>
                <template v-else>
                  <div class="local-account-overview-filters">
                    <button
                      type="button"
                      class="local-account-filter-chip"
                      :data-active="localAccountOverviewFilter === 'all'"
                      @click="localAccountOverviewFilter = 'all'"
                    >全部</button>
                    <button
                      type="button"
                      class="local-account-filter-chip"
                      :data-active="localAccountOverviewFilter === 'with-history'"
                      @click="localAccountOverviewFilter = 'with-history'"
                    >有历史页</button>
                    <button
                      type="button"
                      class="local-account-filter-chip"
                      :data-active="localAccountOverviewFilter === 'recent'"
                      @click="localAccountOverviewFilter = 'recent'"
                    >最近新增</button>
                    <button
                      type="button"
                      class="local-account-filter-chip"
                      :data-active="localAccountOverviewFilter === 'missing-history'"
                      @click="localAccountOverviewFilter = 'missing-history'"
                    >待补历史页</button>
                  </div>
                  <div v-if="filteredLocalAccountOverview.length" class="local-account-overview-list compact">
                    <button
                      v-for="item in filteredLocalAccountOverview"
                      :key="`advanced:${item.overview_key || `${item.account_id}:${getOverviewDisplayName(item)}`}`"
                      type="button"
                      class="local-account-overview-item compact"
                      @click="openLocalAccountOverviewItem(item)"
                    >
                      <div class="local-account-overview-title-row">
                        <span class="local-account-overview-name">{{ getOverviewDisplayName(item) }}</span>
                        <div class="local-account-overview-actions">
                          <span class="local-account-overview-badge" :data-tone="item.has_history_url ? 'success' : 'warning'">
                            {{ item.has_history_url ? '有历史页' : '无历史页' }}
                          </span>
                          <el-button
                            size="small"
                            text
                            :disabled="!item.has_history_url"
                            @click="copyHistoryUrl(item, $event)"
                          >复制历史页</el-button>
                        </div>
                      </div>
                      <div class="local-account-overview-meta">{{ item.account_id }} · 已抓取 {{ item.existing_article_count || 0 }} 篇</div>
                    </button>
                  </div>
                  <div v-else class="crawl-panel-tip">当前还没有可展示的本地账号。只要抓取过一次公众号，后续会自动沉淀到这里。</div>
                </template>
              </div>
              <div class="crawl-panel-title">账号匹配与本地提示</div>
              <el-input v-model="crawlAccountId" placeholder="账号ID（示例：my_wechat_account）" clearable />
              <div class="crawl-account-search-row">
                <el-input
                  v-model="crawlAccountQuery"
                  placeholder="匹配本地公众号名称或账号ID，例如：武术协会"
                  clearable
                  @keyup.enter="searchWechatAccounts"
                />
                <el-button :loading="accountSearchLoading" @click="searchWechatAccounts">匹配本地账号</el-button>
                <el-button plain :loading="accountSearchLoading" @click="searchWechatAccounts(true)">查看全部</el-button>
              </div>
              <div
                v-if="accountSearchFeedback"
                class="desktop-action-feedback"
                :data-tone="accountSearchFeedback.type"
              >
                <div class="desktop-action-feedback-title">{{ accountSearchFeedback.title }}</div>
                <div v-if="accountSearchFeedback.message" class="desktop-action-feedback-message">{{ accountSearchFeedback.message }}</div>
              </div>
              <div v-if="accountCandidates.length" class="account-candidate-list">
                <button
                  v-for="item in accountCandidates"
                  :key="`${item.account_id}:${item.history_urls?.[0] || 'no-history'}`"
                  type="button"
                  class="account-candidate"
                  @click="applyAccountCandidate(item)"
                >
                  <span class="account-candidate-name">{{ item.preferred_name || item.display_name || item.account_id }}</span>
                  <span class="account-candidate-meta">{{ item.account_id }} · 历史页 {{ item.has_history_url ? '已配置' : '未配置' }} · 已抓取 {{ item.existing_article_count || 0 }} 篇 · 匹配分 {{ item.match_score || 0 }}</span>
                  <span v-if="item.possible_names?.length" class="account-candidate-alias">可能的公众号名：{{ item.possible_names.join(' / ') }}</span>
                  <span v-if="item.sample_titles?.length" class="account-candidate-alias">相关文章：{{ item.sample_titles.join('；') }}</span>
                </button>
              </div>
              <div v-if="selectedHistoryUrl" class="crawl-panel-tip">本地记录的历史页：{{ selectedHistoryUrl }}</div>

              <div class="mobile-capture-panel">
                <div class="crawl-panel-title">桌面端自动采集</div>
                <div class="crawl-panel-tip">只在 Agent 无法直抓时再用。这里保留给调试或特殊公众号场景，不建议作为默认入口。</div>
                <div class="mobile-grid two">
                  <el-input v-model="desktopOperatorId" placeholder="operator_id，例如：zhangsan" clearable @change="refreshDesktopProfiles" />
                  <el-select v-model="desktopProfileName" clearable filterable placeholder="选择桌面 profile" @change="applyDesktopProfile">
                    <el-option v-for="item in desktopProfiles" :key="item.profile_name" :label="item.profile_name" :value="item.profile_name">
                      <span>{{ item.profile_name }}</span>
                      <span class="mobile-option-meta">{{ item.account_id || 'no-account' }} · {{ item.machine_name || 'desktop' }}</span>
                    </el-option>
                  </el-select>
                </div>
                <div class="mobile-grid three">
                  <el-input v-model="desktopAccountId" placeholder="采集归属账号ID" clearable />
                  <el-input v-model="desktopDisplayName" placeholder="显示名称（可选）" clearable />
                  <el-input v-model="desktopWechatPath" placeholder="WeChat.exe 路径（可选）" clearable />
                </div>
                <div class="mobile-grid two">
                  <el-input v-model="desktopSearchQuery" placeholder="公众号搜索词，例如：矿业工程学院" clearable />
                  <el-input v-model="desktopArticleTitle" placeholder="文章标题或片段，例如：2025 届毕业典礼" clearable />
                </div>
                <div class="mobile-grid two">
                  <el-input v-model="desktopSourceUrl" placeholder="文章链接，仅写入元数据，可选" clearable />
                  <el-input v-model="desktopWindowTitleRe" placeholder="窗口标题正则，默认 .*微信.*" clearable />
                </div>
                <div class="mobile-grid four compact">
                  <el-input-number v-model="desktopCaptureSteps" :min="1" :max="30" controls-position="right" />
                  <el-input-number v-model="desktopWaitSec" :min="0" :max="10" :step="0.5" controls-position="right" />
                  <el-input-number v-model="desktopSettleDelaySec" :min="0" :max="10" :step="0.2" controls-position="right" />
                  <el-input-number v-model="desktopLaunchTimeoutSec" :min="5" :max="120" :step="5" controls-position="right" />
                </div>
                <div class="mobile-grid three compact">
                  <el-switch v-model="desktopAutoScroll" active-text="自动翻页" inactive-text="不翻页" />
                  <el-switch v-model="desktopSkipHistory" active-text="跳过历史入口" inactive-text="自动点历史" />
                  <el-switch v-model="desktopImportAfterCapture" active-text="采集后自动导入" inactive-text="仅采集包" />
                </div>
                <div class="mobile-grid two compact">
                  <el-switch v-model="desktopCleanAfterImport" active-text="自动清洗" inactive-text="不清洗" :disabled="!desktopImportAfterCapture" />
                  <el-switch v-model="desktopIngestAfterImport" active-text="自动入库" inactive-text="不入库" :disabled="!desktopImportAfterCapture || !desktopCleanAfterImport" />
                </div>
                <div class="mobile-actions">
                  <el-button :loading="desktopContextLoading" @click="refreshDesktopProfiles">刷新桌面 profile</el-button>
                  <el-button type="danger" plain :disabled="!desktopProfileName || desktopCaptureLoading" @click="deleteDesktopProfileEntry">删除当前 profile</el-button>
                  <el-button type="primary" :loading="desktopCaptureLoading" @click="runDesktopCaptureFromUI">启动桌面自动采集</el-button>
                </div>
                <div
                  v-if="desktopActionFeedback"
                  class="desktop-action-feedback"
                  :data-tone="desktopActionFeedback.type"
                >
                  <div class="desktop-action-feedback-title">{{ desktopActionFeedback.title }}</div>
                  <div v-if="desktopActionFeedback.message" class="desktop-action-feedback-message">{{ desktopActionFeedback.message }}</div>
                </div>
                <div v-if="desktopStatusText" class="crawl-status">{{ desktopStatusText }}</div>
                <div v-if="desktopLastCaptureSummary" class="mobile-summary">{{ desktopLastCaptureSummary }}</div>
                <el-scrollbar v-if="desktopLogs.length" max-height="140px" class="crawl-log-scroll">
                  <div v-for="item in desktopLogs" :key="item.id" class="crawl-log-item" :data-status="item.status">
                    <span class="crawl-log-time">{{ item.time }}</span>
                    <span class="crawl-log-text">{{ item.message }}</span>
                  </div>
                </el-scrollbar>
              </div>
            </div>
          </details>
          <div v-if="agentLastRunLabel || agentRunning" class="agent-meta-row">
            <span class="agent-meta-pill" :data-status="agentRunning ? 'running' : 'idle'">
              {{ agentRunning ? (agentActiveRunCount > 1 ? `执行中 ${agentActiveRunCount} 项` : '执行中') : '已停止' }}
            </span>
            <span v-if="agentLastRunLabel" class="agent-meta-text">最近更新：{{ agentLastRunLabel }}</span>
          </div>
          <div
            v-if="agentActionFeedback"
            class="desktop-action-feedback"
            :data-tone="agentActionFeedback.type"
          >
            <div class="desktop-action-feedback-title">{{ agentActionFeedback.title }}</div>
            <div v-if="agentActionFeedback.message" class="desktop-action-feedback-message">{{ agentActionFeedback.message }}</div>
          </div>
          <div v-if="latestAgentTargetArticle" class="agent-latest-article-card">
            <div>
              <div class="agent-task-card-kicker">最新抓取结果</div>
              <div class="agent-latest-article-title">{{ latestAgentTargetArticle.title || latestAgentTargetArticle.article_id }}</div>
              <div class="agent-latest-article-meta">{{ latestAgentTargetArticle.account_id }} · {{ latestAgentTargetArticle.article_id }}</div>
            </div>
            <div class="agent-latest-article-actions">
              <el-button size="small" type="primary" plain @click="openLatestAgentTargetArticle">进入文章</el-button>
            </div>
          </div>
          <div v-if="agentFailureDiagnostics.visible" class="failure-diagnostic-card" :data-tone="agentFailureDiagnostics.tone">
            <div class="failure-diagnostic-head">
              <div>
                <div class="failure-diagnostic-title">{{ agentFailureDiagnostics.title }}</div>
                <div class="failure-diagnostic-status">{{ agentFailureDiagnostics.status }}</div>
              </div>
            </div>
            <div class="failure-diagnostic-summary">{{ agentFailureDiagnostics.summary }}</div>
            <div v-if="agentFailureDiagnostics.chips.length" class="failure-diagnostic-chip-row">
              <span v-for="chip in agentFailureDiagnostics.chips" :key="`failure-chip:${chip}`">{{ chip }}</span>
            </div>
            <div v-if="agentFailureDiagnostics.detail" class="failure-diagnostic-detail">{{ agentFailureDiagnostics.detail }}</div>
          </div>
          <div v-if="agentTaskCard" class="agent-task-card" :data-status="agentTaskCard.status">
            <div class="agent-task-card-header">
              <div class="agent-task-card-main">
                <div class="agent-task-card-kicker">Agent 任务记录</div>
                <div class="agent-task-card-title-row">
                  <div class="agent-task-card-title">{{ agentTaskCard.goal || '延后入库任务' }}</div>
                  <span class="agent-task-card-status-pill" :data-status="agentTaskCard.status">{{ formatAgentTaskStatus(agentTaskCard.status) }}</span>
                </div>
                <div class="agent-task-card-meta">
                  <span v-if="agentTaskCard.account_id">{{ agentTaskCard.account_id }}</span>
                  <span>{{ Array.isArray(agentTaskCard.article_ids) ? agentTaskCard.article_ids.length : 0 }} 篇</span>
                  <span>{{ formatAgentTaskTime(agentTaskCard.updated_at || agentTaskCard.created_at) }}</span>
                </div>
              </div>
              <div class="agent-task-card-actions">
                <el-button size="small" plain :loading="agentTaskLoading" @click="refreshAgentTaskCard">刷新状态</el-button>
                <el-button size="small" plain @click="openAgentTaskDetail(agentTaskCard)">详情</el-button>
                <el-button v-if="canOpenTaskAccount(agentTaskCard)" size="small" plain @click="openTaskAccount(agentTaskCard)">进入账号</el-button>
                <el-button v-if="canOpenTaskArticle(agentTaskCard)" size="small" plain @click="openTaskArticle(agentTaskCard)">进入文章</el-button>
                <el-button v-if="agentTaskCard.status === 'failed'" size="small" type="warning" plain :loading="agentTaskRetryingId === agentTaskCard.task_id" @click="retryAgentTask(agentTaskCard.task_id)">重试</el-button>
              </div>
            </div>
            <div v-if="buildTaskArticlePreview(agentTaskCard).length" class="agent-task-card-article-row">
              <span v-for="title in buildTaskArticlePreview(agentTaskCard, 3)" :key="`${agentTaskCard.task_id}:${title}`" class="agent-task-list-item-article-chip">{{ title }}</span>
            </div>
            <div v-if="buildAgentTaskResultSummary(agentTaskCard).length" class="agent-task-card-meta">
              <span v-for="item in buildAgentTaskResultSummary(agentTaskCard)" :key="`${agentTaskCard.task_id}:${item}`">{{ item }}</span>
            </div>
            <div v-if="agentTaskCard.summary" class="agent-task-card-summary">{{ agentTaskCard.summary }}</div>
            <div v-if="agentTaskCard.last_error" class="agent-task-card-error">最近错误：{{ agentTaskCard.last_error }}</div>
            <div v-else-if="getLatestTaskEventText(agentTaskCard)" class="agent-task-card-summary muted">
              最近进展：{{ getLatestTaskEventText(agentTaskCard) }}
            </div>
          </div>
          <WechatAgentTaskList
            :task-list="agentTaskList"
            :filtered-tasks="filteredAgentTaskList"
            :stats="recentAgentTaskStats"
            :expanded="showRecentAgentTasks"
            :filter="agentTaskFilter"
            :loading="agentTaskListLoading"
            :selected-task-id="agentTaskCard?.task_id || ''"
            :retrying-id="agentTaskRetryingId"
            :format-status="formatAgentTaskStatus"
            :format-time="formatAgentTaskTime"
            :get-article-preview="buildTaskArticlePreview"
            :get-result-summary="buildAgentTaskResultSummary"
            :can-open-account="canOpenTaskAccount"
            :can-open-article="canOpenTaskArticle"
            @toggle="showRecentAgentTasks = !showRecentAgentTasks"
            @refresh="loadRecentAgentTasks()"
            @update:filter="agentTaskFilter = $event"
            @select="selectAgentTask"
            @detail="openAgentTaskDetail"
            @open-account="openTaskAccount"
            @open-article="openTaskArticle"
            @retry="retryAgentTask"
          />
          <div v-if="agentStatusText" class="crawl-status">{{ agentStatusText }}</div>
          <div v-if="agentLogs.length" class="agent-log-panel">
            <div class="agent-log-panel-head">
              <div>
                <div class="agent-task-card-kicker">执行日志</div>
                <div class="agent-task-list-collapsed-tip">最近 {{ agentLogs.length }} 条，最新：{{ latestAgentLog?.message || '暂无' }}</div>
              </div>
              <el-button size="small" text @click="showAgentLogs = !showAgentLogs">{{ showAgentLogs ? '收起日志' : '展开日志' }}</el-button>
            </div>
            <el-scrollbar v-if="showAgentLogs" max-height="120px" class="crawl-log-scroll">
              <div v-for="item in agentLogs" :key="item.id" class="crawl-log-item" :data-status="item.status">
                <span class="crawl-log-time">{{ item.time }}</span>
                <span class="crawl-log-text">{{ item.message }}</span>
              </div>
            </el-scrollbar>
          </div>
        </div>

      </aside>

      <aside v-if="showReviewWorkspace && articleDetail && articleDetail.article.body_text" class="source-panel card-glass">
        <div class="source-panel-header">
          <div class="source-title">原文内容</div>
          <el-button link type="primary" size="small" @click="showArticleBody = !showArticleBody">
            {{ showArticleBody ? '隐藏' : '显示' }}
          </el-button>
        </div>
        <el-scrollbar v-if="showArticleBody" class="source-content">
          <div class="source-text">{{ articleDetail.article.body_text }}</div>
          <div v-if="imagePositionMarkers.length" class="image-markers">
            <div class="markers-title">图片位置标记：</div>
            <div v-for="(marker, idx) in imagePositionMarkers" :key="idx" class="marker-item">
              <span class="marker-badge">{{ marker.display_index }}</span>
              <span class="marker-text">{{ marker.note || '(无描述)' }}</span>
            </div>
          </div>
        </el-scrollbar>
      </aside>

      <main v-if="showReviewWorkspace" class="workspace">
        <section class="history-panel card-glass">
          <div class="panel-header compact">
            <div>
              <div class="panel-title">历史文章</div>
              <div class="panel-desc">搜索标题或 article_id，滚动切换文章后继续标注当前图片。</div>
            </div>
            <div class="history-panel-actions">
              <el-badge :value="annotatorArticles.length" type="primary" />
              <el-button v-if="activeAnnotatorAccountId || activeAnnotatorPublisherName" size="small" text @click="clearAnnotatorAccountScope">查看当前账号全部文章</el-button>
              <el-button size="small" plain @click="closeAnnotatorEntry">返回多 Agent 工作台</el-button>
            </div>
          </div>

          <div class="history-toolbar">
            <el-input
              v-model="articleSearch"
              clearable
              placeholder="搜索标题 / 作者 / article_id"
              :prefix-icon="Search"
              class="history-search"
            />
            <el-tag effect="light" type="info">共 {{ annotatorArticles.length }} 篇</el-tag>
            <el-tag v-if="activeAnnotatorAccountId" effect="light" type="success">当前账号：{{ activeAnnotatorAccountId }}</el-tag>
            <el-tag v-if="activeAnnotatorPublisherName" effect="light" type="warning">当前公众号：{{ activeAnnotatorPublisherName }}</el-tag>
          </div>

          <div class="history-scrollbar">
            <div
              v-for="item in annotatorArticles"
              :key="`${item.account_id}:${item.article_id}`"
              class="article-chip"
              :class="{ active: isSelected(item) }"
              @click="selectArticle(item)"
            >
              <div class="article-chip-title">{{ item.title }}</div>
              <div class="article-chip-author" v-if="item.author">作者：{{ item.author }}</div>
              <div class="article-chip-meta">{{ item.account_id }} · {{ item.article_id }}</div>
              <div class="article-chip-stats">
                <span>{{ item.images_total }} 张</span>
                <span>保留 {{ item.images_indexable }}</span>
                <span>已标注 {{ item.images_reviewed }}</span>
              </div>
            </div>
          </div>
        </section>

        <div class="workspace-main">
        <section class="hero card-glass">
          <div class="hero-copy">
            <div class="kicker">图片审阅与自然语言标注</div>
            <h2>{{ articleDetail?.article?.title || '请选择一篇文章' }}</h2>
            <p v-if="articleDetail">
              <span>
                来源：
                <el-link :href="articleDetail.article.source_link" target="_blank" type="primary">打开原文</el-link>
              </span>
              <span class="dot">·</span>
              <span>图片总数：{{ articleDetail.images_total }}</span>
              <span class="dot">·</span>
              <span>建议保留：{{ articleDetail.images_indexable }}</span>
              <span class="dot">·</span>
              <span>已人工标注：{{ articleDetail.images_reviewed }}</span>
            </p>
          </div>
          <div class="hero-metrics" v-if="articleDetail">
            <div class="metric-card">
              <div class="metric-label">保留</div>
              <div class="metric-value positive">{{ articleDetail.images_kept }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">剔除</div>
              <div class="metric-value negative">{{ articleDetail.images_dropped }}</div>
            </div>
            <div class="metric-card">
              <div class="metric-label">当前筛选</div>
              <div class="metric-value">{{ filteredImages.length }}</div>
            </div>
          </div>
        </section>

        <section class="control-panel card-glass" v-if="articleDetail">
          <div class="panel-header">
            <div>
              <div class="panel-title">自然语言标注</div>
              <div class="panel-desc">例如：第1、2张保留；第4张是表情包不要索引；第6张备注：这是大会现场。</div>
            </div>
            <div class="panel-actions">
              <el-button :icon="Refresh" @click="reloadArticle" :loading="articleLoading">刷新</el-button>
              <el-button @click="autoFillAnnotations(false)" :loading="autofilling">自动预填（仅空白）</el-button>
              <el-button @click="autoFillAnnotations(true)" :loading="autofilling">自动预填（覆盖）</el-button>
              <el-button type="primary" :icon="Edit" @click="applyInstruction" :loading="applying">应用自然语言</el-button>
              <el-button type="success" :icon="Check" @click="saveAnnotations" :loading="saving">保存标注和图片</el-button>
              <el-button @click="exportKeptImages" :loading="exporting">下载已保留图片</el-button>
            </div>
          </div>

          <el-input
            v-model="instruction"
            type="textarea"
            :rows="3"
            resize="none"
            placeholder="请输入自然语言标注指令"
            @keydown.ctrl.enter.prevent="applyInstruction"
          />

          <div class="quick-hints">
            <el-tag effect="light" @click="setInstruction('第1、2、5张保留；第4张是表情包不要索引')">保留/剔除</el-tag>
            <el-tag effect="light" @click="setInstruction('第6张备注：大会现场；第7张标签：武协,合影,活动')">摘要/标签/备注</el-tag>
            <el-tag effect="light" @click="setInstruction('第3张是装饰图不要索引；第8张保留')">装饰图过滤</el-tag>
            <el-tag effect="light" @click="setInstruction('把所有建议保留的图片先保留，建议剔除的图片先剔除')">批量套用建议</el-tag>
          </div>

          <div class="command-timeline" v-if="instructionTimeline.length">
            <div class="command-timeline-title">指令历史</div>
            <el-scrollbar max-height="168px">
              <div class="command-item" v-for="item in instructionTimeline" :key="item.id">
                <div class="command-item-head">
                  <span class="command-item-type">{{ item.type }}</span>
                  <span class="command-item-time">{{ item.time }}</span>
                </div>
                <div class="command-item-text">{{ item.text }}</div>
                <div class="command-item-note">{{ item.note }}</div>
              </div>
            </el-scrollbar>
          </div>
        </section>

        <section class="filter-bar card-glass" v-if="articleDetail">
          <div class="filter-left">
            <el-radio-group v-model="showMode" size="small">
              <el-radio-button label="all">全部</el-radio-button>
              <el-radio-button label="recommended">建议保留</el-radio-button>
              <el-radio-button label="decorative">建议剔除</el-radio-button>
              <el-radio-button label="reviewed">已标注</el-radio-button>
              <el-radio-button label="unreviewed">未标注</el-radio-button>
            </el-radio-group>
          </div>
          <div class="filter-right">
            <el-tag type="success" effect="light">支持自然语言批量标注</el-tag>
            <el-tag type="warning" effect="light">保存后立即写回标注文件</el-tag>
          </div>
        </section>

        <section class="quick-filter-bar card-glass" v-if="articleDetail">
          <div class="quick-filter-title">快速筛选</div>
          <div class="quick-filter-actions">
            <el-button size="small" :type="showMode === 'recommended' ? 'primary' : 'default'" @click="showMode = 'recommended'">
              只看建议保留
            </el-button>
            <el-button size="small" :type="showMode === 'kept' ? 'primary' : 'default'" @click="showMode = 'kept'">
              只看已保留
            </el-button>
            <el-button size="small" :type="showMode === 'decorative' ? 'primary' : 'default'" @click="showMode = 'decorative'">
              只看建议剔除
            </el-button>
            <el-button size="small" :type="showMode === 'dropped' ? 'primary' : 'default'" @click="showMode = 'dropped'">
              只看未保留
            </el-button>
            <el-button size="small" :type="showMode === 'unreviewed' ? 'primary' : 'default'" @click="showMode = 'unreviewed'">
              只看未标注
            </el-button>
            <el-button size="small" :type="showMode === 'reviewed' ? 'primary' : 'default'" @click="showMode = 'reviewed'">
              只看已标注
            </el-button>
            <el-button size="small" @click="showMode = 'all'">清空筛选</el-button>
          </div>
        </section>

        <section v-if="articleDetail" class="gallery-grid">
          <article
            v-for="img in filteredImages"
            :key="img.image_id"
            class="image-card card-glass"
            :class="{ dropped: !img.keep_for_index, reviewed: img.is_reviewed, recommended: img.indexable }"
          >
            <div class="image-topline">
              <el-tag size="small" :type="img.keep_for_index ? 'success' : 'danger'" effect="light">
                {{ img.keep_for_index ? '保留' : '剔除' }}
              </el-tag>
              <el-tag size="small" effect="light">#{{ img.display_index }}</el-tag>
              <el-button
                v-if="img.source_url"
                size="small"
                type="primary"
                text
                @click="downloadHighRes(img, $event)"
                :loading="downloadingHires === img.image_id"
              >
                {{ downloadingHires === img.image_id ? '下载中...' : '高清下载' }}
              </el-button>
            </div>

            <el-image class="thumb" :src="img.url" fit="contain" :preview-src-list="previewUrls" preview-teleported />

            <div class="image-meta">
              <div class="image-id">{{ img.image_id }}</div>
              <div class="image-submeta">{{ img.width || '—' }} × {{ img.height || '—' }} · entropy {{ Number(img.image_entropy || 0).toFixed(2) }}</div>
              <div class="image-submeta">heuristic {{ img.heuristic_score }} · OCR {{ img.ocr_char_count }} 字</div>
              <div class="reason-tags">
                <el-tag
                  v-for="(reason, idx) in (img.index_reasons || []).slice(0, 4)"
                  :key="`${img.image_id}-${reason}-${idx}`"
                  size="small"
                  type="info"
                  effect="plain"
                  :title="reason"
                >
                  {{ img.index_reasons_zh && img.index_reasons_zh[idx] ? img.index_reasons_zh[idx] : reason }}
                </el-tag>
              </div>
            </div>

            <div class="form-block">
              <el-switch v-model="img.keep_for_index" active-text="保留" inactive-text="剔除" />
              <el-button
                v-if="img.api_summary"
                size="small"
                text
                type="primary"
                @click="applyApiSummaryToManual(img)"
              >
                应用 API 描述
              </el-button>
            </div>

            <el-input
              v-model="img.scene_annotation_text"
              type="textarea"
              :autosize="{ minRows: 5, maxRows: 10 }"
              resize="vertical"
              placeholder="活动类型:体育活动|足球赛\n事件名称:2022年xx学院篮球联赛\n时间:2022-11-01\n地点:操场\n人物:张三等（人名）\n身份:x学院舞蹈队长[第七届]\n组织:xx学院|xx社团\n视觉特征:篮球|运动服|眼镜男子\n来源:XX公众号_2022年11月11日，文章标题"
            />

            <div class="summary-block">
              <div class="summary-line muted">索引说明：结构化标注模板优先，API 描述仅作参考并保留。</div>
              <div v-if="img.api_summary" class="summary-line">
                <span class="summary-label">API：</span>
                <span>{{ img.api_summary }}</span>
              </div>
              <div v-else class="summary-line muted">API 未生成语义摘要</div>
              <div v-if="img.scene_annotation_text" class="summary-line">
                <span class="summary-label">标注：</span>
                <span>{{ img.scene_annotation_text.split('\n')[0] }}</span>
              </div>
            </div>
          </article>
        </section>

        <!-- 已剔除图片独立区域 -->
        <section
          v-if="articleDetail && droppedImages.length > 0 && showMode !== 'dropped'"
          class="dropped-panel card-glass"
        >
          <div class="dropped-panel-head" @click="showDroppedPanel = !showDroppedPanel">
            <el-icon style="margin-right:6px"><el-icon-delete /></el-icon>
            <span>已剔除图片（{{ droppedImages.length }} 张）</span>
            <el-tag type="danger" size="small" effect="plain" style="margin-left:8px">不参与索引</el-tag>
            <span class="dropped-toggle-hint">{{ showDroppedPanel ? '▲ 收起' : '▼ 展开查看' }}</span>
          </div>
          <div v-if="showDroppedPanel" class="gallery-grid dropped-grid">
            <article
              v-for="img in droppedImages"
              :key="img.image_id"
              class="image-card card-glass dropped"
            >
              <div class="image-topline">
                <el-tag size="small" type="danger" effect="light">已剔除</el-tag>
                <el-tag size="small" effect="light">#{{ img.display_index }}</el-tag>
              </div>
              <el-image class="thumb" :src="img.url" fit="contain" :preview-src-list="previewUrls" preview-teleported />
              <div class="image-meta">
                <div class="image-id">{{ img.image_id }}</div>
              </div>
              <div class="form-block">
                <el-switch v-model="img.keep_for_index" active-text="恢复保留" inactive-text="已剔除" />
              </div>
            </article>
          </div>
        </section>

        <el-empty v-else-if="!articleDetail" description="请选择一篇文章开始标注" class="empty-state" />
        </div>
      </main>
    </div>

    <WechatAgentTaskDetailDialog
      :visible="agentTaskDetailVisible"
      :task="agentTaskDetailTask"
      :article-entries="agentTaskDetailArticleEntries"
      :error-text="agentTaskDetailErrorText"
      :error-preview="agentTaskDetailErrorPreview"
      :error-expanded="agentTaskErrorExpanded"
      :retrying-id="agentTaskRetryingId"
      :format-status="formatAgentTaskStatus"
      :format-time="formatAgentTaskTime"
      :format-event-detail="formatAgentTaskEventDetail"
      :build-result-summary="buildAgentTaskResultSummary"
      :can-open-account="canOpenTaskAccount"
      :can-open-article="canOpenTaskArticle"
      @update:visible="agentTaskDetailVisible = $event"
      @toggle-error-expanded="agentTaskErrorExpanded = !agentTaskErrorExpanded"
      @open-resolved-article="openResolvedTaskArticle"
      @copy-error="copyAgentTaskError"
      @copy-timeline="copyAgentTaskTimeline"
      @copy-diagnostic-summary="copyAgentTaskDiagnosticSummary"
      @open-account="openTaskAccount"
      @open-article="openTaskArticle"
      @retry="retryAgentTask"
    />
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, useRoute, useRouter } from 'vue-router'
import { Check, Edit, Refresh, Search } from '@element-plus/icons-vue'
import { streamWechatAgentCommand, streamWechatDesktopCapture, wechatAnnotatorAPI } from '@/api'
import WechatAgentProtocolOverview from '@/components/wechat/WechatAgentProtocolOverview.vue'
import WechatAgentTaskDetailDialog from '@/components/wechat/WechatAgentTaskDetailDialog.vue'
import WechatAgentTaskList from '@/components/wechat/WechatAgentTaskList.vue'

const router = useRouter()
const route = useRoute()

const articleGroups = ref([])
const articleSearch = ref('')
const articleLoading = ref(false)
const agentCommand = ref('')
const agentRunning = ref(false)
const agentActiveRunCount = ref(0)
const agentStatusText = ref('')
const agentLogs = ref([])
const agentAbortController = ref(null)
const agentActiveRunIds = ref([])
const agentActionFeedback = ref(null)
const agentOrchestration = ref(null)
const agentTaskCard = ref(null)
const agentTaskLoading = ref(false)
const agentTaskList = ref([])
const agentTaskListLoading = ref(false)
const agentTaskRetryingId = ref('')
const agentTaskFilter = ref('all')
const agentTaskDetailVisible = ref(false)
const agentTaskDetailTask = ref(null)
const agentTaskErrorExpanded = ref(false)
const agentLastSavedAt = ref(0)
const agentLastResult = ref(null)
let agentTaskPollTimer = null
let agentServerPersistTimer = null
const agentLeaveNoticeShown = ref(false)
const agentDetachedRunning = ref(false)
const agentRestoreNotice = ref({ visible: false, title: '', message: '', command: '', tone: 'info' })
const agentBrainState = ref({ visible: false, source: '', sourceLabel: '', intent: '', intentLabel: '', supported: true, message: '', reply: '', title: '', tone: 'info', planTitle: '', planSteps: [], diagnostics: { visible: false, summary: '', detail: '', chips: [], cards: [], suggestions: [] } })
const agentSessionMemory = ref(createEmptyAgentSessionMemory())
const applying = ref(false)
const saving = ref(false)
const autofilling = ref(false)
const downloadingHires = ref(null)
const exporting = ref(false)
const showMode = ref('all')
const showArticleBody = ref(false)
const instruction = ref('')
const instructionTimeline = ref([])
const articleDetail = ref(null)
const selectedKey = ref('')
const crawlAccountId = ref('my_wechat_account')
const crawlAccountQuery = ref('')
const accountCandidates = ref([])
const localAccountOverview = ref([])
const localAccountOverviewLoading = ref(false)
const localAccountOverviewFilter = ref('all')
const showLocalAccountOverview = ref(true)
const brainDiagnosticHistory = ref([])
const evaluationTrendHistory = ref([])
const evaluationTrendLoading = ref(false)
const evaluationCompare = ref(null)
const evaluationCompareLoading = ref(false)
const evaluationRerunHistoryId = ref('')
const showRecentAgentTasks = ref(false)
const showAgentLogs = ref(false)
const accountSearchLoading = ref(false)
const accountSearchFeedback = ref(null)
const selectedHistoryUrl = ref('')
const selectedAccountDisplayName = ref('')
const activeAnnotatorAccountId = ref('')
const activeAnnotatorPublisherName = ref('')
const lastSavedAnnotationVersion = ref('')
const desktopOperatorId = ref('default_operator')
const desktopProfileName = ref('')
const desktopProfiles = ref([])
const desktopAccountId = ref('my_wechat_account')
const desktopDisplayName = ref('')
const desktopWechatPath = ref('')
const desktopSearchQuery = ref('')
const desktopArticleTitle = ref('')
const desktopSourceUrl = ref('')
const desktopWindowTitleRe = ref('.*微信.*')
const desktopCaptureSteps = ref(6)
const desktopWaitSec = ref(0.5)
const desktopSettleDelaySec = ref(1.0)
const desktopLaunchTimeoutSec = ref(25)
const desktopAutoScroll = ref(true)
const desktopSkipHistory = ref(false)
const desktopImportAfterCapture = ref(true)
const desktopCleanAfterImport = ref(true)
const desktopIngestAfterImport = ref(false)
const desktopContextLoading = ref(false)
const desktopCaptureLoading = ref(false)
const desktopStatusText = ref('')
const desktopLastCaptureSummary = ref('')
const desktopLogs = ref([])
const desktopCaptureAbortController = ref(null)
const desktopActionFeedback = ref(null)
const showAdvancedTools = ref(false)
const showReviewWorkspace = ref(false)
const latestAgentTargetArticle = ref(null)

const EXPORT_HISTORY_STORAGE_KEY = 'wechatAnnotatorExportHistoryV1'
const AGENT_PANEL_STATE_STORAGE_KEY = 'wechatAnnotatorAgentPanelStateV1'
const LOCAL_ACCOUNT_OVERVIEW_EXPANDED_STORAGE_KEY = 'wechatAnnotatorLocalAccountOverviewExpandedV1'
const LOCAL_ACCOUNT_OVERVIEW_CACHE_STORAGE_KEY = 'wechatAnnotatorLocalAccountOverviewCacheV1'
const BRAIN_DIAGNOSTIC_HISTORY_STORAGE_KEY = 'wechatAnnotatorBrainDiagnosticHistoryV1'

const flatArticles = computed(() => articleGroups.value.flatMap((group) => group.articles || []))
const filteredArticles = computed(() => {
  const keyword = articleSearch.value.trim().toLowerCase()
  if (!keyword) return flatArticles.value
  return flatArticles.value.filter((item) => [item.title, item.author, item.account_id, item.article_id].some((field) => String(field || '').toLowerCase().includes(keyword)))
})
const annotatorArticles = computed(() => {
  let items = filteredArticles.value
  if (activeAnnotatorAccountId.value) {
    items = items.filter((item) => item.account_id === activeAnnotatorAccountId.value)
  }
  if (activeAnnotatorPublisherName.value) {
    items = items.filter((item) => String(item.author || '').trim() === activeAnnotatorPublisherName.value)
  }
  return items
})

const previewUrls = computed(() => (articleDetail.value?.images || []).map((img) => img.url).filter(Boolean))
const filteredLocalAccountOverview = computed(() => {
  const accounts = Array.isArray(localAccountOverview.value) ? localAccountOverview.value : []
  if (localAccountOverviewFilter.value === 'with-history') {
    return accounts.filter((item) => !!item?.has_history_url)
  }
  if (localAccountOverviewFilter.value === 'recent') {
    return accounts.filter((item) => !!item?.last_run_at || !!item?.latest_article_updated_at)
  }
  if (localAccountOverviewFilter.value === 'missing-history') {
    return accounts.filter((item) => !item?.has_history_url)
  }
  return accounts
})
const localAccountOverviewStats = computed(() => {
  const accounts = Array.isArray(localAccountOverview.value) ? localAccountOverview.value : []
  const accountCount = accounts.length || articleGroups.value.length
  const articleCount = accounts.length
    ? accounts.reduce((sum, item) => sum + Number(item?.existing_article_count || 0), 0)
    : flatArticles.value.length
  return {
    accountCount,
    articleCount,
  }
})
const compactLocalAccountOverview = computed(() => filteredLocalAccountOverview.value.slice(0, 4))
const brainDiagnosticStats = computed(() => {
  const items = Array.isArray(brainDiagnosticHistory.value) ? brainDiagnosticHistory.value : []
  const total = items.length
  const llmWins = items.filter((item) => item?.source === 'llm' && item?.succeeded === true).length
  const ruleFallbacks = items.filter((item) => item?.source !== 'llm' || item?.succeeded !== true).length
  const highDependencyRuns = items.filter((item) => item?.dependencyLevel === '高').length
  const reasonCountMap = new Map()
  for (const item of items) {
    const label = String(item?.fallbackReasonLabel || '').trim()
    if (!label || label === '未回退') continue
    reasonCountMap.set(label, Number(reasonCountMap.get(label) || 0) + 1)
  }
  const reasonItems = [...reasonCountMap.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 4)
    .map(([label, count]) => ({ label, count }))
  return {
    visible: total > 0,
    total,
    llmWins,
    ruleFallbacks,
    highDependencyRuns,
    reasonItems,
  }
})

const evaluationTrendSummary = computed(() => {
  const items = Array.isArray(evaluationTrendHistory.value) ? evaluationTrendHistory.value : []
  const latest = items[0] || null
  const previous = items[1] || null
  const readinessReadyCount = items.filter((item) => String(item?.readiness || '').trim() === 'ready').length
  const avgRagas = items.length
    ? items.reduce((sum, item) => sum + Number(item?.ragas_average || 0), 0) / items.length
    : 0
  const delta = latest && previous
    ? Number(latest?.ragas_average || 0) - Number(previous?.ragas_average || 0)
    : 0
  return {
    visible: items.length > 0,
    total: items.length,
    latest,
    readinessReadyCount,
    avgRagas: items.length ? avgRagas : null,
    delta: latest && previous ? delta : null,
    items: items.slice(0, 5),
  }
})

const evaluationTrendChart = computed(() => {
  const records = (Array.isArray(evaluationTrendHistory.value) ? evaluationTrendHistory.value : [])
    .slice(0, 8)
    .reverse()
    .map((item, index) => ({
      key: `${item?.history_id || item?.recorded_at || 'eval'}:${index}`,
      index,
      recordedAt: item?.recorded_at || '',
      score: Number.isFinite(Number(item?.ragas_average)) ? Number(item?.ragas_average) : null,
      readiness: String(item?.readiness || '').trim(),
    }))

  const validRecords = records.filter((item) => item.score !== null)
  if (!validRecords.length) {
    return {
      visible: false,
      points: [],
      linePoints: '',
      yTicks: [],
      startLabel: '',
      endLabel: '',
      windowLabel: '',
      sampleCount: 0,
      maxLabel: '--',
      minLabel: '--',
    }
  }

  const width = 480
  const height = 136
  const paddingLeft = 18
  const paddingRight = 18
  const paddingTop = 16
  const paddingBottom = 24
  const usableWidth = width - paddingLeft - paddingRight
  const usableHeight = height - paddingTop - paddingBottom
  const pointCount = Math.max(records.length - 1, 1)
  const scoreMin = 0
  const scoreMax = 1
  const normalizeScore = (value) => Math.min(scoreMax, Math.max(scoreMin, Number(value)))
  const toY = (value) => paddingTop + (1 - normalizeScore(value)) * usableHeight
  const yTicks = [0, 0.5, 1].map((value) => ({
    value,
    x1: paddingLeft,
    x2: width - paddingRight,
    y: toY(value),
  }))

  const points = records
    .filter((item) => item.score !== null)
    .map((item) => {
      const x = paddingLeft + usableWidth * (item.index / pointCount)
      const y = toY(item.score)
      return {
        key: item.key,
        x,
        y,
        radius: item.index === records.length - 1 ? 4.5 : 3.5,
        tone: item.readiness === 'ready' ? 'success' : 'warning',
      }
    })
  const linePoints = points.map((point) => `${point.x},${point.y}`).join(' ')
  const latestRecord = validRecords[validRecords.length - 1]
  const oldestRecord = validRecords[0]
  const scores = validRecords.map((item) => item.score)
  return {
    visible: points.length >= 2,
    points,
    linePoints,
    yTicks,
    startLabel: formatAgentTaskShortTime(oldestRecord?.recordedAt),
    endLabel: formatAgentTaskShortTime(latestRecord?.recordedAt),
    windowLabel: `${formatAgentTaskShortTime(oldestRecord?.recordedAt)} 至 ${formatAgentTaskShortTime(latestRecord?.recordedAt)}`,
    sampleCount: validRecords.length,
    maxLabel: formatAgentMetricScore(Math.max(...scores)),
    minLabel: formatAgentMetricScore(Math.min(...scores)),
  }
})

const evaluationCompareSummary = computed(() => {
  const payload = evaluationCompare.value && typeof evaluationCompare.value === 'object' ? evaluationCompare.value : {}
  const latest = payload.latest && typeof payload.latest === 'object' ? payload.latest : null
  const previous = payload.previous && typeof payload.previous === 'object' ? payload.previous : null
  const delta = payload.delta && typeof payload.delta === 'object' ? payload.delta : null
  return {
    visible: !!latest,
    latest,
    previous,
    delta,
  }
})

const agentFailureDiagnostics = computed(() => buildAgentFailureDiagnostics(agentLastResult.value || null))

const handoffContractCards = computed(() => {
  const orchestration = agentOrchestration.value
  if (!orchestration) return []

  const completedAgents = Array.isArray(orchestration.completedAgents) ? orchestration.completedAgents : []
  const handoffs = Array.isArray(orchestration.handoffs) ? orchestration.handoffs : []
  const artifactTypes = Array.isArray(orchestration.artifactTypes) ? orchestration.artifactTypes : []
  const protocolHandoffs = Array.isArray(orchestration.protocol?.handoffTemplates) ? orchestration.protocol.handoffTemplates : []
  const taskStatus = String(orchestration.task?.status || '').trim()
  const review = orchestration.review || {}

  const buildCard = ({ key, fromAgent, toAgent, title, requiredInputs, fallbackSummary, inputsReady }) => {
    const handoff = handoffs.find((item) => item.fromAgent === fromAgent && item.toAgent === toAgent) || null
    const targetCompleted = completedAgents.includes(toAgent)
    const waiting = !targetCompleted && !!handoff && orchestration.nextAgent === toAgent && taskStatus === 'waiting_handoff'

    let status = '未触发'
    let tone = 'idle'
    let summary = fallbackSummary
    let detail = ''

    if (targetCompleted) {
      status = '已完成'
      tone = 'success'
      summary = `${formatAgentRoleName(toAgent)} 已经完成这一跳。`
      detail = handoff ? `交接原因：${formatHandoffReason(handoff.handoffReason)}。` : '这一跳已经完成，所以当前没有挂起中的 handoff。'
    } else if (waiting) {
      status = '等待下一跳'
      tone = 'warning'
      summary = `${formatAgentRoleName(fromAgent)} 已经准备好输入，当前等待 ${formatAgentRoleName(toAgent)} 接手。`
      detail = `交接原因：${formatHandoffReason(handoff?.handoffReason)}。`
    } else if (!inputsReady) {
      status = '缺少输入'
      tone = 'danger'
      summary = `这一跳还缺少必需输入，所以 ${formatAgentRoleName(toAgent)} 没有启动。`
      detail = review.summary || ''
    } else if (handoff) {
      status = '已生成契约'
      tone = 'warning'
      summary = '这一跳的 handoff 契约已经生成，但还没有被下一跳消费。'
      detail = `交接原因：${formatHandoffReason(handoff.handoffReason)}。`
    } else if (taskStatus && taskStatus !== 'completed' && taskStatus !== 'partial_success' && toAgent === 'evaluation_optimization_agent') {
      status = '上游未完成'
      tone = 'warning'
      summary = '上游阶段还没有稳定完成，所以评测阶段不应继续推进。'
      detail = review.failureReason || review.summary || ''
    }

    const chips = [
      `来源：${formatAgentRoleName(fromAgent)}`,
      `目标：${formatAgentRoleName(toAgent)}`,
      ...(handoff?.requiredInputs || requiredInputs).map((item) => `需要 ${formatRequiredInputLabel(item)}`),
      handoff?.deadlineSec ? `时限 ${handoff.deadlineSec}s` : '',
    ].filter(Boolean)

    return { key, title, status, tone, summary, detail, chips }
  }

  const templates = protocolHandoffs.length
    ? protocolHandoffs
    : [
        {
          handoffId: 'collect-to-governance',
          fromAgent: 'knowledge_acquisition_agent',
          toAgent: 'knowledge_governance_agent',
          title: '采集 Agent -> 治理 Agent',
          requiredInputs: ['created_articles', 'clean_result', 'shared_context'],
          inputRules: [
            { input: 'created_articles', artifactTypesAny: ['article_record', 'cleaning_result'] },
            { input: 'clean_result', artifactTypesAny: ['article_record', 'cleaning_result'] },
            { input: 'shared_context', always: true },
          ],
          fallbackSummary: '只有采集阶段形成新文章记录或清洗结果后，这一跳才应该被创建。',
        },
        {
          handoffId: 'governance-to-evaluation',
          fromAgent: 'knowledge_governance_agent',
          toAgent: 'evaluation_optimization_agent',
          title: '治理 Agent -> 评测 Agent',
          requiredInputs: ['governance_report', 'shared_context'],
          inputRules: [
            { input: 'governance_report', artifactTypesAny: ['governance_report'] },
            { input: 'shared_context', always: true },
          ],
          fallbackSummary: '只有治理阶段产出治理报告后，评测 Agent 才应该被触发。',
        },
      ]
  return templates.map((item) => buildCard({
    key: item.handoffId || `${item.fromAgent}:${item.toAgent}`,
    fromAgent: item.fromAgent,
    toAgent: item.toAgent,
    title: item.title,
    requiredInputs: Array.isArray(item.requiredInputs) ? item.requiredInputs : [],
    fallbackSummary: item.fallbackSummary || '当前 handoff 还没有满足触发条件。',
    inputsReady: (Array.isArray(item.inputRules) && item.inputRules.length)
      ? item.inputRules.every((rule) => isProtocolInputReady(rule, artifactTypes))
      : true,
  }))
})

const agentLastRunLabel = computed(() => {
  if (!agentLastSavedAt.value) return ''
  try {
    return new Date(agentLastSavedAt.value).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return ''
  }
})
const agentMemorySummary = computed(() => {
  const memory = normalizeAgentSessionMemory(agentSessionMemory.value)
  const items = []
  const accountLabel = memory.pinnedDisplayName || memory.pinnedAccountId || memory.recentDisplayName || memory.recentAccountId
  if (accountLabel) {
    const accountIdLabel = memory.pinnedAccountId || memory.recentAccountId
    const prefix = memory.accountLocked && memory.pinnedAccountId ? '已锁定账号：' : '最近账号：'
    items.push(`${prefix}${accountLabel}${accountIdLabel && accountLabel !== accountIdLabel ? `（${accountIdLabel}）` : ''}`)
  }
  if (memory.recentDecision) items.push(`最近决策：${formatAgentDecisionLabel(memory.recentDecision)}`)
  if (memory.recentArticleTitle) items.push(`最近文章：${memory.recentArticleTitle}`)
  if (memory.recentHistoryUrl) items.push('历史页入口：已记录')
  if (Array.isArray(memory.recentUrls) && memory.recentUrls.length) items.push(`最近链接：${memory.recentUrls.length} 条`)
  if (memory.recentFailureReason) items.push(`最近失败：${memory.recentFailureReason}`)
  return items.slice(0, 6)
})
const agentStageCards = computed(() => {
  const finalData = agentLastResult.value || {}
  const steps = Array.isArray(finalData?.steps) ? finalData.steps : []
  const collectStep = getAgentCollectStep(finalData)
  const cleanStep = steps.find((step) => step?.name === 'clean') || null
  const reasonStep = steps.find((step) => step?.name === 'reason') || null
  const runResult = collectStep?.result?.run_result || {}
  const orchestration = agentOrchestration.value || null
  const completedAgents = Array.isArray(orchestration?.completedAgents) ? orchestration.completedAgents : []
  const governance = orchestration?.governance || null
  const evaluation = orchestration?.evaluation || null
  const parsedIntent = agentBrainState.value?.intentLabel || '未解析'
  const parsedSource = agentBrainState.value?.sourceLabel || '尚未判断'
  const decisionLabel = formatAgentDecisionLabel(reasonStep?.result?.action)
  const created = Number(runResult?.new_articles || 0)
  const processed = Number(runResult?.processed_articles || 0)
  const duplicateCount = Number(collectStep?.result?.duplicate_url_count || runResult?.duplicate_url_count || (Array.isArray(collectStep?.result?.duplicate_article_urls) ? collectStep.result.duplicate_article_urls.length : 0) || 0)
  const collectFailed = String(collectStep?.evaluation?.status || collectStep?.status || '').trim() === 'failed'
  const cleanFailed = String(cleanStep?.evaluation?.status || cleanStep?.status || '').trim() === 'failed'
  const governanceFailed = String(governance?.status || '').trim() === 'failed'
  const evaluationFailed = String(evaluation?.status || '').trim() === 'failed'
  const cleanSkippedReason = String(cleanStep?.result?.skipped_reason || '').trim()
  const protocol = orchestration?.protocol || null
  const protocolAgents = Array.isArray(protocol?.agents) ? protocol.agents : []
  const collectAgent = getProtocolAgentDefinition(protocol, 'knowledge_acquisition_agent')
  const governanceAgent = getProtocolAgentDefinition(protocol, 'knowledge_governance_agent')
  const evaluationAgent = getProtocolAgentDefinition(protocol, 'evaluation_optimization_agent')

  const collectCard = {
    key: 'collect',
    kicker: collectAgent?.kicker || 'Agent 01',
    title: collectAgent?.title || '知识采集 Agent',
    tone: 'idle',
    status: '等待输入',
    summary: formatProtocolSummary(protocol, 'knowledge_acquisition_agent', 'idle', {}, '尚未接收到新的公众号指令。'),
    metrics: [],
    detail: '',
  }
  if (agentRunning.value && !collectStep) {
    collectCard.tone = 'running'
    collectCard.status = '准备执行'
    collectCard.summary = formatProtocolSummary(protocol, 'knowledge_acquisition_agent', 'preparing', { parsed_intent: parsedIntent }, `正在做入口判断，当前意图 ${parsedIntent}。`)
    collectCard.metrics = [formatProtocolMetric(protocol, 'knowledge_acquisition_agent', 'source', parsedSource, `解析源：${parsedSource}`)].filter(Boolean)
  } else if (collectStep) {
    collectCard.tone = collectFailed ? 'danger' : (created > 0 ? 'success' : 'warning')
    collectCard.status = collectFailed ? '采集失败' : (created > 0 ? '采集完成' : '已执行无新增')
    collectCard.summary = collectFailed
      ? (describeZeroNewArticles(finalData) || formatProtocolSummary(protocol, 'knowledge_acquisition_agent', 'failed', {}, '采集阶段执行失败。'))
      : (created > 0
        ? formatProtocolSummary(protocol, 'knowledge_acquisition_agent', 'completed', { processed, created }, `已处理 ${processed} 条链接，新增 ${created} 篇文章。`)
        : formatProtocolSummary(protocol, 'knowledge_acquisition_agent', 'no_new', { processed, created }, '当前轮次已执行采集，但没有新增文章进入后续阶段。'))
    collectCard.metrics = [
      formatProtocolMetric(protocol, 'knowledge_acquisition_agent', 'source', parsedSource, `解析源：${parsedSource}`),
      decisionLabel && decisionLabel !== '未记录' ? formatProtocolMetric(protocol, 'knowledge_acquisition_agent', 'decision', decisionLabel, `决策：${decisionLabel}`) : '',
      processed > 0 ? formatProtocolMetric(protocol, 'knowledge_acquisition_agent', 'processed', processed, `处理 ${processed} 条`) : '',
      duplicateCount > 0 ? formatProtocolMetric(protocol, 'knowledge_acquisition_agent', 'duplicate', duplicateCount, `重复 ${duplicateCount} 条`) : '',
    ].filter(Boolean)
    collectCard.detail = cleanSkippedReason === 'no_new_articles_to_clean'
      ? formatProtocolSummary(protocol, 'knowledge_acquisition_agent', 'clean_skipped_detail', {}, '这一轮没有形成新的清洗目标。')
      : ''
  } else if (agentBrainState.value?.visible) {
    collectCard.tone = agentBrainState.value.supported ? 'info' : 'warning'
    collectCard.status = agentBrainState.value.supported ? '已完成判断' : '能力外请求'
    collectCard.summary = agentBrainState.value.message || formatProtocolSummary(protocol, 'knowledge_acquisition_agent', 'decision_ready', { parsed_intent: parsedIntent }, `当前意图 ${parsedIntent}，等待进入执行阶段。`)
    collectCard.metrics = [
      formatProtocolMetric(protocol, 'knowledge_acquisition_agent', 'source', parsedSource, `解析源：${parsedSource}`),
      formatProtocolMetric(protocol, 'knowledge_acquisition_agent', 'intent', parsedIntent, `意图：${parsedIntent}`),
    ].filter(Boolean)
  }

  const governanceTriggered = completedAgents.includes('knowledge_governance_agent') || String(governance?.status || '').trim() === 'completed'
  const governanceCard = {
    key: 'governance',
    kicker: governanceAgent?.kicker || 'Agent 02',
    title: governanceAgent?.title || '知识治理 Agent',
    tone: 'idle',
    status: '未触发',
    summary: formatProtocolSummary(protocol, 'knowledge_governance_agent', 'idle', {}, '只有在采集阶段形成新的知识资产后，才会继续进入治理。'),
    metrics: [],
    detail: '',
  }
  if (governanceFailed) {
    governanceCard.tone = 'danger'
    governanceCard.status = '治理失败'
    governanceCard.summary = governance?.summary || formatProtocolSummary(protocol, 'knowledge_governance_agent', 'failed', {}, '治理阶段执行失败。')
  } else if (governanceTriggered) {
    governanceCard.tone = 'success'
    governanceCard.status = '治理完成'
    governanceCard.summary = governance?.summary || formatProtocolSummary(protocol, 'knowledge_governance_agent', 'completed', {}, '治理阶段已完成。')
    governanceCard.metrics = [governance?.riskLevel ? formatProtocolMetric(protocol, 'knowledge_governance_agent', 'risk_level', governance.riskLevel, `风险：${governance.riskLevel}`) : ''].filter(Boolean)
  } else if (collectStep) {
    governanceCard.tone = cleanSkippedReason === 'no_new_articles_to_clean' ? 'idle' : 'warning'
    governanceCard.status = cleanSkippedReason === 'no_new_articles_to_clean' ? '未获得输入' : '等待触发'
    governanceCard.summary = cleanSkippedReason === 'no_new_articles_to_clean'
      ? formatProtocolSummary(protocol, 'knowledge_governance_agent', 'no_input', {}, '采集阶段没有形成新的清洗目标，所以治理没有拿到输入。')
      : formatProtocolSummary(protocol, 'knowledge_governance_agent', 'waiting', {}, '当前轮次还没有进入治理阶段。')
  }

  const evaluationTriggered = completedAgents.includes('evaluation_optimization_agent') || String(evaluation?.status || '').trim() === 'completed'
  const evaluationCard = {
    key: 'evaluation',
    kicker: evaluationAgent?.kicker || 'Agent 03',
    title: evaluationAgent?.title || '评测优化 Agent',
    tone: 'idle',
    status: '未触发',
    summary: formatProtocolSummary(protocol, 'evaluation_optimization_agent', 'idle', {}, '评测 Agent 会在治理或编排确认后再汇总质量指标。'),
    metrics: [],
    detail: '',
  }
  if (evaluationFailed) {
    evaluationCard.tone = 'danger'
    evaluationCard.status = '评测失败'
    evaluationCard.summary = evaluation?.summary || formatProtocolSummary(protocol, 'evaluation_optimization_agent', 'failed', {}, '评测阶段执行失败。')
  } else if (evaluationTriggered) {
    evaluationCard.tone = 'success'
    evaluationCard.status = '评测完成'
    evaluationCard.summary = evaluation?.summary || formatProtocolSummary(protocol, 'evaluation_optimization_agent', 'completed', {}, '评测阶段已完成。')
    evaluationCard.metrics = [
      evaluation?.ragasAverage !== null ? formatProtocolMetric(protocol, 'evaluation_optimization_agent', 'ragas_average', formatAgentMetricScore(evaluation.ragasAverage), `RAGAS ${formatAgentMetricScore(evaluation.ragasAverage)}`) : '',
      evaluation?.sampleCount ? formatProtocolMetric(protocol, 'evaluation_optimization_agent', 'sample_count', evaluation.sampleCount, `样本 ${evaluation.sampleCount}`) : '',
      evaluation?.readiness ? formatProtocolMetric(protocol, 'evaluation_optimization_agent', 'readiness', evaluation.readiness, `就绪度：${evaluation.readiness}`) : '',
    ].filter(Boolean)
    evaluationCard.detail = evaluation?.snapshotLabel ? formatProtocolMetric(protocol, 'evaluation_optimization_agent', 'snapshot', evaluation.snapshotLabel, `快照：${evaluation.snapshotLabel}`) : ''
  } else if (governanceTriggered || governanceFailed || cleanStep) {
    evaluationCard.tone = cleanFailed ? 'warning' : 'idle'
    evaluationCard.status = cleanFailed ? '上游中断' : '等待触发'
    evaluationCard.summary = cleanFailed
      ? formatProtocolSummary(protocol, 'evaluation_optimization_agent', 'upstream_blocked', {}, '清洗或治理阶段没有稳定完成，评测阶段因此没有继续。')
      : formatProtocolSummary(protocol, 'evaluation_optimization_agent', 'waiting', {}, '当前轮次还没有进入评测阶段。')
  }

  const cardsByAgent = {
    knowledge_acquisition_agent: collectCard,
    knowledge_governance_agent: governanceCard,
    evaluation_optimization_agent: evaluationCard,
  }
  if (protocolAgents.length) {
    return protocolAgents.map((item) => cardsByAgent[item.agentId]).filter(Boolean)
  }
  return [collectCard, governanceCard, evaluationCard]
})
const filteredAgentTaskList = computed(() => {
  const items = Array.isArray(agentTaskList.value) ? agentTaskList.value : []
  if (agentTaskFilter.value === 'active') {
    return items.filter((item) => ['queued', 'running', 'deferred'].includes(String(item?.status || '').trim()))
  }
  if (agentTaskFilter.value === 'failed') {
    return items.filter((item) => String(item?.status || '').trim() === 'failed')
  }
  if (agentTaskFilter.value === 'completed') {
    return items.filter((item) => String(item?.status || '').trim() === 'completed')
  }
  return items
})
const recentAgentTaskStats = computed(() => {
  const items = Array.isArray(agentTaskList.value) ? agentTaskList.value : []
  return {
    total: items.length,
    active: items.filter((item) => ['queued', 'running', 'deferred'].includes(String(item?.status || '').trim())).length,
    failed: items.filter((item) => String(item?.status || '').trim() === 'failed').length,
    completed: items.filter((item) => String(item?.status || '').trim() === 'completed').length,
  }
})
const latestAgentLog = computed(() => (Array.isArray(agentLogs.value) && agentLogs.value.length ? agentLogs.value[0] : null))
const agentTaskDetailArticleEntries = computed(() => listTaskArticleEntries(agentTaskDetailTask.value))
const agentTaskDetailErrorText = computed(() => String(agentTaskDetailTask.value?.last_error || '').trim())
const agentTaskDetailErrorPreview = computed(() => {
  const text = agentTaskDetailErrorText.value
  if (!text) return ''
  if (agentTaskErrorExpanded.value || text.length <= 240) return text
  return `${text.slice(0, 240)}...`
})
const agentTaskDetailTimelineText = computed(() => buildAgentTaskTimelineText(agentTaskDetailTask.value))
const agentTaskDetailDiagnosticSummary = computed(() => buildAgentTaskDiagnosticSummary(agentTaskDetailTask.value))

const imagePositionMarkers = computed(() => {
  if (!articleDetail.value?.images) return []
  return (articleDetail.value.images || []).map((img) => ({
    display_index: img.display_index,
    image_id: img.image_id,
    note: img.manual_summary || img.api_summary || '(无描述)',
  }))
})

const filteredImages = computed(() => {
  const images = articleDetail.value?.images || []
  // 'all' 模式默认只显示保留的图片（已剔除图片在独立区域展示）
  if (showMode.value === 'all') return images.filter((img) => img.keep_for_index)
  if (showMode.value === 'recommended') return images.filter((img) => img.indexable)
  if (showMode.value === 'kept') return images.filter((img) => img.keep_for_index)
  if (showMode.value === 'decorative') return images.filter((img) => !img.indexable || img.decorative_candidate)
  if (showMode.value === 'dropped') return images.filter((img) => !img.keep_for_index)
  if (showMode.value === 'reviewed') return images.filter((img) => img.is_reviewed)
  if (showMode.value === 'unreviewed') return images.filter((img) => !img.is_reviewed)
  return images
})

const droppedImages = computed(() => {
  // 仅在非 dropped 模式下显示独立剔除区（dropped 模式时主gallery已显示）
  if (showMode.value === 'dropped') return []
  return (articleDetail.value?.images || []).filter((img) => !img.keep_for_index)
})

const showDroppedPanel = ref(false)

function isSelected(item) {
  return selectedKey.value === `${item.account_id}:${item.article_id}`
}

function setInstruction(text) {
  instruction.value = text
}

function applyApiSummaryToManual(img) {
  if (!img) return
  const apiText = String(img.api_summary || '').trim()
  if (!apiText) return
  const lines = String(img.scene_annotation_text || '').split('\n')
  const next = []
  let replaced = false
  for (const raw of lines) {
    const line = String(raw || '').trim()
    if (!line) continue
    if (/^事件名称\s*[:：]/.test(line)) {
      next.push(`事件名称:${apiText}`)
      replaced = true
    } else {
      next.push(line)
    }
  }
  if (!replaced) next.push(`事件名称:${apiText}`)
  img.scene_annotation_text = next.join('\n')
}

function getOverviewDisplayName(item) {
  const baseName = item?.preferred_name || item?.display_name || item?.account_id || '未命名账号'
  const duplicates = (Array.isArray(localAccountOverview.value) ? localAccountOverview.value : []).filter((candidate) => {
    const candidateName = candidate?.preferred_name || candidate?.display_name || candidate?.account_id || ''
    return candidateName === baseName
  })
  if (duplicates.length > 1 && item?.account_id) {
    return `${baseName}（${item.account_id}）`
  }
  return baseName
}

function getOverviewDisplayNameHint(item) {
  const displayName = String(item?.display_name || '').trim()
  const preferredName = String(item?.preferred_name || '').trim()
  const accountId = String(item?.account_id || '').trim()
  const possibleNames = Array.isArray(item?.possible_names) ? item.possible_names.filter(Boolean) : []

  if (preferredName && possibleNames.includes(preferredName)) {
    return '当前中文名来自已抓取文章里的作者名线索，不代表 source 配置里原本就是中文。'
  }
  if (displayName && displayName !== accountId) {
    return '当前名称来自本地配置文件或导入记录。'
  }
  if ((item?.existing_article_count || 0) > 0) {
    return '当前没有稳定的中文公众号名线索，因此先显示账号 ID；不一定是解析失败。'
  }
  return '这是调试账号、占位账号或尚未抓到文章的账号，所以暂时只能显示账号 ID。'
}

function resolveOverviewPublisherName(item) {
  const preferredName = String(item?.preferred_name || '').trim()
  if (preferredName) return preferredName
  const displayName = String(item?.display_name || '').trim()
  if (displayName && displayName !== String(item?.account_id || '').trim()) return displayName
  return ''
}

function restoreLocalAccountOverviewState() {
  try {
    const raw = localStorage.getItem(LOCAL_ACCOUNT_OVERVIEW_EXPANDED_STORAGE_KEY)
    if (raw === '0') {
      showLocalAccountOverview.value = false
      return
    }
  } catch {
    // ignore storage errors for transient UI preference
  }
  showLocalAccountOverview.value = true
}

function persistLocalAccountOverviewState() {
  try {
    localStorage.setItem(LOCAL_ACCOUNT_OVERVIEW_EXPANDED_STORAGE_KEY, showLocalAccountOverview.value ? '1' : '0')
  } catch {
    // ignore storage errors for transient UI preference
  }
}

function restoreLocalAccountOverviewCache() {
  try {
    const raw = sessionStorage.getItem(LOCAL_ACCOUNT_OVERVIEW_CACHE_STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return
    localAccountOverview.value = parsed
  } catch {
    // ignore broken transient cache
  }
}

function persistLocalAccountOverviewCache(list) {
  try {
    sessionStorage.setItem(
      LOCAL_ACCOUNT_OVERVIEW_CACHE_STORAGE_KEY,
      JSON.stringify(Array.isArray(list) ? list.slice(0, 8) : []),
    )
  } catch {
    // ignore storage quota errors for transient cache
  }
}

function toggleLocalAccountOverview() {
  showLocalAccountOverview.value = !showLocalAccountOverview.value
  persistLocalAccountOverviewState()
}

function parseSceneAnnotationText(text) {
  const out = {}
  String(text || '')
    .split('\n')
    .forEach((row) => {
      const line = String(row || '').trim()
      if (!line) return
      const splitIdx = line.indexOf(':') >= 0 ? line.indexOf(':') : line.indexOf('：')
      if (splitIdx <= 0) return
      const key = line.slice(0, splitIdx).trim()
      const value = line.slice(splitIdx + 1).trim()
      if (key && value) out[key] = value
    })
  return out
}

function pushTimeline(type, text, note) {
  instructionTimeline.value = [
    {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      type,
      time: new Date().toLocaleString('zh-CN', { hour12: false }),
      text,
      note,
    },
    ...instructionTimeline.value,
  ].slice(0, 8)
}

function getExportHistory() {
  try {
    const raw = localStorage.getItem(EXPORT_HISTORY_STORAGE_KEY)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    return parsed && typeof parsed === 'object' ? parsed : {}
  } catch {
    return {}
  }
}

function setExportHistory(history) {
  localStorage.setItem(EXPORT_HISTORY_STORAGE_KEY, JSON.stringify(history))
}

function createEmptyAgentSessionMemory() {
  return {
    accountLocked: false,
    pinnedAccountId: '',
    pinnedDisplayName: '',
    recentAccountId: '',
    recentDisplayName: '',
    recentHistoryUrl: '',
    recentUrls: [],
    recentArticleTitle: '',
    recentFailureReason: '',
    recentDecision: '',
    taskMemory: {
      command: '',
      goal: '',
      intent: '',
      status: 'idle',
      lastStep: '',
      lastFailureReason: '',
      attemptCount: 0,
      lastPlanSignature: '',
      targetAccountId: '',
      targetDisplayName: '',
      targetArticleTitle: '',
      targetSearchQuery: '',
      updatedAt: '',
    },
    taskHistory: [],
    accountHistory: [],
    updatedAt: 0,
  }
}

function normalizeAgentSessionMemory(raw) {
  const payload = raw && typeof raw === 'object' ? raw : {}
  const rawUrls = payload.recentUrls || payload.recent_urls
  const rawTaskMemory = payload.taskMemory || payload.task_memory || {}
  const rawTaskHistory = Array.isArray(payload.taskHistory || payload.task_history) ? (payload.taskHistory || payload.task_history) : []
  const rawAccountHistory = Array.isArray(payload.accountHistory || payload.account_history) ? (payload.accountHistory || payload.account_history) : []
  return {
    accountLocked: Boolean(payload.accountLocked ?? payload.account_locked ?? false),
    pinnedAccountId: String(payload.pinnedAccountId || payload.pinned_account_id || '').trim(),
    pinnedDisplayName: String(payload.pinnedDisplayName || payload.pinned_display_name || '').trim(),
    recentAccountId: String(payload.recentAccountId || payload.recent_account_id || '').trim(),
    recentDisplayName: String(payload.recentDisplayName || payload.recent_display_name || '').trim(),
    recentHistoryUrl: String(payload.recentHistoryUrl || payload.recent_history_url || '').trim(),
    recentUrls: Array.isArray(rawUrls) ? rawUrls.map((item) => String(item || '').trim()).filter(Boolean).slice(0, 5) : [],
    recentArticleTitle: String(payload.recentArticleTitle || payload.recent_article_title || '').trim(),
    recentFailureReason: String(payload.recentFailureReason || payload.recent_failure_reason || '').trim(),
    recentDecision: String(payload.recentDecision || payload.recent_decision || '').trim(),
    taskMemory: {
      command: String(rawTaskMemory.command || '').trim(),
      goal: String(rawTaskMemory.goal || '').trim(),
      intent: String(rawTaskMemory.intent || '').trim(),
      status: String(rawTaskMemory.status || 'idle').trim() || 'idle',
      lastStep: String(rawTaskMemory.lastStep || rawTaskMemory.last_step || '').trim(),
      lastFailureReason: String(rawTaskMemory.lastFailureReason || rawTaskMemory.last_failure_reason || '').trim(),
      attemptCount: Number(rawTaskMemory.attemptCount || rawTaskMemory.attempt_count || 0),
      lastPlanSignature: String(rawTaskMemory.lastPlanSignature || rawTaskMemory.last_plan_signature || '').trim(),
      targetAccountId: String(rawTaskMemory.targetAccountId || rawTaskMemory.target_account_id || '').trim(),
      targetDisplayName: String(rawTaskMemory.targetDisplayName || rawTaskMemory.target_display_name || '').trim(),
      targetArticleTitle: String(rawTaskMemory.targetArticleTitle || rawTaskMemory.target_article_title || '').trim(),
      targetSearchQuery: String(rawTaskMemory.targetSearchQuery || rawTaskMemory.target_search_query || '').trim(),
      updatedAt: String(rawTaskMemory.updatedAt || rawTaskMemory.updated_at || '').trim(),
    },
    taskHistory: rawTaskHistory.map((item) => ({
      command: String(item?.command || '').trim(),
      goal: String(item?.goal || '').trim(),
      intent: String(item?.intent || '').trim(),
      status: String(item?.status || '').trim(),
      lastStep: String(item?.lastStep || item?.last_step || '').trim(),
      failureReason: String(item?.failureReason || item?.failure_reason || '').trim(),
      accountId: String(item?.accountId || item?.account_id || '').trim(),
      finishedAt: String(item?.finishedAt || item?.finished_at || '').trim(),
    })).filter((item) => item.command || item.goal || item.accountId).slice(0, 8),
    accountHistory: rawAccountHistory.map((item) => ({
      accountId: String(item?.accountId || item?.account_id || '').trim(),
      displayName: String(item?.displayName || item?.display_name || '').trim(),
      historyUrl: String(item?.historyUrl || item?.history_url || '').trim(),
      articleTitle: String(item?.articleTitle || item?.article_title || '').trim(),
      searchQuery: String(item?.searchQuery || item?.search_query || '').trim(),
      lastAction: String(item?.lastAction || item?.last_action || '').trim(),
      lastOutcome: String(item?.lastOutcome || item?.last_outcome || '').trim(),
      lastFailureReason: String(item?.lastFailureReason || item?.last_failure_reason || '').trim(),
      lastSuccessAt: String(item?.lastSuccessAt || item?.last_success_at || '').trim(),
      lastAttemptAt: String(item?.lastAttemptAt || item?.last_attempt_at || '').trim(),
    })).filter((item) => item.accountId || item.displayName).slice(0, 10),
    updatedAt: Number(payload.updatedAt || payload.updated_at || 0),
  }
}

function buildAgentSessionMemoryPayload() {
  const memory = normalizeAgentSessionMemory(agentSessionMemory.value)
  return {
    account_locked: memory.accountLocked,
    pinned_account_id: memory.pinnedAccountId,
    pinned_display_name: memory.pinnedDisplayName,
    recent_account_id: memory.recentAccountId,
    recent_display_name: memory.recentDisplayName,
    recent_history_url: memory.recentHistoryUrl,
    recent_urls: memory.recentUrls,
    recent_article_title: memory.recentArticleTitle,
    recent_failure_reason: memory.recentFailureReason,
    recent_decision: memory.recentDecision,
    task_memory: {
      command: memory.taskMemory.command,
      goal: memory.taskMemory.goal,
      intent: memory.taskMemory.intent,
      status: memory.taskMemory.status,
      last_step: memory.taskMemory.lastStep,
      last_failure_reason: memory.taskMemory.lastFailureReason,
      attempt_count: memory.taskMemory.attemptCount,
      last_plan_signature: memory.taskMemory.lastPlanSignature,
      target_account_id: memory.taskMemory.targetAccountId,
      target_display_name: memory.taskMemory.targetDisplayName,
      target_article_title: memory.taskMemory.targetArticleTitle,
      target_search_query: memory.taskMemory.targetSearchQuery,
      updated_at: memory.taskMemory.updatedAt,
    },
    task_history: memory.taskHistory.map((item) => ({
      command: item.command,
      goal: item.goal,
      intent: item.intent,
      status: item.status,
      last_step: item.lastStep,
      failure_reason: item.failureReason,
      account_id: item.accountId,
      finished_at: item.finishedAt,
    })),
    account_history: memory.accountHistory.map((item) => ({
      account_id: item.accountId,
      display_name: item.displayName,
      history_url: item.historyUrl,
      article_title: item.articleTitle,
      search_query: item.searchQuery,
      last_action: item.lastAction,
      last_outcome: item.lastOutcome,
      last_failure_reason: item.lastFailureReason,
      last_success_at: item.lastSuccessAt,
      last_attempt_at: item.lastAttemptAt,
    })),
  }
}

function hasAgentSessionMemory(memory) {
  const normalized = normalizeAgentSessionMemory(memory)
  return !!(
    normalized.accountLocked
    || normalized.pinnedAccountId
    || normalized.pinnedDisplayName
    || normalized.recentAccountId
    || normalized.recentDisplayName
    || normalized.recentHistoryUrl
    || normalized.recentArticleTitle
    || normalized.recentFailureReason
    || normalized.recentDecision
    || normalized.recentUrls.length
    || normalized.taskMemory.goal
    || normalized.taskHistory.length
    || normalized.accountHistory.length
  )
}

function updateAgentSessionMemory(patch = {}, options = {}) {
  const current = normalizeAgentSessionMemory(agentSessionMemory.value)
  const next = { ...current }

  if (Object.prototype.hasOwnProperty.call(patch, 'accountLocked')) next.accountLocked = !!patch.accountLocked
  if (Object.prototype.hasOwnProperty.call(patch, 'pinnedAccountId')) next.pinnedAccountId = String(patch.pinnedAccountId || '').trim()
  if (Object.prototype.hasOwnProperty.call(patch, 'pinnedDisplayName')) next.pinnedDisplayName = String(patch.pinnedDisplayName || '').trim()
  if (Object.prototype.hasOwnProperty.call(patch, 'recentAccountId')) next.recentAccountId = String(patch.recentAccountId || '').trim()
  if (Object.prototype.hasOwnProperty.call(patch, 'recentDisplayName')) next.recentDisplayName = String(patch.recentDisplayName || '').trim()
  if (Object.prototype.hasOwnProperty.call(patch, 'recentHistoryUrl')) next.recentHistoryUrl = String(patch.recentHistoryUrl || '').trim()
  if (Object.prototype.hasOwnProperty.call(patch, 'recentArticleTitle')) next.recentArticleTitle = String(patch.recentArticleTitle || '').trim()
  if (Object.prototype.hasOwnProperty.call(patch, 'recentDecision')) next.recentDecision = String(patch.recentDecision || '').trim()
  if (Object.prototype.hasOwnProperty.call(patch, 'recentFailureReason')) next.recentFailureReason = String(patch.recentFailureReason || '').trim()
  if (Object.prototype.hasOwnProperty.call(patch, 'recentUrls')) {
    next.recentUrls = Array.isArray(patch.recentUrls) ? patch.recentUrls.map((item) => String(item || '').trim()).filter(Boolean).slice(0, 5) : []
  }
  if (Object.prototype.hasOwnProperty.call(patch, 'taskMemory')) {
    next.taskMemory = normalizeAgentSessionMemory({ ...next, taskMemory: patch.taskMemory }).taskMemory
  }
  if (Object.prototype.hasOwnProperty.call(patch, 'taskHistory')) {
    next.taskHistory = normalizeAgentSessionMemory({ ...next, taskHistory: patch.taskHistory }).taskHistory
  }
  if (Object.prototype.hasOwnProperty.call(patch, 'accountHistory')) {
    next.accountHistory = normalizeAgentSessionMemory({ ...next, accountHistory: patch.accountHistory }).accountHistory
  }
  if (next.accountLocked && next.pinnedAccountId) {
    next.recentAccountId = next.pinnedAccountId
    if (next.pinnedDisplayName) next.recentDisplayName = next.pinnedDisplayName
  }
  if (options.clearFailure) next.recentFailureReason = ''
  next.updatedAt = Date.now()
  agentSessionMemory.value = next
}

function clearAgentSessionMemory() {
  agentSessionMemory.value = createEmptyAgentSessionMemory()
  persistAgentPanelState()
}

function toggleAgentAccountLock() {
  const memory = normalizeAgentSessionMemory(agentSessionMemory.value)
  if (memory.accountLocked && memory.pinnedAccountId) {
    updateAgentSessionMemory({ accountLocked: false, pinnedAccountId: '', pinnedDisplayName: '' })
    pushAgentLog('已解除账号上下文锁定，后续指令会继续根据最新观察刷新账号记忆。', 'info')
    persistAgentPanelState()
    return
  }

  const targetAccountId = String(crawlAccountId.value || memory.recentAccountId || '').trim()
  const targetDisplayName = String(selectedAccountDisplayName.value || memory.recentDisplayName || '').trim()
  if (!targetAccountId) {
    setAgentActionFeedback('warning', '无法锁定账号上下文', '当前没有可锁定的账号，请先执行一次账号匹配或抓取。')
    return
  }
  updateAgentSessionMemory({
    accountLocked: true,
    pinnedAccountId: targetAccountId,
    pinnedDisplayName: targetDisplayName,
    recentAccountId: targetAccountId,
    recentDisplayName: targetDisplayName || memory.recentDisplayName,
  })
  pushAgentLog(`已锁定账号上下文：${targetDisplayName || targetAccountId}。后续省略表达会优先落到这个账号。`, 'resolved')
  persistAgentPanelState()
}

function snapshotAgentPanelState() {
  return {
    command: '',
    running: !!agentRunning.value,
    statusText: agentRunning.value || agentDetachedRunning.value ? agentStatusText.value : '',
    logs: agentRunning.value || agentDetachedRunning.value ? (Array.isArray(agentLogs.value) ? agentLogs.value.slice(0, 40) : []) : [],
    feedback: agentRunning.value || agentDetachedRunning.value ? (agentActionFeedback.value ? { ...agentActionFeedback.value } : null) : null,
    orchestration: agentOrchestration.value ? JSON.parse(JSON.stringify(agentOrchestration.value)) : null,
    taskCard: agentTaskCard.value ? JSON.parse(JSON.stringify(agentTaskCard.value)) : null,
    brainState: agentBrainState.value ? { ...agentBrainState.value, planSteps: Array.isArray(agentBrainState.value.planSteps) ? [...agentBrainState.value.planSteps] : [] } : null,
    sessionMemory: buildAgentSessionMemoryPayload(),
    crawlAccountId: crawlAccountId.value,
    selectedHistoryUrl: selectedHistoryUrl.value,
    selectedAccountDisplayName: selectedAccountDisplayName.value,
    leaveNoticeShown: !!agentLeaveNoticeShown.value,
    detachedRunning: !!agentDetachedRunning.value,
    latestTargetArticle: latestAgentTargetArticle.value ? { ...latestAgentTargetArticle.value } : null,
    savedAt: Date.now(),
  }
}

function persistAgentPanelState() {
  try {
    localStorage.setItem(AGENT_PANEL_STATE_STORAGE_KEY, JSON.stringify(snapshotAgentPanelState()))
  } catch {
    // ignore storage quota errors for local UI state
  }
  queuePersistAgentServerState()
}

function restoreAgentPanelState() {
  try {
    const raw = localStorage.getItem(AGENT_PANEL_STATE_STORAGE_KEY) || sessionStorage.getItem(AGENT_PANEL_STATE_STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return

    const restoredRunning = !!parsed.running
    const restoredDetachedRunning = !!parsed.detachedRunning

    agentCommand.value = ''
    agentRunning.value = false
    agentStatusText.value = restoredRunning || restoredDetachedRunning ? String(parsed.statusText || '') : ''
    agentLogs.value = restoredRunning || restoredDetachedRunning ? (Array.isArray(parsed.logs) ? parsed.logs : []) : []
    agentActionFeedback.value = restoredRunning || restoredDetachedRunning
      ? (parsed.feedback && typeof parsed.feedback === 'object' ? parsed.feedback : null)
      : null
    agentOrchestration.value = normalizeAgentOrchestration(parsed.orchestration)
    agentTaskCard.value = parsed.taskCard && typeof parsed.taskCard === 'object' ? normalizeAgentTask(parsed.taskCard) : null
    latestAgentTargetArticle.value = parsed.latestTargetArticle && typeof parsed.latestTargetArticle === 'object'
      ? {
          account_id: String(parsed.latestTargetArticle.account_id || '').trim(),
          article_id: String(parsed.latestTargetArticle.article_id || '').trim(),
          title: String(parsed.latestTargetArticle.title || '').trim(),
        }
      : null
    agentBrainState.value = parsed.brainState && typeof parsed.brainState === 'object'
      ? {
          visible: !!parsed.brainState.visible,
          source: String(parsed.brainState.source || ''),
          sourceLabel: String(parsed.brainState.sourceLabel || ''),
          intent: String(parsed.brainState.intent || ''),
          intentLabel: String(parsed.brainState.intentLabel || ''),
          supported: parsed.brainState.supported !== false,
          message: String(parsed.brainState.message || ''),
          reply: String(parsed.brainState.reply || ''),
          title: String(parsed.brainState.title || ''),
          tone: String(parsed.brainState.tone || 'info'),
          planTitle: String(parsed.brainState.planTitle || ''),
          planSteps: Array.isArray(parsed.brainState.planSteps) ? parsed.brainState.planSteps.map((item) => String(item || '').trim()).filter(Boolean) : [],
          diagnostics: parsed.brainState.diagnostics && typeof parsed.brainState.diagnostics === 'object'
            ? {
                visible: !!parsed.brainState.diagnostics.visible,
                summary: String(parsed.brainState.diagnostics.summary || ''),
                detail: String(parsed.brainState.diagnostics.detail || ''),
                chips: Array.isArray(parsed.brainState.diagnostics.chips) ? parsed.brainState.diagnostics.chips.map((item) => String(item || '').trim()).filter(Boolean) : [],
                cards: Array.isArray(parsed.brainState.diagnostics.cards)
                  ? parsed.brainState.diagnostics.cards.map((item) => ({
                      title: String(item?.title || '').trim(),
                      value: String(item?.value || '').trim(),
                      note: String(item?.note || '').trim(),
                      tone: String(item?.tone || 'idle').trim(),
                    })).filter((item) => item.title || item.value || item.note)
                  : [],
                suggestions: Array.isArray(parsed.brainState.diagnostics.suggestions) ? parsed.brainState.diagnostics.suggestions.map((item) => String(item || '').trim()).filter(Boolean) : [],
              }
            : { visible: false, summary: '', detail: '', chips: [], cards: [], suggestions: [] },
        }
      : { visible: false, source: '', sourceLabel: '', intent: '', intentLabel: '', supported: true, message: '', reply: '', title: '', tone: 'info', planTitle: '', planSteps: [], diagnostics: { visible: false, summary: '', detail: '', chips: [], cards: [], suggestions: [] } }
    agentSessionMemory.value = normalizeAgentSessionMemory(parsed.sessionMemory)
    crawlAccountId.value = String(parsed.crawlAccountId || crawlAccountId.value || 'my_wechat_account')
    selectedHistoryUrl.value = String(parsed.selectedHistoryUrl || '')
    selectedAccountDisplayName.value = String(parsed.selectedAccountDisplayName || '')
    agentLeaveNoticeShown.value = !!parsed.leaveNoticeShown
    agentDetachedRunning.value = false
    agentLastSavedAt.value = Number(parsed.savedAt || 0)

    if (restoredRunning || restoredDetachedRunning) {
      agentRestoreNotice.value = {
        visible: true,
        title: '已恢复上次执行上下文',
        message: '检测到上次页面离开时曾处于执行中。当前只恢复任务上下文，不再自动回灌旧指令和旧日志，避免干扰新一轮操作。',
        command: '',
        tone: 'warning',
      }
    } else {
      agentRestoreNotice.value = { visible: false, title: '', message: '', command: '', tone: 'info' }
    }
  } catch {
    // ignore broken session payloads
  }
}

async function restoreAgentServerState() {
  try {
    const response = await wechatAnnotatorAPI.getAgentSessionState()
    const state = response?.data?.state
    if (!state || typeof state !== 'object') return
    const localRaw = localStorage.getItem(AGENT_PANEL_STATE_STORAGE_KEY) || sessionStorage.getItem(AGENT_PANEL_STATE_STORAGE_KEY)
    let localSavedAt = 0
    if (localRaw) {
      try {
        localSavedAt = Number((JSON.parse(localRaw) || {}).savedAt || 0)
      } catch {
        localSavedAt = 0
      }
    }
    if (Number(state.savedAt || 0) >= localSavedAt) {
      localStorage.setItem(AGENT_PANEL_STATE_STORAGE_KEY, JSON.stringify(state))
      restoreAgentPanelState()
    }
  } catch {
    // ignore server state restore failures and keep local fallback
  }
}

function queuePersistAgentServerState() {
  if (agentServerPersistTimer) {
    clearTimeout(agentServerPersistTimer)
  }
  const snapshot = snapshotAgentPanelState()
  agentServerPersistTimer = setTimeout(async () => {
    try {
      await wechatAnnotatorAPI.saveAgentSessionState(snapshot)
    } catch {
      // ignore server persistence failures and keep local fallback
    }
  }, 600)
}

function flushPersistAgentServerState() {
  if (agentServerPersistTimer) {
    clearTimeout(agentServerPersistTimer)
    agentServerPersistTimer = null
  }
  const snapshot = snapshotAgentPanelState()
  wechatAnnotatorAPI.saveAgentSessionState(snapshot).catch(() => {
    // ignore flush failures and keep local fallback
  })
}

async function clearAgentServerState() {
  try {
    await wechatAnnotatorAPI.clearAgentSessionState()
  } catch {
    // ignore server clear failures
  }
}

function buildReviewRouteQuery(accountId = '', articleId = '') {
  const nextQuery = { ...route.query, view: 'review' }
  if (accountId) nextQuery.account_id = accountId
  else delete nextQuery.account_id
  if (articleId) nextQuery.article_id = articleId
  else delete nextQuery.article_id
  return nextQuery
}

async function syncReviewRouteState(accountId = '', articleId = '', replace = false) {
  const nextQuery = buildReviewRouteQuery(accountId, articleId)
  const sameView = String(route.query.view || '') === String(nextQuery.view || '')
  const sameAccount = String(route.query.account_id || '') === String(nextQuery.account_id || '')
  const sameArticle = String(route.query.article_id || '') === String(nextQuery.article_id || '')
  if (sameView && sameAccount && sameArticle) return
  const target = { query: nextQuery }
  if (replace) {
    await router.replace(target)
    return
  }
  await router.push(target)
}

async function clearReviewRouteState(replace = true) {
  const nextQuery = { ...route.query }
  delete nextQuery.view
  delete nextQuery.account_id
  delete nextQuery.article_id
  if (!route.query.view && !route.query.account_id && !route.query.article_id) return
  const target = { query: nextQuery }
  if (replace) {
    await router.replace(target)
    return
  }
  await router.push(target)
}

function clearAgentPanelState() {
  agentStatusText.value = ''
  agentLogs.value = []
  agentActionFeedback.value = null
  agentOrchestration.value = null
  agentLastResult.value = null
  agentTaskCard.value = null
  agentTaskList.value = []
  agentTaskLoading.value = false
  agentTaskRetryingId.value = ''
  agentTaskDetailVisible.value = false
  agentTaskDetailTask.value = null
  agentTaskErrorExpanded.value = false
  agentBrainState.value = { visible: false, source: '', sourceLabel: '', intent: '', intentLabel: '', supported: true, message: '', reply: '', title: '', tone: 'info', planTitle: '', planSteps: [], diagnostics: { visible: false, summary: '', detail: '', chips: [], cards: [], suggestions: [] } }
  agentSessionMemory.value = createEmptyAgentSessionMemory()
  agentLastSavedAt.value = 0
  agentLeaveNoticeShown.value = false
  agentDetachedRunning.value = false
  agentRestoreNotice.value = { visible: false, title: '', message: '', command: '', tone: 'info' }
  try {
    localStorage.removeItem(AGENT_PANEL_STATE_STORAGE_KEY)
    sessionStorage.removeItem(AGENT_PANEL_STATE_STORAGE_KEY)
  } catch {
    // ignore storage errors
  }
  clearAgentServerState()
}

function dismissAgentRestoreNotice() {
  agentRestoreNotice.value = { visible: false, title: '', message: '', command: '', tone: 'info' }
}

function normalizeAgentIntentLabel(intent) {
  const value = String(intent || '').trim()
  if (!value) return '未标注'
  if (value === 'collect') return '抓取'
  if (value === 'clean') return '清洗'
  if (value === 'ingest') return '入库'
  if (value === 'collect_and_ingest') return '抓取并入库'
  if (value === 'clean_and_ingest') return '清洗并入库'
  if (value === 'desktop_collect') return '桌面采集'
  if (value === 'review') return '进入标注'
  if (value === 'unsupported') return '超出能力范围'
  return value
}

function formatAgentRoleName(value) {
  const name = String(value || '').trim()
  if (!name) return '未记录'
  if (name === 'knowledge_acquisition_agent') return '知识采集 Agent'
  if (name === 'knowledge_governance_agent') return '知识治理 Agent'
  if (name === 'evaluation_optimization_agent') return '评测优化 Agent'
  if (name === 'knowledge_orchestrator') return '知识编排器'
  return name
}

function formatAgentOrchestrationStatus(value) {
  const status = String(value || '').trim()
  if (!status) return '未知'
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'partial_success') return '部分成功'
  if (status === 'waiting_handoff') return '等待下一跳'
  if (status === 'running') return '执行中'
  return status
}

function formatAgentMetricScore(value) {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) return '--'
  return numeric.toFixed(2)
}

function normalizeAgentProtocol(payload) {
  const protocol = payload && typeof payload === 'object' ? payload : {}
  const agents = Array.isArray(protocol.agents)
    ? protocol.agents
      .map((item) => ({
        agentId: String(item?.agent_id || item?.agentId || '').trim(),
        title: String(item?.title || '').trim(),
        kicker: String(item?.kicker || '').trim(),
        defaultSummary: String(item?.default_summary || item?.defaultSummary || '').trim(),
        metricTemplates: item?.metric_templates && typeof item.metric_templates === 'object'
          ? Object.entries(item.metric_templates).reduce((acc, [key, value]) => {
            const normalizedKey = String(key || '').trim()
            const normalizedValue = String(value || '').trim()
            if (normalizedKey && normalizedValue) acc[normalizedKey] = normalizedValue
            return acc
          }, {})
          : {},
        summaryTemplates: item?.summary_templates && typeof item.summary_templates === 'object'
          ? Object.entries(item.summary_templates).reduce((acc, [key, value]) => {
            const normalizedKey = String(key || '').trim()
            const normalizedValue = String(value || '').trim()
            if (normalizedKey && normalizedValue) acc[normalizedKey] = normalizedValue
            return acc
          }, {})
          : {},
      }))
      .filter((item) => item.agentId)
    : []
  const handoffTemplates = Array.isArray(protocol.handoff_templates || protocol.handoffTemplates)
    ? (protocol.handoff_templates || protocol.handoffTemplates)
      .map((item) => ({
        handoffId: String(item?.handoff_id || item?.handoffId || '').trim(),
        fromAgent: String(item?.from_agent || item?.fromAgent || '').trim(),
        toAgent: String(item?.to_agent || item?.toAgent || '').trim(),
        title: String(item?.title || '').trim(),
        requiredInputs: Array.isArray(item?.required_inputs || item?.requiredInputs)
          ? (item?.required_inputs || item?.requiredInputs).map((entry) => String(entry || '').trim()).filter(Boolean)
          : [],
        inputRules: normalizeProtocolInputRules(item?.input_rules || item?.inputRules),
        fallbackSummary: String(item?.fallback_summary || item?.fallbackSummary || '').trim(),
      }))
      .filter((item) => item.fromAgent && item.toAgent)
    : []
  return {
    version: String(protocol.version || '').trim(),
    orchestrator: String(protocol.orchestrator || '').trim(),
    agents,
    handoffTemplates,
  }
}

function getProtocolAgentDefinition(protocol, agentId) {
  const agents = Array.isArray(protocol?.agents) ? protocol.agents : []
  return agents.find((item) => item.agentId === agentId) || null
}

function formatProtocolSummary(protocol, agentId, key, replacements = {}, fallback = '') {
  const agent = getProtocolAgentDefinition(protocol, agentId)
  const template = String(agent?.summaryTemplates?.[key] || '').trim() || String(agent?.defaultSummary || '').trim() || String(fallback || '').trim()
  return template.replace(/\{(\w+)\}/g, (_, token) => {
    const value = replacements[token]
    return value === undefined || value === null || value === '' ? '--' : String(value)
  })
}

function formatProtocolMetric(protocol, agentId, key, value, fallback = '') {
  if (value === undefined || value === null || value === '') return ''
  const agent = getProtocolAgentDefinition(protocol, agentId)
  const template = String(agent?.metricTemplates?.[key] || '').trim() || String(fallback || '').trim()
  if (!template) return String(value)
  return template.replace(/\{value\}/g, String(value))
}

function normalizeProtocolInputRules(value) {
  return Array.isArray(value)
    ? value
      .map((item) => ({
        input: String(item?.input || '').trim(),
        always: item?.always === true,
        artifactTypesAny: Array.isArray(item?.artifact_types_any || item?.artifactTypesAny)
          ? (item?.artifact_types_any || item?.artifactTypesAny).map((entry) => String(entry || '').trim()).filter(Boolean)
          : [],
      }))
      .filter((item) => item.input)
    : []
}

function isProtocolInputReady(rule, artifactTypes) {
  if (!rule || typeof rule !== 'object') return true
  if (rule.always) return true
  if (Array.isArray(rule.artifactTypesAny) && rule.artifactTypesAny.length) {
    return rule.artifactTypesAny.some((artifactType) => artifactTypes.includes(artifactType))
  }
  return true
}

function normalizeAgentOrchestration(payload) {
  if (!payload || typeof payload !== 'object') return null
  const task = payload.task && typeof payload.task === 'object' ? payload.task : {}
  const review = payload.review && typeof payload.review === 'object' ? payload.review : {}
  const governance = payload.governance && typeof payload.governance === 'object' ? payload.governance : null
  const artifacts = Array.isArray(payload.artifacts) ? payload.artifacts.filter((item) => item && typeof item === 'object') : []
  const governanceArtifact = artifacts.find((item) => String(item.artifact_type || '').trim() === 'governance_report') || null
  const evaluationArtifact = artifacts.find((item) => String(item.artifact_type || '').trim() === 'evaluation_report') || null
  const evaluationMetrics = evaluationArtifact && evaluationArtifact.metrics && typeof evaluationArtifact.metrics === 'object' ? evaluationArtifact.metrics : {}
  const ragasMetrics = evaluationMetrics.ragas_metrics && typeof evaluationMetrics.ragas_metrics === 'object' ? evaluationMetrics.ragas_metrics : {}
  const evaluationSnapshot = evaluationMetrics.evaluation_snapshot && typeof evaluationMetrics.evaluation_snapshot === 'object' ? evaluationMetrics.evaluation_snapshot : {}
  const parseOptionalNumber = (value) => {
    const numeric = Number(value)
    return Number.isFinite(numeric) ? numeric : null
  }
  return {
    version: String(payload.version || '').trim(),
    orchestrator: String(payload.orchestrator || '').trim(),
    protocol: normalizeAgentProtocol(payload.protocol),
    task: {
      taskId: String(task.task_id || '').trim(),
      traceId: String(task.trace_id || '').trim(),
      goal: String(task.goal || '').trim(),
      status: String(task.status || '').trim(),
      currentAgent: String(task.current_agent || '').trim(),
    },
    route: Array.isArray(task.route) ? task.route.map((item) => String(item || '').trim()).filter(Boolean) : [],
    nextAgent: String(payload.next_agent || '').trim(),
    completedAgents: Array.isArray(payload.completed_agents) ? payload.completed_agents.map((item) => String(item || '').trim()).filter(Boolean) : [],
    handoffs: Array.isArray(payload.handoffs)
      ? payload.handoffs
        .map((item) => ({
          fromAgent: String(item?.from_agent || '').trim(),
          toAgent: String(item?.to_agent || '').trim(),
          handoffReason: String(item?.handoff_reason || '').trim(),
          requiredInputs: Array.isArray(item?.required_inputs) ? item.required_inputs.map((entry) => String(entry || '').trim()).filter(Boolean) : [],
          blocking: item?.blocking !== false,
          deadlineSec: Number(item?.deadline_sec || 0),
        }))
        .filter((item) => item.fromAgent || item.toAgent)
      : [],
    artifactTypes: artifacts.map((item) => String(item?.artifact_type || '').trim()).filter(Boolean),
    review: {
      outcome: String(review.outcome || '').trim(),
      summary: String(review.summary || '').trim(),
      failureReason: String(review.failure_reason || '').trim(),
      recommendedNextActions: Array.isArray(review.recommended_next_actions) ? review.recommended_next_actions.map((item) => String(item || '').trim()).filter(Boolean) : [],
    },
    governance: governance || governanceArtifact
      ? {
          status: String((governance || {}).status || review.outcome || '').trim(),
          summary: String((governanceArtifact || {}).summary || (governance || {}).error || '').trim(),
          riskLevel: String((((governance || {}).report || {}).risk_level) || (((governanceArtifact || {}).metrics || {}).risk_level) || '').trim(),
        }
      : null,
    evaluation: evaluationArtifact
      ? {
          summary: String(evaluationArtifact.summary || '').trim(),
          readiness: String((evaluationArtifact.metrics || {}).readiness || '').trim(),
          qualityScore: Number((evaluationArtifact.metrics || {}).quality_score || 0),
          coverageScore: Number((evaluationArtifact.metrics || {}).coverage_score || 0),
          ragasAverage: parseOptionalNumber(evaluationMetrics.ragas_average),
          faithfulness: parseOptionalNumber(ragasMetrics.faithfulness),
          contextPrecision: parseOptionalNumber(ragasMetrics.context_precision),
          contextRecall: parseOptionalNumber(ragasMetrics.context_recall),
          responseRelevancy: parseOptionalNumber(ragasMetrics.response_relevancy),
          sampleCount: Number(evaluationSnapshot.sample_count || 0),
          snapshotLabel: [String(evaluationSnapshot.file_name || '').trim(), String(evaluationSnapshot.evaluated_at || '').trim()].filter(Boolean).join(' · '),
        }
      : null,
  }
}

function formatAgentDecisionLabel(action) {
  const value = String(action || '').trim()
  if (!value) return '未记录'
  if (value === 'crawl_history_url') return '优先历史页抓取'
  if (value === 'crawl_seed_urls') return '直抓详情页/种子链接'
  if (value === 'desktop_capture') return '回退到桌面微信采集'
  if (value === 'request_user_intervention') return '请求人工介入'
  if (value === 'skip_collect') return '跳过抓取'
  return value
}

function formatHandoffReason(reason) {
  const value = String(reason || '').trim()
  if (!value) return '未记录原因'
  if (value === 'new_knowledge_created') return '已形成新知识资产'
  if (value === 'governance_report_ready') return '治理报告已就绪'
  return value
}

function formatRequiredInputLabel(value) {
  const input = String(value || '').trim()
  if (!input) return '未记录输入'
  if (input === 'created_articles') return '新文章记录'
  if (input === 'clean_result') return '清洗结果'
  if (input === 'shared_context') return '共享上下文'
  if (input === 'governance_report') return '治理报告'
  return input
}

function formatBrainFallbackReason(reason) {
  const value = String(reason || '').trim()
  if (!value) return '未回退'
  if (value === 'llm_unconfigured') return '未配置可用 LLM'
  if (value === 'llm_client_unavailable') return 'LLM 客户端不可用'
  if (value === 'llm_empty_response') return 'LLM 返回空结果'
  if (value === 'llm_invalid_json') return 'LLM 返回结果不可解析'
  if (value === 'llm_request_failed') return 'LLM 请求失败'
  if (value === 'help_query_short_circuit') return '帮助类问题被短路'
  if (value === 'domain_signal_rule_override') return '规则检测到领域信号并强制继续'
  if (value === 'rule_path') return '当前走规则路径'
  return value
}

function resolveSimplePathDependencyLevel({ source, configured, attempted, succeeded, fallbackReason }) {
  if (source === 'llm' && succeeded) {
    return { label: '低', note: '当前主判断由模型完成，最简规则路径不是主链路。', tone: 'success' }
  }
  if (!configured || fallbackReason === 'llm_unconfigured') {
    return { label: '高', note: '当前没有可用模型配置，入口判断明显依赖最简规则方案。', tone: 'danger' }
  }
  if (attempted && !succeeded) {
    return { label: '高', note: '模型链路已尝试但未稳定返回，当前仍严重依赖规则兜底。', tone: 'danger' }
  }
  return { label: '中', note: '当前有模型条件，但本轮仍存在规则兜底或规则强制继续。', tone: 'warning' }
}

function getBrainDiagnosticHistoryItem(parsed, source) {
  const raw = parsed?.brain_diagnostics && typeof parsed.brain_diagnostics === 'object' ? parsed.brain_diagnostics : {}
  const fallbackReason = String(raw?.fallback_reason || '').trim()
  const fallbackReasonLabel = formatBrainFallbackReason(fallbackReason)
  const dependencyLevel = resolveSimplePathDependencyLevel({
    source,
    configured: raw?.configured === true,
    attempted: raw?.attempted === true,
    succeeded: raw?.succeeded === true,
    fallbackReason,
  })
  return {
    source,
    succeeded: raw?.succeeded === true,
    configured: raw?.configured === true,
    attempted: raw?.attempted === true,
    fallbackReason,
    fallbackReasonLabel,
    dependencyLevel: dependencyLevel.label,
    intent: String(parsed?.intent_label || '').trim(),
    recordedAt: Date.now(),
  }
}

function persistBrainDiagnosticHistory() {
  try {
    sessionStorage.setItem(BRAIN_DIAGNOSTIC_HISTORY_STORAGE_KEY, JSON.stringify(brainDiagnosticHistory.value.slice(0, 12)))
  } catch {
    // ignore storage quota errors for transient diagnostic history
  }
}

function restoreBrainDiagnosticHistory() {
  try {
    const raw = localStorage.getItem(BRAIN_DIAGNOSTIC_HISTORY_STORAGE_KEY) || sessionStorage.getItem(BRAIN_DIAGNOSTIC_HISTORY_STORAGE_KEY)
    if (!raw) return
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return
    brainDiagnosticHistory.value = parsed
      .map((item) => ({
        source: String(item?.source || '').trim(),
        succeeded: item?.succeeded === true,
        configured: item?.configured === true,
        attempted: item?.attempted === true,
        fallbackReason: String(item?.fallbackReason || '').trim(),
        fallbackReasonLabel: String(item?.fallbackReasonLabel || '').trim(),
        dependencyLevel: String(item?.dependencyLevel || '').trim(),
        intent: String(item?.intent || '').trim(),
        recordedAt: Number(item?.recordedAt || 0),
      }))
      .filter((item) => item.source || item.fallbackReasonLabel)
      .slice(0, 12)
  } catch {
    // ignore broken session payloads
  }
}

function appendBrainDiagnosticHistory(parsed, source) {
  const nextItem = getBrainDiagnosticHistoryItem(parsed, source)
  brainDiagnosticHistory.value = [nextItem, ...brainDiagnosticHistory.value].slice(0, 12)
  persistBrainDiagnosticHistory()
}

function clearBrainDiagnosticHistory() {
  brainDiagnosticHistory.value = []
  try {
    localStorage.removeItem(BRAIN_DIAGNOSTIC_HISTORY_STORAGE_KEY)
    sessionStorage.removeItem(BRAIN_DIAGNOSTIC_HISTORY_STORAGE_KEY)
  } catch {
    // ignore session storage errors
  }
}

async function loadEvaluationTrendHistory() {
  evaluationTrendLoading.value = true
  try {
    const res = await wechatAnnotatorAPI.getEvaluationHistory(30)
    evaluationTrendHistory.value = Array.isArray(res?.data?.history) ? res.data.history : []
    const latestAccountId = String((evaluationTrendHistory.value[0] || {}).account_id || '').trim()
    await loadEvaluationCompare(latestAccountId)
  } catch {
    evaluationTrendHistory.value = []
    evaluationCompare.value = null
  } finally {
    evaluationTrendLoading.value = false
  }
}

async function loadEvaluationCompare(accountId = '') {
  evaluationCompareLoading.value = true
  try {
    const res = await wechatAnnotatorAPI.getEvaluationHistoryCompare(accountId)
    evaluationCompare.value = res?.data && typeof res.data === 'object' ? res.data : null
  } catch {
    evaluationCompare.value = null
  } finally {
    evaluationCompareLoading.value = false
  }
}

async function rerunLatestEvaluationHistory() {
  const historyId = String((evaluationTrendSummary.value.latest || {}).history_id || '').trim()
  if (!historyId) {
    setAgentActionFeedback('warning', '无法重跑评测', '当前没有可重跑的历史评测记录。')
    return
  }
  evaluationRerunHistoryId.value = historyId
  try {
    const response = await wechatAnnotatorAPI.rerunEvaluationHistory(historyId)
    const result = response?.data?.result || {}
    await loadEvaluationTrendHistory()
    setAgentActionFeedback(
      'success',
      '评测已重跑',
      `最新结果：就绪度 ${String(result?.evaluation?.readiness || 'unknown')}，质量 ${Number(result?.evaluation?.quality_score || 0)}，覆盖 ${Number(result?.evaluation?.coverage_score || 0)}。`,
    )
  } catch (error) {
    setAgentActionFeedback('error', '评测重跑失败', error?.response?.data?.detail || error?.message || '请稍后重试。')
  } finally {
    evaluationRerunHistoryId.value = ''
  }
}

function buildAgentBrainDiagnostics(parsed, source, sourceLabel) {
  const raw = parsed?.brain_diagnostics && typeof parsed.brain_diagnostics === 'object' ? parsed.brain_diagnostics : {}
  const signalSummary = raw?.signal_summary && typeof raw.signal_summary === 'object' ? raw.signal_summary : {}
  const configured = raw?.configured === true
  const attempted = raw?.attempted === true
  const succeeded = raw?.succeeded === true
  const fallbackReason = formatBrainFallbackReason(raw?.fallback_reason)
  const dependencyLevel = resolveSimplePathDependencyLevel({
    source,
    configured,
    attempted,
    succeeded,
    fallbackReason: String(raw?.fallback_reason || '').trim(),
  })
  const chips = [
    configured ? 'LLM 已配置' : 'LLM 未配置',
    attempted ? '已尝试模型判断' : '未尝试模型判断',
    succeeded ? '模型判断成功' : '',
    Number(signalSummary?.url_count || 0) > 0 ? `公众号链接 ${Number(signalSummary.url_count)} 条` : '',
    signalSummary?.has_search_query ? '带公众号搜索词' : '',
    signalSummary?.has_article_title ? '带文章标题' : '',
    raw?.continuation_mode ? '续跑模式' : '',
    raw?.domain_signal_detected ? '命中公众号领域信号' : '',
  ].filter(Boolean)

  let summary = `${sourceLabel}正在负责入口判断。`
  let detail = ''
  if (source === 'llm' && succeeded) {
    summary = `当前由 ${sourceLabel} 直接完成意图判断，没有回退到规则。`
    detail = raw?.model ? `当前模型：${raw.model}${raw?.base_url ? `，服务端点 ${raw.base_url}` : ''}。` : ''
  } else if (attempted) {
    summary = `当前没有拿到稳定的模型判断结果，系统改走规则回退。原因：${fallbackReason}。`
    detail = raw?.error ? `最近异常：${raw.error}` : ''
  } else if (!configured) {
    summary = '当前没有可用的模型配置，所以直接走规则判断。'
    detail = raw?.model ? `当前模型字段：${raw.model}` : ''
  } else {
    summary = `当前走规则判断。原因：${fallbackReason}。`
  }

  const cards = [
    {
      title: '模型链路',
      value: source === 'llm' && succeeded ? '主判断生效' : (attempted ? '已尝试但未稳定生效' : '未参与本轮判断'),
      note: configured
        ? (raw?.model ? `模型 ${raw.model}` : '已具备模型配置')
        : '当前缺少可用模型配置',
      tone: source === 'llm' && succeeded ? 'success' : (attempted ? 'warning' : 'idle'),
    },
    {
      title: '规则兜底',
      value: source === 'llm' && succeeded ? '本轮未接管' : fallbackReason,
      note: source === 'llm' && succeeded ? '规则仍保留，但当前不是主决策来源。' : '这里只显示本轮实际回退原因。',
      tone: source === 'llm' && succeeded ? 'success' : (attempted || !configured ? 'warning' : 'idle'),
    },
    {
      title: '领域信号',
      value: raw?.domain_signal_detected ? '已命中公众号域信号' : '未命中明显域信号',
      note: [
        Number(signalSummary?.url_count || 0) > 0 ? `链接 ${Number(signalSummary.url_count)} 条` : '',
        signalSummary?.has_search_query ? '含搜索词' : '',
        signalSummary?.has_article_title ? '含文章标题' : '',
      ].filter(Boolean).join('，') || '本轮没有明显的公众号任务线索。',
      tone: raw?.domain_signal_detected ? 'success' : 'idle',
    },
    {
      title: '最简方案依赖',
      value: dependencyLevel.label,
      note: dependencyLevel.note,
      tone: dependencyLevel.tone,
    },
  ]

  const suggestions = []
  if (!configured) {
    suggestions.push('补齐 GENERAL_API_KEY、GENERAL_BASE_URL 和 GENERAL_LLM_MODEL，让入口判断先具备稳定模型主链路。')
  }
  if (attempted && !succeeded) {
    suggestions.push('记录并对比 llm_request_failed、llm_empty_response、llm_invalid_json 三类失败占比，先把回退原因量化。')
  }
  if (raw?.domain_signal_detected && source !== 'llm') {
    suggestions.push('对命中公众号领域信号却仍走规则的样本做专项回放，优先降低这类高价值样本的规则依赖。')
  }
  if (!raw?.domain_signal_detected) {
    suggestions.push('补更细的领域信号特征，例如链接类型、账号词、历史页词和续跑词，避免入口判断过早掉到帮助类或空意图。')
  }
  if (source === 'llm' && succeeded) {
    suggestions.push('下一步应统计模型判断与规则回退的真实占比，而不是继续凭体感判断是否依赖最简方案。')
  }

  return {
    visible: configured || attempted || !!raw?.fallback_reason || !!raw?.domain_signal_detected,
    summary,
    detail,
    chips,
    cards,
    suggestions,
  }
}

function buildAgentBrainState(parsed) {
  const source = String(parsed?.brain_source || 'rules').trim() || 'rules'
  const supported = parsed?.capability_supported !== false
  const sourceLabel = source === 'llm' ? 'LLM 大脑' : '规则回退'
  const intent = String(parsed?.intent_label || '').trim()
  const intentLabel = normalizeAgentIntentLabel(intent)
  const message = String(parsed?.capability_message || '').trim()
  const reply = String(parsed?.assistant_reply || '').trim()
  const executionPlan = Array.isArray(parsed?.execution_plan)
    ? parsed.execution_plan.filter((item) => item && item.enabled !== false).map((item) => String(item.title || item.name || '').trim()).filter(Boolean)
    : []
  const planSteps = supported
    ? (executionPlan.length ? executionPlan : (Array.isArray(parsed?.plan_outline) ? parsed.plan_outline.map((item) => String(item || '').trim()).filter(Boolean) : []))
    : []
  const diagnostics = buildAgentBrainDiagnostics(parsed, source, sourceLabel)
  return {
    visible: true,
    source,
    sourceLabel,
    intent,
    intentLabel,
    supported,
    message: reply || message || (supported ? '这条指令已经完成解析，后续只会按真实执行结果更新。' : '当前 Agent 只支持公众号相关工作。'),
    reply,
    title: supported ? `大脑解析完成：${intentLabel}` : '当前页能力说明',
    tone: supported ? (source === 'llm' ? 'success' : 'warning') : 'warning',
    planTitle: supported ? '待执行计划' : '',
    planSteps,
    diagnostics,
  }
}

function hasAgentExecutionSteps(data) {
  const steps = Array.isArray(data?.steps) ? data.steps : []
  return steps.some((step) => ['collect', 'desktop_collect', 'clean'].includes(String(step?.name || '')))
}

function restorePreviousAgentCommand() {
  if (agentSessionMemory.value?.taskMemory?.command) {
    agentCommand.value = agentSessionMemory.value.taskMemory.command
  }
}

function buildTaskArticlePreview(task, limit = 2) {
  return listTaskArticleEntries(task)
    .map((entry) => String(entry?.title || '').trim())
    .filter(Boolean)
    .slice(0, limit)
}

async function openLatestAgentTargetArticle() {
  if (!latestAgentTargetArticle.value?.account_id || !latestAgentTargetArticle.value?.article_id) {
    ElMessage.warning('当前没有可直接打开的文章')
    return
  }
  const target = findArticleByIds(latestAgentTargetArticle.value.account_id, latestAgentTargetArticle.value.article_id)
  if (!target) {
    ElMessage.warning('本地文章列表里暂时还没定位到这篇文章')
    return
  }
  await selectArticle(target)
}

async function saveBlobToUserPath(blob, suggestedName) {
  if (window.showSaveFilePicker) {
    const ext = suggestedName.includes('.') ? suggestedName.slice(suggestedName.lastIndexOf('.')) : ''
    const picker = await window.showSaveFilePicker({
      suggestedName,
      types: [
        {
          description: '下载文件',
          accept: {
            [blob.type || 'application/octet-stream']: ext ? [ext] : ['.bin'],
          },
        },
      ],
    })
    const writable = await picker.createWritable()
    await writable.write(blob)
    await writable.close()
    return 'custom-path'
  }

  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = suggestedName
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
  return 'browser-default'
}

function normalizeArticleDetail(payload) {
  const detail = { ...payload }
  detail.images = (detail.images || []).map((img) => ({
    ...img,
    scene_annotation_text: String(img.scene_annotation_text || '').trim(),
    manual_tags_text: Array.isArray(img.manual_tags) ? img.manual_tags.join(', ') : '',
  }))
  return detail
}

function buildAnnotationVersion(detail, lastInstruction = '') {
  const images = (detail?.images || []).map((img) => ({
    image_id: img.image_id,
    local_path: img.local_path,
    manual_summary: img.manual_summary || '',
    manual_tags: Array.isArray(img.manual_tags) ? [...img.manual_tags] : String(img.manual_tags_text || '').split(/[，,]/).map((t) => t.trim()).filter(Boolean),
    manual_notes: img.manual_notes || '',
    scene_annotation_text: String(img.scene_annotation_text || '').trim(),
    keep_for_index: !!img.keep_for_index,
  }))
  return JSON.stringify({
    article_id: detail?.article?.article_id || '',
    account_id: detail?.article?.account_id || '',
    last_instruction: String(lastInstruction || '').trim(),
    annotations: images,
  })
}

function clearSelection(message = '') {
  selectedKey.value = ''
  articleDetail.value = null
  showArticleBody.value = false
  if (message) {
    ElMessage.warning(message)
  }
}

async function loadArticles(options = {}) {
  const normalized = typeof options === 'boolean'
    ? { keepSelected: options, autoSelectFirst: true }
    : { keepSelected: true, autoSelectFirst: true, ...options }
  const res = await wechatAnnotatorAPI.listArticles()
  articleGroups.value = res.data.accounts || []
  const first = flatArticles.value[0]
  if ((!normalized.keepSelected || !selectedKey.value || !flatArticles.value.some((item) => `${item.account_id}:${item.article_id}` === selectedKey.value)) && normalized.autoSelectFirst) {
    if (first) {
      await selectArticle(first)
    }
  }
}

async function searchWechatAccounts(showAll = false) {
  const keyword = showAll ? '' : (crawlAccountQuery.value.trim() || crawlAccountId.value.trim())
  if (!showAll && !keyword) {
    setAccountSearchFeedback('warning', '无法匹配本地账号', '请输入本地公众号名称或账号ID，或点击“查看全部”。')
    return
  }
  accountSearchFeedback.value = null
  accountSearchLoading.value = true
  try {
    const res = await wechatAnnotatorAPI.searchAccounts(keyword)
    accountCandidates.value = res?.data?.accounts || []
    if (!accountCandidates.value.length) {
      selectedHistoryUrl.value = ''
      selectedAccountDisplayName.value = ''
      setAccountSearchFeedback('warning', showAll ? '当前没有本地账号' : '没有找到本地匹配账号', showAll ? '还没有任何已沉淀到本地 source.json 或本地抓取目录的公众号账号。' : '系统只会搜索 source.json 和本地已抓取文章作者名，请检查关键词是否过短或别名是否不同。')
      return
    }
    if (!showAll && accountCandidates.value.length === 1) {
      applyAccountCandidate(accountCandidates.value[0])
    } else {
      setAccountSearchFeedback('success', showAll ? '已加载全部本地账号' : '已找到本地候选账号', `共 ${accountCandidates.value.length} 个候选账号，请点击一个条目确认使用。`)
    }
  } catch (err) {
    setAccountSearchFeedback('error', '本地账号匹配失败', err?.response?.data?.detail || '请稍后重试。')
  } finally {
    accountSearchLoading.value = false
  }
}

async function loadLocalAccountOverview() {
  localAccountOverviewLoading.value = true
  try {
    const res = await wechatAnnotatorAPI.searchAccounts('')
    const nextOverview = Array.isArray(res?.data?.accounts) ? res.data.accounts.slice(0, 8) : []
    localAccountOverview.value = nextOverview
    persistLocalAccountOverviewCache(nextOverview)
  } catch {
    restoreLocalAccountOverviewCache()
  } finally {
    localAccountOverviewLoading.value = false
  }
}

async function copyTextToClipboard(text, successMessage = '已复制', errorMessage = '复制失败，请手动复制') {
  const value = String(text || '').trim()
  if (!value) return false
  try {
    if (navigator.clipboard?.writeText) {
      await navigator.clipboard.writeText(value)
    } else {
      const textarea = document.createElement('textarea')
      textarea.value = value
      textarea.style.position = 'fixed'
      textarea.style.opacity = '0'
      document.body.appendChild(textarea)
      textarea.focus()
      textarea.select()
      document.execCommand('copy')
      document.body.removeChild(textarea)
    }
    if (successMessage) ElMessage.success(successMessage)
    return true
  } catch {
    if (errorMessage) ElMessage.error(errorMessage)
    return false
  }
}

async function copyHistoryUrl(item, event) {
  event?.stopPropagation?.()
  const historyUrl = String((item?.history_urls || [])[0] || '').trim()
  if (!historyUrl) {
    ElMessage.warning('该账号当前没有可复制的历史页链接')
    return
  }
  await copyTextToClipboard(historyUrl, '已复制历史页链接', '复制失败，请手动复制该链接')
}

function applyAccountCandidate(item) {
  crawlAccountId.value = item.account_id || crawlAccountId.value
  selectedHistoryUrl.value = (item.history_urls || [])[0] || ''
  selectedAccountDisplayName.value = item.preferred_name || item.display_name || item.account_id || ''
  crawlAccountQuery.value = item.preferred_name || item.display_name || item.account_id || crawlAccountQuery.value
  if (selectedHistoryUrl.value) {
    setAccountSearchFeedback('success', '已选择本地账号', `${selectedAccountDisplayName.value || crawlAccountId.value}，且已带出历史页记录。`)
  } else {
    setAccountSearchFeedback('warning', '已选择本地账号', '该账号没有本地历史页记录，但仍可直接粘贴公众号链接抓取。')
  }
}

async function openLocalAccountOverviewItem(item) {
  applyAccountCandidate(item)
  activeAnnotatorAccountId.value = String(item?.account_id || '').trim()
  activeAnnotatorPublisherName.value = resolveOverviewPublisherName(item)
  showReviewWorkspace.value = true
  await syncReviewRouteState(activeAnnotatorAccountId.value, '', false)
  const target = annotatorArticles.value[0] || null
  if (target) {
    await selectArticle(target)
    return
  }
  clearSelection('该账号当前还没有可展开的历史文章，只完成了账号沉淀。')
}

function clearAnnotatorAccountScope() {
  activeAnnotatorPublisherName.value = ''
}

function pushDesktopLog(message, status = 'info') {
  desktopLogs.value = [
    {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      status,
      message,
    },
    ...desktopLogs.value,
  ].slice(0, 60)
}

function setDesktopActionFeedback(type, title, message = '') {
  desktopActionFeedback.value = { type, title, message }
}

async function refreshDesktopProfiles() {
  desktopContextLoading.value = true
  try {
    const res = await wechatAnnotatorAPI.listDesktopProfiles(desktopOperatorId.value.trim())
    desktopProfiles.value = res?.data?.profiles || []
    if (desktopProfileName.value && !desktopProfiles.value.some((item) => item.profile_name === desktopProfileName.value)) {
      desktopProfileName.value = ''
    }
    if (desktopProfiles.value.length) {
      setDesktopActionFeedback('success', '桌面 profile 已更新', `当前共 ${desktopProfiles.value.length} 个可选 profile。`)
    } else {
      setDesktopActionFeedback('warning', '未找到桌面 profile', '当前 operator_id 下还没有可用 profile，可直接填写参数后启动一次采集。')
    }
  } catch (err) {
    setDesktopActionFeedback('error', '读取桌面 profile 失败', err?.response?.data?.detail || '请确认后端服务、operator_id 和桌面端配置是否可用。')
  } finally {
    desktopContextLoading.value = false
  }
}

function applyDesktopProfile(profileName) {
  const target = desktopProfiles.value.find((item) => item.profile_name === profileName)
  if (!target) return
  desktopProfileName.value = target.profile_name || profileName
  desktopAccountId.value = target.account_id || desktopAccountId.value
  desktopDisplayName.value = target.display_name || desktopDisplayName.value
  desktopSearchQuery.value = target.search_query || desktopSearchQuery.value
  desktopArticleTitle.value = target.article_title || desktopArticleTitle.value
  desktopSourceUrl.value = target.last_source_url || desktopSourceUrl.value
  desktopWechatPath.value = target.wechat_path || desktopWechatPath.value
  desktopWindowTitleRe.value = target.window_title_re || desktopWindowTitleRe.value || '.*微信.*'
  desktopCaptureSteps.value = Number(target.steps || desktopCaptureSteps.value || 6)
  desktopWaitSec.value = Number(target.wait_sec || desktopWaitSec.value || 0)
  desktopSettleDelaySec.value = Number(target.settle_delay_sec || desktopSettleDelaySec.value || 1)
  crawlAccountId.value = target.account_id || crawlAccountId.value
}

async function deleteDesktopProfileEntry() {
  const profileName = desktopProfileName.value.trim()
  if (!profileName) return
  if (!window.confirm(`确认删除桌面 profile：${profileName} ？`)) return
  try {
    const res = await wechatAnnotatorAPI.deleteDesktopProfile(profileName, desktopOperatorId.value.trim())
    desktopProfiles.value = res?.data?.profiles || []
    desktopProfileName.value = ''
    setDesktopActionFeedback('success', '已删除桌面 profile', profileName)
  } catch (err) {
    setDesktopActionFeedback('error', '删除桌面 profile 失败', err?.response?.data?.detail || '请稍后重试。')
  }
}

async function runDesktopCaptureFromUI() {
  const accountId = (desktopAccountId.value || crawlAccountId.value).trim()
  if (!accountId) {
    setDesktopActionFeedback('warning', '无法启动桌面采集', '请输入采集归属账号ID。')
    return
  }
  if (!desktopSearchQuery.value.trim() && !desktopProfileName.value.trim()) {
    setDesktopActionFeedback('warning', '无法启动桌面采集', '请先输入公众号搜索词，或选择历史 profile。')
    return
  }

  desktopActionFeedback.value = null
  desktopCaptureLoading.value = true
  desktopStatusText.value = '正在启动桌面端自动采集…'
  desktopLastCaptureSummary.value = ''
  desktopLogs.value = []
  desktopCaptureAbortController.value = new AbortController()
  try {
    let finalPayload = null
    await streamWechatDesktopCapture({
      operator_id: desktopOperatorId.value.trim(),
      profile_name: desktopProfileName.value.trim(),
      account_id: accountId,
      display_name: desktopDisplayName.value.trim() || selectedAccountDisplayName.value.trim() || accountId,
      source_url: desktopSourceUrl.value.trim(),
      search_query: desktopSearchQuery.value.trim(),
      article_title: desktopArticleTitle.value.trim(),
      wechat_path: desktopWechatPath.value.trim(),
      window_title_re: desktopWindowTitleRe.value.trim() || '.*微信.*',
      steps: Number(desktopCaptureSteps.value || 6),
      wait_sec: Number(desktopWaitSec.value || 0),
      settle_delay_sec: Number(desktopSettleDelaySec.value || 1),
      launch_timeout_sec: Number(desktopLaunchTimeoutSec.value || 25),
      auto_scroll: !!desktopAutoScroll.value,
      skip_history: !!desktopSkipHistory.value,
      import_after_capture: !!desktopImportAfterCapture.value,
      clean_after_import: !!desktopCleanAfterImport.value,
      ingest_after_import: !!desktopIngestAfterImport.value,
      force_import: true,
      remember: true,
    }, {
      onLoading: (event) => {
        desktopStatusText.value = event?.message || '正在启动桌面端自动采集…'
        pushDesktopLog(desktopStatusText.value, 'loading')
      },
      onDesktopReady: (event) => {
        desktopStatusText.value = `已连接微信窗口：${event?.window_title || '微信'}`
        pushDesktopLog(desktopStatusText.value, 'success')
      },
      onChatSelected: (event) => {
        pushDesktopLog(`已选中公众号会话：${event?.search_query || desktopSearchQuery.value}`, 'success')
      },
      onHistoryOpened: (event) => {
        pushDesktopLog(`已打开历史入口：${event?.entry_label || '历史消息'}`, 'success')
      },
      onArticleOpened: (event) => {
        pushDesktopLog(`已打开文章：${event?.article_title || desktopArticleTitle.value}`, 'success')
      },
      onCaptureStarted: (event) => {
        desktopStatusText.value = `开始采集，共 ${event?.total_steps || desktopCaptureSteps.value} 步`
        pushDesktopLog(desktopStatusText.value, 'resolved')
      },
      onAutoScrolled: (event) => {
        pushDesktopLog(`第 ${event?.step || '?'} 步自动翻页，驱动=${event?.scroll_driver || 'page_down'}`, 'info')
      },
      onCaptureStep: (event) => {
        desktopStatusText.value = `已完成截图 ${event?.step || 0}/${event?.total || desktopCaptureSteps.value}`
        pushDesktopLog(`截图完成：第 ${event?.step || 0}/${event?.total || desktopCaptureSteps.value} 步`, 'success')
      },
      onProfileSaved: (event) => {
        pushDesktopLog(`已更新桌面 profile：${event?.profile_name || desktopProfileName.value}`, 'success')
      },
      onCaptureFinished: (event) => {
        desktopStatusText.value = `采集结束：${event?.screenshots || 0} 张截图`
        pushDesktopLog(desktopStatusText.value, 'done')
      },
      onImportStart: () => {
        desktopStatusText.value = '采集包已生成，开始导入采矿安全智能问答系统…'
        pushDesktopLog(desktopStatusText.value, 'loading')
      },
      onImportDone: (event) => {
        const result = event?.result || {}
        desktopStatusText.value = `导入完成：${result.title || result.article_id || ''}`
        pushDesktopLog(`已导入文章：${result.article_id || ''}`, 'success')
      },
      onDone: (event) => {
        finalPayload = event?.data || {}
      },
      onError: (message) => {
        desktopStatusText.value = message || '桌面端自动采集失败'
      },
      onLog: (event) => {
        pushDesktopLog(event?.message || '采集中…', 'info')
      },
    }, { signal: desktopCaptureAbortController.value.signal })

    const capture = finalPayload?.capture || {}
    const importResult = finalPayload?.import_result || null
    desktopProfiles.value = finalPayload?.profiles || desktopProfiles.value
    desktopProfileName.value = capture.profile_name || desktopProfileName.value
    desktopStatusText.value = importResult
      ? `桌面端采集并导入完成：${importResult.title || importResult.article_id}`
      : `桌面端采集完成：已生成 ${capture.screenshots || 0} 张截图包`
    desktopLastCaptureSummary.value = importResult
      ? `article_id=${importResult.article_id}，正文长度 ${importResult.body_length || 0}，截图 ${capture.screenshots || 0}`
      : `session=${capture.session_dir || ''}`
    setDesktopActionFeedback(
      'success',
      importResult ? '桌面采集与导入已完成' : '桌面采集已完成',
      importResult
        ? `已写入文章 ${importResult.article_id || ''}，共生成 ${capture.screenshots || 0} 张截图。`
        : `已生成 ${capture.screenshots || 0} 张截图包，可继续导入或复查 session。`
    )

    crawlAccountId.value = accountId
    if (importResult?.account_id) {
      await loadArticles({ keepSelected: false, autoSelectFirst: false })
    }
  } catch (err) {
    const msg = err?.response?.data?.detail || err?.message || '桌面端自动采集失败'
    desktopStatusText.value = msg
    pushDesktopLog(msg, 'error')
    setDesktopActionFeedback('error', '桌面采集失败', msg)
  } finally {
    desktopCaptureLoading.value = false
    desktopCaptureAbortController.value = null
  }
}

function findArticleByIds(accountId, articleId) {
  if (!accountId || !articleId) return null
  return flatArticles.value.find((item) => item.account_id === accountId && item.article_id === articleId) || null
}

function normalizeWechatArticleUrl(url) {
  const raw = String(url || '').trim()
  if (!raw) return ''
  try {
    const parsed = new URL(raw)
    const params = new URLSearchParams(parsed.search)
    const keys = ['__biz', 'mid', 'idx', 'sn', 'chksm', 'album_id']
    const normalized = new URL(`${parsed.origin}${parsed.pathname}`)
    for (const key of keys) {
      if (params.has(key)) {
        normalized.searchParams.set(key, params.get(key))
      }
    }
    return normalized.toString()
  } catch {
    return raw
  }
}

function findArticleBySourceLink(accountId, sourceLink) {
  const normalized = normalizeWechatArticleUrl(sourceLink)
  if (!normalized) return null
  return flatArticles.value.find((item) => {
    if (accountId && item.account_id !== accountId) return false
    return normalizeWechatArticleUrl(item.source_link || item.article_url || '') === normalized
  }) || null
}

function pickCreatedArticle(createdArticles, fallbackAccountId = '') {
  const list = Array.isArray(createdArticles) ? createdArticles : []
  for (const item of list) {
    const byIds = findArticleByIds(item?.account_id || fallbackAccountId, item?.article_id)
    if (byIds) return byIds
    const byLink = findArticleBySourceLink(item?.account_id || fallbackAccountId, item?.source_link)
    if (byLink) return byLink
  }
  return null
}

function pickArticleFromRefreshed(refreshed) {
  const accounts = refreshed?.accounts || []
  for (const acc of accounts) {
    const list = acc?.articles || []
    if (list.length > 0) {
      return {
        account_id: list[0].account_id,
        article_id: list[0].article_id,
      }
    }
  }
  return null
}

function pickAgentTargetArticle(data) {
  const steps = Array.isArray(data?.steps) ? data.steps : []
  const collectStep = steps.find((step) => step?.name === 'collect')
  const collectRefreshed = collectStep?.result?.refreshed
  const collectRunResult = collectStep?.result?.run_result || {}
  const collectCreated = collectStep?.result?.created_articles || collectRunResult?.created_articles || []

  const preciseTarget = pickCreatedArticle(collectCreated)
  if (preciseTarget) {
    return {
      target: { account_id: preciseTarget.account_id, article_id: preciseTarget.article_id },
      newArticles: Number(collectRunResult?.new_articles || 0),
      processed: Number(collectRunResult?.processed_articles || 0),
    }
  }

  const fromCollect = pickArticleFromRefreshed(collectRefreshed)
  if (fromCollect) {
    return {
      target: fromCollect,
      newArticles: Number(collectRunResult?.new_articles || 0),
      processed: Number(collectRunResult?.processed_articles || 0),
    }
  }

  const fromDone = pickArticleFromRefreshed(data?.refreshed)
  if (fromDone) {
    return {
      target: fromDone,
      newArticles: Number(collectRunResult?.new_articles || 0),
      processed: Number(collectRunResult?.processed_articles || 0),
    }
  }

  return {
    target: null,
    newArticles: Number(collectRunResult?.new_articles || 0),
    processed: Number(collectRunResult?.processed_articles || 0),
  }
}

function getAgentCollectStep(data) {
  const steps = Array.isArray(data?.steps) ? data.steps : []
  return steps.find((step) => step?.name === 'collect' || step?.name === 'desktop_collect') || null
}

function describeBlockedReasons(blockedArticles) {
  const reasons = Array.isArray(blockedArticles)
    ? blockedArticles.map((item) => String(item?.reason || '').trim()).filter(Boolean)
    : []
  const uniqueReasons = [...new Set(reasons)]
  if (!uniqueReasons.length) return ''
  return uniqueReasons.slice(0, 2).join('；')
}

function describeZeroNewArticles(data) {
  const collectStep = getAgentCollectStep(data)
  if (!collectStep) {
    return '本次没有新增文章，当前这轮更像是仅执行了观察、清洗或入库。'
  }

   const collectEvaluation = collectStep?.evaluation || {}

  if (collectStep.name === 'desktop_collect') {
    const importResult = collectStep?.result?.import_result || {}
    const imported = Number(importResult?.imported_articles || importResult?.imported_count || 0)
    if (imported <= 0) {
      return '桌面采集链路已执行，但没有导入到新的文章，可能是没有命中目标文章，或采集包里没有形成可导入结果。'
    }
  }

  const result = collectStep?.result || {}
  const runResult = result?.run_result || {}
  const resolvedCount = Number(result?.resolved_url_count || 0)
  const duplicateCount = Number(result?.duplicate_url_count || runResult?.duplicate_url_count || (Array.isArray(result?.duplicate_article_urls) ? result.duplicate_article_urls.length : 0) || 0)
  const blockedCount = Array.isArray(runResult?.blocked_articles) ? runResult.blocked_articles.length : 0
  const failedCount = Array.isArray(runResult?.failed_articles) ? runResult.failed_articles.length : 0
  const skippedWindow = Number(runResult?.skipped_time_window || 0)
  const skippedReason = String(runResult?.skipped_reason || '').trim()
  const blockedReasonText = describeBlockedReasons(runResult?.blocked_articles)

  if (String(collectEvaluation?.status || '').trim() === 'failed') {
    if (blockedCount > 0) {
      return `这次已经执行了抓取，但公众号页面被访问保护拦住了${blockedReasonText ? `，拦截特征：${blockedReasonText}` : ''}。更像是抓到了验证页、空壳页或受限页，不是完全没执行。`
    }
    if (failedCount > 0) {
      return '这次已经执行了抓取，但抓取过程失败，没有形成可用文章结果。'
    }
    return '这次已经执行了抓取，但没有形成可用文章结果。'
  }

  if (skippedReason === 'frequency_control') {
    return '这次没有重新抓取，原因是命中了频率控制；如果你确认要立即重跑，需要显式强制抓取。'
  }
  if (skippedReason === 'all_duplicates') {
    return `这次没有新增文章，已识别到 ${duplicateCount || 0} 条链接都抓取过，更像是重复链接，不是风控。`
  }
  if (skippedReason === 'all_duplicates_or_empty_history') {
    return '这次没有新增文章，历史页里没有解析出新的未采集文章；更像是历史页为空或已经抓完。'
  }
  if (blockedCount > 0) {
    return `这次没有新增文章，其中有 ${blockedCount} 条页面被公众号页面质量保护拦住；这更像是命中了微信验证页或页面访问保护，不一定是账号本身被风控${blockedReasonText ? `。当前拦截特征：${blockedReasonText}` : '。'}`
  }
  if (resolvedCount <= 0 && duplicateCount <= 0 && failedCount <= 0) {
    return '这次没有新增文章，而且这一轮没有解析出可处理的新链接。更像是链接失效、历史页没有可见文章，或者页面已经跳到了微信验证/受限页面。'
  }
  if (duplicateCount > 0 && failedCount <= 0 && skippedWindow <= 0) {
    return `这次没有新增文章，已识别到 ${duplicateCount} 条重复链接，更像是你输入的链接之前抓过。`
  }
  if (skippedWindow > 0 && failedCount <= 0) {
    return `这次没有新增文章，有 ${skippedWindow} 条文章落在当前时间窗之外，被规则过滤掉了。`
  }
  if (failedCount > 0) {
    return `这次没有新增文章，抓取过程中有 ${failedCount} 条链接失败；如果链接本身可打开，优先怀疑页面访问异常或解析失败。`
  }
  return '这次没有新增文章。更常见的原因是重复链接、时间窗过滤，或者本轮实际上只执行了清洗/入库。'
}

function toAgentNarration(message) {
  const text = String(message || '').trim()
  if (!text) return ''
  if (/^正在初始化公众号采集器/.test(text)) return '我先启动公众号采集器，确认本轮抓取环境可用。'
  if (/^正在解析公众号链接并准备文章队列/.test(text)) return '我正在拆解你给的链接，并整理出这一轮真正要处理的文章队列。'
  if (/^已解析出\s*\d+\s*条待处理文章链接/.test(text)) return `我已经整理好待处理链接。${text.replace(/^已/, '')}。`
  if (/^正在处理第\s*\d+\/\d+\s*条文章链接/.test(text)) return `我正在逐条检查文章入口。${text}`
  if (/^第\s*\d+\/\d+\s*条处理成功/.test(text)) return `这一条已经处理成功。${text}`
  if (/^第\s*\d+\/\d+\s*条已跳过/.test(text)) return `这一条我先跳过了。${text}`
  if (/^第\s*\d+\/\d+\s*条未抓取成功/.test(text)) return `这一条没有抓下来。${text}`
  if (/^第\s*\d+\/\d+\s*条抓取失败/.test(text)) return `这一条执行失败了。${text}`
  if (/^正在连接本机微信窗口/.test(text)) return '我正在接管本机微信窗口，准备走桌面采集回退链路。'
  if (/^正在尝试打开历史消息与目标文章/.test(text)) return '我正在桌面微信里定位公众号和目标文章，这一步会受界面响应速度影响。'
  if (/^正在整理截图采集包并准备导入结果/.test(text)) return '我正在整理桌面采集结果，并准备把它导回当前系统。'
  if (/^正在清洗文章内容与图片元数据/.test(text)) return '我开始清洗文章正文和图片元数据，准备进入检索链路。'
  if (/^正在生成可检索块并准备写入知识库/.test(text)) return '我正在生成可检索内容块，并准备把结果写入知识库。'
  return text
}

function buildAgentExecutionSummary(data) {
  const parsed = data?.parsed || {}
  if (parsed?.capability_supported === false) {
    return String(parsed?.assistant_reply || parsed?.capability_message || '当前只返回了能力说明，没有进入公众号执行链路。').trim()
  }

  const collectStep = getAgentCollectStep(data)
  const cleanStep = (Array.isArray(data?.steps) ? data.steps : []).find((step) => step?.name === 'clean')
  const ingestStep = (Array.isArray(data?.steps) ? data.steps : []).find((step) => step?.name === 'ingest')
  const runResult = collectStep?.result?.run_result || {}
  const processed = Number(runResult?.processed_articles || 0)
  const created = Number(runResult?.new_articles || 0)
  const duplicateCount = Number(collectStep?.result?.duplicate_url_count || runResult?.duplicate_url_count || (Array.isArray(collectStep?.result?.duplicate_article_urls) ? collectStep.result.duplicate_article_urls.length : 0) || 0)
  const blockedCount = Array.isArray(runResult?.blocked_articles) ? runResult.blocked_articles.length : 0
  const failedCount = Array.isArray(runResult?.failed_articles) ? runResult.failed_articles.length : 0
  const skippedWindow = Number(runResult?.skipped_time_window || 0)
  const cleanResult = cleanStep?.result || {}
  const cleanedArticles = Number(cleanStep?.result?.cleaned_articles || 0)
  const ingestedChunks = Number(cleanStep?.result?.ingested_chunks || 0)
  const ingestedFiles = Number(cleanStep?.result?.ingested_files || 0)
  const cleanSkippedReason = String(cleanResult?.skipped_reason || '').trim()
  const ingestDeferred = Boolean(cleanResult?.ingest_deferred)

  if (!collectStep && !cleanStep) {
    return '本轮未进入抓取、桌面采集或清洗阶段。'
  }

  const parts = []
  if (collectStep) {
    parts.push(`本轮检查了 ${processed} 条文章链接，新增 ${created} 篇文章`)
    if (duplicateCount > 0) parts.push(`识别出重复链接 ${duplicateCount} 条`)
    if (skippedWindow > 0) parts.push(`按时间窗跳过 ${skippedWindow} 条`)
    if (blockedCount > 0) parts.push(`页面访问受限 ${blockedCount} 条`)
    if (failedCount > 0) parts.push(`抓取失败 ${failedCount} 条`)
  }
  if (cleanStep) {
    if (cleanSkippedReason === 'no_new_articles_to_clean') {
      parts.push('这轮没有新文章进入清洗，所以跳过了清洗与入库')
    } else if (ingestDeferred) {
      parts.push(`后续清洗了 ${cleanedArticles} 篇文章，但在线入库已延后；当前暂未写入新的检索块`)
    } else if (ingestedFiles > 0 || ingestedChunks > 0) {
      parts.push(`后续清洗了 ${cleanedArticles} 篇文章，并写入 ${ingestedFiles} 个文件、${ingestedChunks} 个检索块`)
    } else {
      parts.push(`后续清洗了 ${cleanedArticles} 篇文章，本轮未产生新的入库块`)
    }
  }
  if (ingestStep && ingestDeferred) {
    const ingestError = String(cleanResult?.ingest_error || '').trim()
    if (ingestError) {
      parts.push('在线入库已自动降级，服务保持可用')
    }
  }
  const governance = data?.governance || {}
  const governanceRisk = String(governance?.report?.risk_level || '').trim()
  if (governanceRisk) {
    parts.push(`治理风险等级 ${governanceRisk}`)
  }
  return `${parts.join('；')}。`
}

function buildAgentStageBoundarySummary(data) {
  const parsed = data?.parsed || {}
  if (parsed?.capability_supported === false) {
    return '阶段边界：本轮只停在能力判断，没有进入采集、治理或评测链路。'
  }

  const steps = Array.isArray(data?.steps) ? data.steps : []
  const collectStep = getAgentCollectStep(data)
  const cleanStep = steps.find((step) => step?.name === 'clean') || null
  const governance = data?.governance || null
  const evaluation = data?.evaluation_optimization || null
  const orchestration = data?.orchestration || {}
  const completedAgents = Array.isArray(orchestration?.completed_agents) ? orchestration.completed_agents.map((item) => String(item || '').trim()) : []

  const collectStatus = String(collectStep?.evaluation?.status || collectStep?.status || '').trim()
  const cleanStatus = String(cleanStep?.evaluation?.status || cleanStep?.status || '').trim()
  const governanceStatus = String(governance?.status || '').trim()
  const evaluationStatus = String(evaluation?.status || '').trim()

  const parts = []
  if (!collectStep) {
    parts.push('未进入采集 Agent')
  } else if (collectStatus === 'failed') {
    parts.push('停在采集 Agent')
  } else {
    parts.push('已完成采集 Agent')
  }

  if (!cleanStep) {
    parts.push('未进入清洗入库')
  } else if (cleanStatus === 'failed') {
    parts.push('停在清洗入库')
  } else if (String(cleanStep?.result?.skipped_reason || '').trim() === 'no_new_articles_to_clean') {
    parts.push('采集后未形成新的清洗目标')
  } else {
    parts.push('已完成清洗入库')
  }

  if (completedAgents.includes('knowledge_governance_agent') || governanceStatus === 'completed') {
    parts.push('已触发治理 Agent')
  } else if (governanceStatus === 'failed') {
    parts.push('停在治理 Agent')
  } else {
    parts.push('未触发治理 Agent')
  }

  if (completedAgents.includes('evaluation_optimization_agent') || evaluationStatus === 'completed') {
    parts.push('已触发评测 Agent')
  } else if (evaluationStatus === 'failed') {
    parts.push('停在评测 Agent')
  } else {
    parts.push('未触发评测 Agent')
  }

  return `阶段边界：${parts.join(' -> ')}。`
}

function buildAgentFeedbackTitle(data, { pickedNewArticles = 0 } = {}) {
  const parsed = data?.parsed || {}
  if (parsed?.capability_supported === false) return 'Agent 能力说明'

  const collectStep = getAgentCollectStep(data)
  const cleanStep = (Array.isArray(data?.steps) ? data.steps : []).find((step) => step?.name === 'clean') || null
  const governance = data?.governance || null
  const evaluation = data?.evaluation_optimization || null

  if (String(collectStep?.evaluation?.status || collectStep?.status || '').trim() === 'failed') return '采集阶段失败'
  if (String(cleanStep?.evaluation?.status || cleanStep?.status || '').trim() === 'failed') return '清洗入库阶段失败'
  if (String(governance?.status || '').trim() === 'failed') return '治理阶段失败'
  if (String(evaluation?.status || '').trim() === 'failed') return '评测阶段失败'

  const completedAgents = Array.isArray((data?.orchestration || {}).completed_agents)
    ? (data?.orchestration || {}).completed_agents.map((item) => String(item || '').trim())
    : []
  if (completedAgents.includes('evaluation_optimization_agent')) return '多 Agent 执行完成'
  if (completedAgents.includes('knowledge_governance_agent')) return '已进入治理阶段'
  if (pickedNewArticles > 0) return '采集阶段完成'
  if (collectStep || cleanStep) return '本轮未新增知识资产'
  return '未触发执行阶段'
}

function buildAgentCompletionFeedbackMessage(data, { pickedNewArticles = 0, hasTarget = false } = {}) {
  const summary = buildAgentExecutionSummary(data)
  const boundary = buildAgentStageBoundarySummary(data)
  if (pickedNewArticles > 0) {
    return `${summary} ${boundary}${hasTarget ? ' 本轮目标文章已经进入历史文章列表，可手动进入标注工作台查看。' : ' 新文章已进入历史文章列表，可手动进入标注工作台查看。'}`
  }

  const reason = describeZeroNewArticles(data)
  if (!reason) return `${summary} ${boundary}`
  if (reason === summary) return `${summary} ${boundary}`
  return `${summary} ${boundary} 原因判断：${reason}`
}

function buildAgentFailureDiagnostics(data) {
  if (!data || typeof data !== 'object') {
    return { visible: false, title: '', status: '', tone: 'idle', summary: '', detail: '', chips: [] }
  }

  const parsed = data?.parsed || {}
  if (parsed?.capability_supported === false) {
    return {
      visible: true,
      title: '能力边界拦截',
      status: '未进入执行',
      tone: 'warning',
      summary: '当前输入被判定为公众号工作台能力域之外，所以没有进入采集、治理或评测。',
      detail: String(parsed?.assistant_reply || parsed?.capability_message || '').trim(),
      chips: ['分类：capability_unsupported'],
    }
  }

  const collectStep = getAgentCollectStep(data)
  const cleanStep = (Array.isArray(data?.steps) ? data.steps : []).find((step) => step?.name === 'clean') || null
  const governance = data?.governance || null
  const evaluation = data?.evaluation_optimization || null
  const runResult = collectStep?.result?.run_result || {}
  const skippedReason = String(runResult?.skipped_reason || '').trim()
  const blockedCount = Array.isArray(runResult?.blocked_articles) ? runResult.blocked_articles.length : 0
  const failedCount = Array.isArray(runResult?.failed_articles) ? runResult.failed_articles.length : 0
  const duplicateCount = Number(collectStep?.result?.duplicate_url_count || runResult?.duplicate_url_count || (Array.isArray(collectStep?.result?.duplicate_article_urls) ? collectStep.result.duplicate_article_urls.length : 0) || 0)
  const skippedWindow = Number(runResult?.skipped_time_window || 0)
  const collectFailed = String(collectStep?.evaluation?.status || collectStep?.status || '').trim() === 'failed'
  const cleanFailed = String(cleanStep?.evaluation?.status || cleanStep?.status || '').trim() === 'failed'
  const governanceFailed = String(governance?.status || '').trim() === 'failed'
  const evaluationFailed = String(evaluation?.status || '').trim() === 'failed'

  if (evaluationFailed) {
    return {
      visible: true,
      title: '评测阶段异常',
      status: '停在评测',
      tone: 'danger',
      summary: '治理结果已经形成，但评测 Agent 本轮没有稳定完成。',
      detail: String(evaluation?.error || evaluation?.artifact?.summary || '').trim(),
      chips: ['分类：evaluation_failed'],
    }
  }
  if (governanceFailed) {
    return {
      visible: true,
      title: '治理阶段异常',
      status: '停在治理',
      tone: 'danger',
      summary: '采集或清洗阶段已经完成，但治理 Agent 失败，后续评测不会继续触发。',
      detail: String(governance?.error || '').trim(),
      chips: ['分类：governance_failed'],
    }
  }
  if (cleanFailed) {
    return {
      visible: true,
      title: '清洗入库异常',
      status: '停在清洗入库',
      tone: 'danger',
      summary: '采集结果已经拿到，但清洗入库阶段失败，所以知识资产没有稳定进入后续治理链路。',
      detail: String(cleanStep?.error || '').trim(),
      chips: ['分类：clean_failed'],
    }
  }
  if (collectFailed) {
    return {
      visible: true,
      title: '采集阶段异常',
      status: '停在采集',
      tone: 'danger',
      summary: describeZeroNewArticles(data) || '采集阶段失败，本轮没有形成可用的新文章结果。',
      detail: '',
      chips: ['分类：collect_failed'],
    }
  }
  if (skippedReason === 'all_duplicates') {
    return {
      visible: true,
      title: '重复链接',
      status: '未形成新资产',
      tone: 'warning',
      summary: `本轮没有新增文章，输入链接命中了 ${duplicateCount} 条重复记录。`,
      detail: '这不是抓取失败，而是同一账号下已经存在这些文章。',
      chips: ['分类：all_duplicates'],
    }
  }
  if (skippedReason === 'frequency_control') {
    return {
      visible: true,
      title: '频率控制',
      status: '本轮未重跑',
      tone: 'warning',
      summary: '当前账号命中了频率控制规则，所以本轮没有重新抓取。',
      detail: '如果这是预期外结果，需要显式强制抓取。',
      chips: ['分类：frequency_control'],
    }
  }
  if (skippedWindow > 0 && failedCount <= 0) {
    return {
      visible: true,
      title: '时间窗过滤',
      status: '未形成新资产',
      tone: 'warning',
      summary: `本轮有 ${skippedWindow} 条文章落在时间窗之外，被规则过滤。`,
      detail: '这不是页面错误，而是当前过滤条件把文章挡掉了。',
      chips: ['分类：time_window_filtered'],
    }
  }
  if (blockedCount > 0) {
    return {
      visible: true,
      title: '页面访问受限',
      status: '链接已命中但页面受限',
      tone: 'warning',
      summary: `本轮有 ${blockedCount} 条页面被微信验证页或访问保护拦住。`,
      detail: '更像是页面访问质量保护，而不是账号或链接完全无效。',
      chips: ['分类：blocked_page'],
    }
  }
  if (failedCount > 0) {
    return {
      visible: true,
      title: '链接处理失败',
      status: '未形成新资产',
      tone: 'warning',
      summary: `本轮有 ${failedCount} 条链接处理失败。`,
      detail: '优先排查页面可访问性、解析异常或响应结构变化。',
      chips: ['分类：crawl_failed'],
    }
  }
  if (String(cleanStep?.result?.skipped_reason || '').trim() === 'no_new_articles_to_clean') {
    return {
      visible: true,
      title: '没有新的清洗目标',
      status: '停在清洗前',
      tone: 'warning',
      summary: '采集阶段没有形成新的文章资产，所以后续清洗、治理、评测都不会继续。',
      detail: describeZeroNewArticles(data),
      chips: ['分类：no_new_articles_to_clean'],
    }
  }
  return { visible: false, title: '', status: '', tone: 'idle', summary: '', detail: '', chips: [] }
}

function pushAgentLog(message, status = 'info') {
  agentLogs.value = [
    {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
      status,
      message,
    },
    ...agentLogs.value,
  ].slice(0, 40)
  agentLastSavedAt.value = Date.now()
}

function syncAgentRunningState() {
  agentActiveRunCount.value = agentActiveRunIds.value.length
  agentRunning.value = agentActiveRunCount.value > 0
  if (!agentRunning.value) {
    agentAbortController.value = null
    agentLeaveNoticeShown.value = false
    agentDetachedRunning.value = false
  }
}

function startAgentRun(runId, controller) {
  agentActiveRunIds.value = [...agentActiveRunIds.value, runId]
  agentAbortController.value = controller
  syncAgentRunningState()
}

function finishAgentRun(runId, controller) {
  agentActiveRunIds.value = agentActiveRunIds.value.filter((item) => item !== runId)
  if (agentAbortController.value === controller) {
    agentAbortController.value = null
  }
  syncAgentRunningState()
}

function setAgentActionFeedback(type, title, message = '') {
  agentActionFeedback.value = { type, title, message }
  agentLastSavedAt.value = Date.now()
  persistAgentPanelState()
}

function normalizeAgentTask(task) {
  if (!task || typeof task !== 'object') return null
  return {
    task_id: String(task.task_id || '').trim(),
    task_type: String(task.task_type || '').trim(),
    status: String(task.status || 'unknown').trim() || 'unknown',
    goal: String(task.goal || '').trim(),
    summary: String(task.summary || '').trim(),
    account_id: String(task.account_id || '').trim(),
    article_ids: Array.isArray(task.article_ids) ? task.article_ids.map((item) => String(item || '').trim()).filter(Boolean) : [],
    article_titles: Array.isArray(task.article_titles) ? task.article_titles.map((item) => String(item || '').trim()).filter(Boolean) : [],
    created_at: String(task.created_at || '').trim(),
    updated_at: String(task.updated_at || '').trim(),
    retried_count: Number(task.retried_count || 0),
    last_error: String(task.last_error || '').trim(),
    result: task.result && typeof task.result === 'object' ? {
      cleaned_articles: Number(task.result.cleaned_articles || 0),
      generated_docs: Number(task.result.generated_docs || 0),
      ingest_enabled: !!task.result.ingest_enabled,
      ingest_deferred: !!task.result.ingest_deferred,
      ingested_files: Number(task.result.ingested_files || 0),
      ingested_chunks: Number(task.result.ingested_chunks || 0),
    } : null,
    events: Array.isArray(task.events)
      ? task.events.filter((item) => item && typeof item === 'object').map((item) => ({
          type: String(item.type || 'info').trim(),
          message: String(item.message || '').trim(),
          at: String(item.at || '').trim(),
          detail: item.detail && typeof item.detail === 'object' ? { ...item.detail } : null,
        }))
      : [],
  }
}

function upsertAgentTask(task) {
  const normalized = normalizeAgentTask(task)
  if (!normalized?.task_id) return null
  const items = Array.isArray(agentTaskList.value) ? [...agentTaskList.value] : []
  agentTaskList.value = [normalized, ...items.filter((item) => item?.task_id !== normalized.task_id)].slice(0, 8)
  return normalized
}

function formatAgentTaskStatus(status) {
  if (status === 'deferred') return '已延后'
  if (status === 'running') return '执行中'
  if (status === 'completed') return '已完成'
  if (status === 'failed') return '失败'
  if (status === 'queued') return '排队中'
  return status || '未知'
}

function formatAgentTaskTime(value) {
  if (!value) return ''
  try {
    return new Date(value).toLocaleString('zh-CN', { hour12: false })
  } catch {
    return value
  }
}

function formatAgentTaskShortTime(value) {
  if (!value) return '--'
  try {
    return new Date(value).toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    })
  } catch {
    return String(value)
  }
}

function buildAgentTaskResultSummary(task) {
  const result = task?.result
  if (!result || typeof result !== 'object') return []
  const items = []
  if (Number(result.cleaned_articles || 0) > 0) items.push(`清洗 ${Number(result.cleaned_articles || 0)} 篇`)
  if (Number(result.generated_docs || 0) > 0) items.push(`文档 ${Number(result.generated_docs || 0)} 份`)
  if (Number(result.ingested_files || 0) > 0) items.push(`入库文件 ${Number(result.ingested_files || 0)} 个`)
  if (Number(result.ingested_chunks || 0) > 0) items.push(`入库切块 ${Number(result.ingested_chunks || 0)} 个`)
  if (result.ingest_deferred) items.push('入库已延后')
  return items.slice(0, 4)
}

function getLatestTaskEventText(task) {
  const events = Array.isArray(task?.events) ? task.events : []
  if (!events.length) return ''
  const latest = events[events.length - 1]
  const detail = formatAgentTaskEventDetail(latest)
  const message = [String(latest?.message || '').trim(), detail].filter(Boolean).join('，')
  if (message.length <= 120) return message
  return `${message.slice(0, 120)}...`
}

function formatAgentTaskEventDetail(event) {
  const detail = event?.detail
  if (!detail || typeof detail !== 'object') return ''
  const parts = []
  if (detail.reason) parts.push(`原因 ${detail.reason}`)
  if (detail.retried_count) parts.push(`第 ${detail.retried_count} 次重试`)
  if (detail.exit_code) parts.push(`退出码 ${detail.exit_code}`)
  if (detail.ingested_files) parts.push(`文件 ${detail.ingested_files} 个`)
  if (detail.ingested_chunks) parts.push(`切块 ${detail.ingested_chunks} 个`)
  if (detail.article_ids && Array.isArray(detail.article_ids) && detail.article_ids.length) parts.push(`文章 ${detail.article_ids.length} 篇`)
  if (!parts.length && detail.error) {
    return String(detail.error || '').trim().slice(0, 140)
  }
  return parts.join('，')
}

function buildAgentTaskTimelineText(task) {
  if (!task || !Array.isArray(task.events) || !task.events.length) return ''
  return task.events
    .map((event) => {
      const time = formatAgentTaskTime(event.at) || event.at || '未知时间'
      const detail = formatAgentTaskEventDetail(event)
      return detail ? `[${time}] ${event.message} | ${detail}` : `[${time}] ${event.message}`
    })
    .join('\n')
}

function buildAgentTaskDiagnosticSummary(task) {
  if (!task) return ''
  const lines = []
  lines.push(`任务ID: ${task.task_id || '未记录'}`)
  lines.push(`状态: ${formatAgentTaskStatus(task.status)}`)
  lines.push(`账号: ${task.account_id || '未记录'}`)
  lines.push(`创建时间: ${formatAgentTaskTime(task.created_at) || task.created_at || '未记录'}`)
  lines.push(`更新时间: ${formatAgentTaskTime(task.updated_at || task.created_at) || task.updated_at || task.created_at || '未记录'}`)
  if (task.goal) lines.push(`目标: ${task.goal}`)
  if (task.summary) lines.push(`摘要: ${task.summary}`)
  if (task.article_ids?.length) {
    lines.push(`文章数: ${task.article_ids.length}`)
    const articleLines = listTaskArticleEntries(task).map((entry) => `- ${entry.title} (${entry.accountId || '未记录账号'} / ${entry.articleId})${entry.resolved ? '' : ' [本地未定位]'}`)
    if (articleLines.length) {
      lines.push('涉及文章:')
      lines.push(...articleLines)
    }
  }
  const resultSummary = buildAgentTaskResultSummary(task)
  if (resultSummary.length) {
    lines.push(`结果: ${resultSummary.join('；')}`)
  }
  if (task.last_error) {
    lines.push('最近错误:')
    lines.push(task.last_error)
  }
  const timelineText = buildAgentTaskTimelineText(task)
  if (timelineText) {
    lines.push('事件时间线:')
    lines.push(timelineText)
  }
  return lines.join('\n')
}

function listTaskArticleEntries(task) {
  const accountId = String(task?.account_id || '').trim()
  const articleIds = Array.isArray(task?.article_ids) ? task.article_ids : []
  const articleTitles = Array.isArray(task?.article_titles) ? task.article_titles.map((item) => String(item || '').trim()).filter(Boolean) : []
  const seen = new Set()
  const entries = []
  for (const rawId of articleIds) {
    const articleId = String(rawId || '').trim()
    if (!articleId || seen.has(articleId)) continue
    seen.add(articleId)
    const matched = findArticleByIds(accountId, articleId)
      || flatArticles.value.find((item) => item.article_id === articleId && (!accountId || item.account_id === accountId))
      || null
    entries.push({
      articleId,
      accountId: matched?.account_id || accountId,
      title: String(matched?.title || articleId).trim(),
      resolved: !!matched,
      matched,
    })
  }
  if (!entries.length && articleTitles.length) {
    articleTitles.forEach((title, index) => {
      entries.push({
        articleId: `title:${index + 1}`,
        accountId,
        title,
        resolved: false,
        matched: null,
      })
    })
  }
  return entries
}

function canOpenTaskAccount(task) {
  return !!String(task?.account_id || '').trim()
}

function getTaskPrimaryArticle(task) {
  const accountId = String(task?.account_id || '').trim()
  const articleIds = Array.isArray(task?.article_ids) ? task.article_ids : []
  for (const articleId of articleIds) {
    const matched = findArticleByIds(accountId, String(articleId || '').trim())
    if (matched) return matched
  }
  return null
}

function canOpenTaskArticle(task) {
  return !!getTaskPrimaryArticle(task)
}

function openAgentTaskDetail(task) {
  const normalized = normalizeAgentTask(task)
  if (!normalized) return
  agentTaskErrorExpanded.value = false
  agentTaskDetailTask.value = normalized
  agentTaskDetailVisible.value = true
}

async function copyAgentTaskError() {
  const errorText = agentTaskDetailErrorText.value
  if (!errorText) {
    ElMessage.warning('当前任务没有可复制的错误详情')
    return
  }
  await copyTextToClipboard(errorText, '已复制错误详情', '复制失败，请手动复制错误详情')
}

async function copyAgentTaskTimeline() {
  const timelineText = agentTaskDetailTimelineText.value
  if (!timelineText) {
    ElMessage.warning('当前任务没有可复制的事件时间线')
    return
  }
  await copyTextToClipboard(timelineText, '已复制任务时间线', '复制失败，请手动复制时间线')
}

async function copyAgentTaskDiagnosticSummary() {
  const summaryText = agentTaskDetailDiagnosticSummary.value
  if (!summaryText) {
    ElMessage.warning('当前任务没有可复制的诊断摘要')
    return
  }
  await copyTextToClipboard(summaryText, '已复制诊断摘要', '复制失败，请手动复制诊断摘要')
}

async function openResolvedTaskArticle(entry) {
  if (!entry?.matched) {
    ElMessage.warning('该文章尚未在本地历史列表中定位到')
    return
  }
  crawlAccountId.value = entry.matched.account_id || crawlAccountId.value
  if (agentTaskDetailTask.value?.task_id) {
    agentTaskCard.value = upsertAgentTask(agentTaskDetailTask.value) || agentTaskCard.value
  }
  agentTaskDetailVisible.value = false
  await selectArticle(entry.matched)
}

async function openTaskAccount(task) {
  const accountId = String(task?.account_id || '').trim()
  if (!accountId) {
    ElMessage.warning('当前任务没有可跳转的账号')
    return
  }
  const first = flatArticles.value.find((item) => item.account_id === accountId)
  if (!first) {
    ElMessage.warning('当前账号下还没有可打开的本地文章')
    return
  }
  crawlAccountId.value = accountId
  agentTaskCard.value = upsertAgentTask(task) || agentTaskCard.value
  agentTaskDetailTask.value = normalizeAgentTask(task)
  agentTaskDetailVisible.value = false
  await selectArticle(first)
}

async function openTaskArticle(task) {
  const target = getTaskPrimaryArticle(task)
  if (!target) {
    ElMessage.warning('当前任务还没有可定位的本地文章')
    return
  }
  crawlAccountId.value = target.account_id || crawlAccountId.value
  agentTaskCard.value = upsertAgentTask(task) || agentTaskCard.value
  agentTaskDetailTask.value = normalizeAgentTask(task)
  agentTaskDetailVisible.value = false
  await selectArticle(target)
}

function isTerminalAgentTaskStatus(status) {
  return ['completed', 'failed', 'cancelled'].includes(String(status || '').trim())
}

function stopAgentTaskPolling() {
  if (agentTaskPollTimer) {
    clearInterval(agentTaskPollTimer)
    agentTaskPollTimer = null
  }
}

function syncAgentTaskPolling() {
  if (!agentTaskCard.value?.task_id || isTerminalAgentTaskStatus(agentTaskCard.value?.status)) {
    stopAgentTaskPolling()
    return
  }
  if (agentTaskPollTimer) return
  agentTaskPollTimer = setInterval(() => {
    if (!agentTaskCard.value?.task_id || agentTaskLoading.value || isTerminalAgentTaskStatus(agentTaskCard.value?.status)) {
      syncAgentTaskPolling()
      return
    }
    refreshAgentTaskCard()
  }, 4000)
}

async function refreshAgentTaskCard() {
  const taskId = agentTaskCard.value?.task_id
  if (!taskId) return
  agentTaskLoading.value = true
  try {
    const response = await wechatAnnotatorAPI.getAgentTask(taskId)
    agentTaskCard.value = upsertAgentTask(response?.data?.task)
    agentLastSavedAt.value = Date.now()
    persistAgentPanelState()
  } catch (error) {
    pushAgentLog(error?.response?.data?.detail || error?.message || '刷新 Agent 任务状态失败', 'warning')
  } finally {
    agentTaskLoading.value = false
    syncAgentTaskPolling()
  }
}

function selectAgentTask(task) {
  const normalized = normalizeAgentTask(task)
  if (!normalized) return
  agentTaskCard.value = normalized
  upsertAgentTask(normalized)
  agentLastSavedAt.value = Date.now()
  persistAgentPanelState()
}

async function loadRecentAgentTasks() {
  agentTaskListLoading.value = true
  try {
    const response = await wechatAnnotatorAPI.listAgentTasks(8)
    const items = Array.isArray(response?.data?.tasks) ? response.data.tasks.map(normalizeAgentTask).filter(Boolean) : []
    agentTaskList.value = items
    if (agentTaskCard.value?.task_id) {
      const matched = items.find((item) => item.task_id === agentTaskCard.value.task_id)
      if (matched) {
        agentTaskCard.value = matched
      }
    }
  } catch (error) {
    pushAgentLog(error?.response?.data?.detail || error?.message || '加载最近 Agent 任务失败', 'warning')
  } finally {
    agentTaskListLoading.value = false
  }
}

async function retryAgentTask(taskId) {
  const normalizedTaskId = String(taskId || '').trim()
  if (!normalizedTaskId) return
  agentTaskRetryingId.value = normalizedTaskId
  try {
    const response = await wechatAnnotatorAPI.retryAgentTask(normalizedTaskId)
    const task = upsertAgentTask(response?.data?.task)
    if (task) {
      agentTaskCard.value = task
      pushAgentLog(`任务已重新入队：${task.task_id}，当前状态 ${formatAgentTaskStatus(task.status)}。`, 'info')
    }
    await loadRecentAgentTasks()
    syncAgentTaskPolling()
  } catch (error) {
    pushAgentLog(error?.response?.data?.detail || error?.message || '重试 Agent 任务失败', 'warning')
  } finally {
    agentTaskRetryingId.value = ''
  }
}

function setAccountSearchFeedback(type, title, message = '') {
  accountSearchFeedback.value = { type, title, message }
}

async function runAgentCommand() {
  const text = agentCommand.value.trim()
  if (!text) {
    setAgentActionFeedback('warning', '无法执行 Agent 指令', '请输入自然语言指令。')
    return
  }

  const runId = `${Date.now()}-${Math.random().toString(16).slice(2)}`
  const abortController = new AbortController()
  agentActionFeedback.value = null
  agentTaskCard.value = null
  agentLastResult.value = null
  latestAgentTargetArticle.value = null
  agentLogs.value = []
  showAgentLogs.value = false
  startAgentRun(runId, abortController)
  agentStatusText.value = agentActiveRunCount.value > 1 ? `正在并行执行 ${agentActiveRunCount.value} 项 Agent 任务…` : '正在执行 Agent 指令…'
  agentBrainState.value = { visible: false, source: '', sourceLabel: '', intent: '', intentLabel: '', supported: true, message: '', reply: '', title: '', tone: 'info', planTitle: '', planSteps: [], diagnostics: { visible: false, summary: '', detail: '', chips: [], cards: [], suggestions: [] } }
  agentLastSavedAt.value = Date.now()
  agentLeaveNoticeShown.value = false
  agentRestoreNotice.value = { visible: false, title: '', message: '', command: '', tone: 'info' }
  persistAgentPanelState()
  let finalData = null
  const memoryPayload = buildAgentSessionMemoryPayload()
  pushAgentLog(`已提交新任务：${text}`, 'info')

  try {
    await streamWechatAgentCommand({
      command: text,
      default_account_id: crawlAccountId.value.trim() || 'my_wechat_account',
      frequency_days: 30,
      window_days: 365,
      force: true,
      session_memory: memoryPayload,
    }, {
      onLoading: (event) => {
        const message = event?.message || '正在执行…'
        agentStatusText.value = message
        agentLastSavedAt.value = Date.now()
        pushAgentLog(message, 'loading')
      },
      onParsed: (event) => {
        const parsed = event?.data || {}
        agentLastResult.value = { parsed }
        agentBrainState.value = buildAgentBrainState(parsed)
        appendBrainDiagnosticHistory(parsed, agentBrainState.value.source)
        agentStatusText.value = parsed?.capability_supported === false
          ? '已返回能力说明，当前不会进入公众号执行链路。'
          : '指令解析完成，开始执行阶段任务…'
        agentLastSavedAt.value = Date.now()
        if (parsed?.capability_supported === false || agentBrainState.value.reply || parsed?.capability_message) {
          pushAgentLog(agentBrainState.value.message, agentBrainState.value.supported ? 'info' : 'warning')
        }
        if (parsed?.capability_supported !== false) {
          updateAgentSessionMemory({
            recentArticleTitle: parsed?.article_title || agentSessionMemory.value.recentArticleTitle,
            recentUrls: Array.isArray(parsed?.urls) && parsed.urls.length ? parsed.urls : agentSessionMemory.value.recentUrls,
          }, { clearFailure: true })
        }
        if (parsed?.capability_supported === false) {
          setAgentActionFeedback('warning', 'Agent 能力说明', agentBrainState.value.reply || agentBrainState.value.message)
        }
      },
      onStepStart: (event) => {
        const name = event?.name || 'step'
        const message = event?.message || `${name} 开始`
        agentStatusText.value = message
        agentLastSavedAt.value = Date.now()
        pushAgentLog(toAgentNarration(message), 'loading')
      },
      onNote: (event) => {
        const message = String(event?.message || '').trim()
        if (!message) return
        const narrated = toAgentNarration(message)
        agentStatusText.value = narrated
        agentLastSavedAt.value = Date.now()
        const noteStatus = /成功|已完成|已解析出/.test(message)
          ? 'resolved'
          : /失败|受限|跳过/.test(message)
            ? 'warning'
            : 'info'
        pushAgentLog(narrated, noteStatus)
      },
      onStepDone: (event) => {
        const name = event?.name || 'step'
        if (name === 'observe') {
          const result = event?.result || {}
          const resolvedAccount = result?.resolved_account_id || result?.requested_account_id || '未确定账号'
          const cookieText = result?.has_cookie_session ? '已检测到 cookie 会话' : '未检测到 cookie 会话'
          const historyText = result?.has_history_url ? '存在历史页入口' : '暂无历史页入口'
          updateAgentSessionMemory({
            recentAccountId: result?.resolved_account_id || '',
            recentDisplayName: result?.matched_display_name || '',
            recentHistoryUrl: result?.history_url || '',
            recentArticleTitle: result?.article_title || agentSessionMemory.value.recentArticleTitle,
            recentUrls: Array.isArray(result?.seed_urls) && result.seed_urls.length ? result.seed_urls : agentSessionMemory.value.recentUrls,
          }, { clearFailure: true })
          pushAgentLog(`观察完成：账号=${resolvedAccount}，${cookieText}，${historyText}，已有文章 ${result?.existing_article_count || 0} 篇`, 'resolved')
        } else if (name === 'reason') {
          const result = event?.result || {}
          const action = result?.action || 'unknown'
          updateAgentSessionMemory({
            recentDecision: action,
            recentAccountId: result?.account_id || agentSessionMemory.value.recentAccountId,
            recentDisplayName: result?.display_name || result?.search_query || agentSessionMemory.value.recentDisplayName,
            recentArticleTitle: result?.article_title || agentSessionMemory.value.recentArticleTitle,
            recentUrls: Array.isArray(result?.seed_urls) && result.seed_urls.length ? result.seed_urls : agentSessionMemory.value.recentUrls,
          }, { clearFailure: true })
          if (action === 'crawl_history_url') {
            pushAgentLog('决策完成：优先复用历史页与 cookie，会自动补抓未采文章', 'resolved')
          } else if (action === 'crawl_seed_urls') {
            pushAgentLog('决策完成：检测到可直接抓取的公众号链接，进入直抓模式', 'resolved')
          } else if (action === 'desktop_capture') {
            pushAgentLog('决策完成：直抓入口不足，回退到桌面微信采集模式', 'resolved')
          } else if (action === 'request_user_intervention') {
            pushAgentLog(result?.message || '决策完成：当前需要人工介入后才能继续', 'warning')
          } else {
            pushAgentLog(`决策完成：${action}`, 'resolved')
          }
        } else if (name === 'collect') {
          const rr = event?.result?.run_result || {}
          const resolvedCount = Number(event?.result?.resolved_url_count || 0)
          const duplicateCount = Number(event?.result?.duplicate_url_count || rr?.duplicate_url_count || (Array.isArray(event?.result?.duplicate_article_urls) ? event.result.duplicate_article_urls.length : 0) || 0)
          const blockedCount = Array.isArray(rr?.blocked_articles) ? rr.blocked_articles.length : 0
          const failedCount = Array.isArray(rr?.failed_articles) ? rr.failed_articles.length : 0
          const skippedWindow = Number(rr?.skipped_time_window || 0)
          const processed = Number(rr?.processed_articles || 0)
          const created = Number(rr?.new_articles || 0)
          const blockedReasonText = describeBlockedReasons(rr?.blocked_articles)
          const reasonParts = []
          if (resolvedCount > 0) reasonParts.push(`解析到 ${resolvedCount} 条候选链接`)
          if (duplicateCount > 0) reasonParts.push(`重复链接 ${duplicateCount} 条`)
          if (skippedWindow > 0) reasonParts.push(`时间窗过滤 ${skippedWindow} 条`)
          if (blockedCount > 0) reasonParts.push(`页面受限 ${blockedCount} 条`)
          if (failedCount > 0) reasonParts.push(`抓取失败 ${failedCount} 条`)
          pushAgentLog(
            `采集完成：处理 ${processed} 篇，新增 ${created} 篇${reasonParts.length ? `；${reasonParts.join('，')}` : ''}`,
            created > 0 ? 'success' : 'warning'
          )
          if (blockedCount > 0) {
            pushAgentLog(`说明：页面受限更接近“公众号页面访问被拦住”，更像是命中微信验证页或页面保护，不一定是账号本身被风控${blockedReasonText ? `；拦截特征：${blockedReasonText}` : ''}。`, 'warning')
          } else if (processed <= 0 && resolvedCount <= 0 && duplicateCount <= 0) {
            pushAgentLog('说明：这一轮没有真正解析出可处理链接，优先怀疑链接失效、历史页为空，或页面已经跳到微信验证/受限页面。', 'warning')
          }
        } else if (name === 'desktop_collect') {
          const capture = event?.result?.capture || {}
          const importResult = event?.result?.import_result || {}
          const capturePath = capture?.session_dir || '桌面会话目录'
          const imported = importResult?.imported_articles || importResult?.imported_count || 0
          pushAgentLog(`桌面采集完成：已生成采集包 ${capturePath}，导入文章 ${imported} 篇`, 'success')
        } else if (name === 'intervention') {
          const result = event?.result || {}
          pushAgentLog(result?.message || '需要人工介入后再继续执行', 'warning')
        } else if (name === 'clean') {
          const cr = event?.result || {}
          pushAgentLog(`清洗完成：文章 ${cr.cleaned_articles || 0}，入库块 ${cr.ingested_chunks || 0}`, 'success')
        } else {
          pushAgentLog(`${name} 完成`, 'success')
        }
      },
      onDone: (event) => {
        finalData = event?.data || {}
        agentLastResult.value = finalData
      },
      onError: (message) => {
        if (message === '__ABORTED__') {
          agentStatusText.value = 'Agent 执行已取消'
          agentLastSavedAt.value = Date.now()
          return
        }
        agentStatusText.value = message || 'Agent 执行失败'
        agentLastSavedAt.value = Date.now()
      },
    }, { signal: abortController.signal })

    const parsed = finalData?.parsed || {}
    const steps = finalData?.steps || []
    const accountId = parsed?.account_id || crawlAccountId.value.trim()

    agentStatusText.value = parsed?.capability_supported === false
      ? '已返回页面能力说明'
      : `执行完成：${steps.length} 个阶段`
    agentLastSavedAt.value = Date.now()
    if (parsed?.capability_supported === false) {
      pushAgentLog('本轮未进入公众号执行链路，只返回了页面能力说明。', 'done')
    } else if (hasAgentExecutionSteps(finalData)) {
      pushAgentLog('真实执行阶段已完成，可继续查看结果或进入标注工作台。', 'done')
    } else {
      pushAgentLog('本轮没有触发抓取、桌面采集或清洗阶段。', 'done')
    }
    pushAgentLog(buildAgentExecutionSummary(finalData), 'done')

    if (accountId) {
      crawlAccountId.value = accountId
    }
    if (finalData?.updated_session_memory) {
      agentSessionMemory.value = normalizeAgentSessionMemory(finalData.updated_session_memory)
    } else {
      updateAgentSessionMemory({
        recentAccountId: accountId || agentSessionMemory.value.recentAccountId,
      }, { clearFailure: true })
    }

    await loadArticles({ keepSelected: false, autoSelectFirst: false })
    await loadLocalAccountOverview()
    agentOrchestration.value = normalizeAgentOrchestration(finalData?.orchestration)
    agentTaskCard.value = normalizeAgentTask(finalData?.task)
    if (agentTaskCard.value?.task_id) {
      upsertAgentTask(agentTaskCard.value)
      pushAgentLog(`已生成正式任务记录：${agentTaskCard.value.task_id}，当前状态 ${formatAgentTaskStatus(agentTaskCard.value.status)}。`, 'info')
    }
    if (agentOrchestration.value?.task?.taskId) {
      pushAgentLog(`编排状态：${formatAgentOrchestrationStatus(agentOrchestration.value.task.status)}；当前 ${formatAgentRoleName(agentOrchestration.value.task.currentAgent)}。`, 'info')
      if (agentOrchestration.value.nextAgent) {
        pushAgentLog(`下一跳已指向 ${formatAgentRoleName(agentOrchestration.value.nextAgent)}。`, 'info')
      }
      if (agentOrchestration.value.governance?.summary) {
        pushAgentLog(`治理摘要：${agentOrchestration.value.governance.summary}`, agentOrchestration.value.governance.status === 'failed' ? 'warning' : 'resolved')
      }
      if (agentOrchestration.value.evaluation?.summary) {
        pushAgentLog(`评测摘要：${agentOrchestration.value.evaluation.summary}`, 'resolved')
      }
    }
    await loadRecentAgentTasks()

    const picked = pickAgentTargetArticle(finalData)
    const target = picked?.target ? findArticleByIds(picked.target.account_id, picked.target.article_id) : null
    if (target) {
      latestAgentTargetArticle.value = {
        account_id: target.account_id,
        article_id: target.article_id,
        title: target.title || target.article_id,
      }
      pushAgentLog(`本轮文章已写入历史列表：${target.title || target.article_id}，正在自动进入文章页。`, 'success')
      await selectArticle(target)
    } else {
      latestAgentTargetArticle.value = null
    }

    agentCommand.value = ''

    if (parsed?.capability_supported === false) {
      setAgentActionFeedback(
        'warning',
        buildAgentFeedbackTitle(finalData),
        buildAgentExecutionSummary(finalData),
      )
    } else if (picked.newArticles > 0) {
      setAgentActionFeedback(
        'success',
        buildAgentFeedbackTitle(finalData, {
          pickedNewArticles: picked.newArticles,
        }),
        buildAgentCompletionFeedbackMessage(finalData, {
          pickedNewArticles: picked.newArticles,
          hasTarget: !!target,
        })
      )
    } else {
      if (!target) {
        clearSelection('本次没有定位到新文章，已清空旧文章显示，避免误判为抓取到了上一条文章。')
      }
      setAgentActionFeedback(
        'warning',
        buildAgentFeedbackTitle(finalData, {
          pickedNewArticles: 0,
        }),
        buildAgentCompletionFeedbackMessage(finalData, {
          pickedNewArticles: 0,
          hasTarget: !!target,
        })
      )
    }
  } catch (err) {
    if (err?.name === 'AbortError') {
      pushAgentLog('用户手动停止 Agent 执行', 'warning')
      setAgentActionFeedback('warning', 'Agent 已停止', '当前任务已被手动取消。')
      return
    }
    const msg = err?.response?.data?.detail || err?.message || 'Agent 执行失败'
    agentStatusText.value = msg
    agentLastSavedAt.value = Date.now()
    pushAgentLog(msg, 'error')
    updateAgentSessionMemory({ recentFailureReason: msg })
    setAgentActionFeedback('error', 'Agent 执行失败', msg)
  } finally {
    finishAgentRun(runId, abortController)
    if (agentRunning.value) {
      agentStatusText.value = `仍有 ${agentActiveRunCount.value} 项 Agent 任务在执行中…`
    }
    persistAgentPanelState()
  }
}

function stopAgentCommand() {
  if (!agentRunning.value || !agentAbortController.value) return
  agentAbortController.value.abort()
}

onBeforeRouteLeave(() => {
  if (agentRunning.value && !agentLeaveNoticeShown.value) {
    ElMessage.info('离开后此页面会继续运行')
    agentLeaveNoticeShown.value = true
  }
  if (agentRunning.value) {
    agentDetachedRunning.value = true
    persistAgentPanelState()
  }
  return true
})

async function runQuickIngest() {
  const account = crawlAccountId.value.trim() || 'my_wechat_account'
  agentCommand.value = `清洗并入库，账号: ${account}`
  await runAgentCommand()
}

function openAnnotatorEntry() {
  showReviewWorkspace.value = true
  activeAnnotatorPublisherName.value = ''
  if (!activeAnnotatorAccountId.value && crawlAccountId.value.trim()) {
    activeAnnotatorAccountId.value = crawlAccountId.value.trim()
  }
  const first = activeAnnotatorAccountId.value
    ? flatArticles.value.find((item) => item.account_id === activeAnnotatorAccountId.value)
    : flatArticles.value[0]
  if (!selectedKey.value && first) {
    selectArticle(first)
    return
  }
  syncReviewRouteState(activeAnnotatorAccountId.value, articleDetail.value?.article?.article_id || '', false)
}

async function closeAnnotatorEntry() {
  showReviewWorkspace.value = false
  activeAnnotatorAccountId.value = ''
  activeAnnotatorPublisherName.value = ''
  await clearReviewRouteState(true)
}

async function selectArticle(item) {
  showReviewWorkspace.value = true
  activeAnnotatorAccountId.value = item.account_id || activeAnnotatorAccountId.value
  selectedKey.value = `${item.account_id}:${item.article_id}`
  articleLoading.value = true
  try {
    const res = await wechatAnnotatorAPI.getArticle(item.account_id, item.article_id)
    articleDetail.value = normalizeArticleDetail(res.data)
    instruction.value = res.data.last_instruction || ''
    lastSavedAnnotationVersion.value = buildAnnotationVersion(articleDetail.value, instruction.value)
    instructionTimeline.value = res.data.last_instruction
      ? [
          {
            id: `seed:${selectedKey.value}`,
            type: '最近指令',
            time: res.data.last_instruction_at || '',
            text: res.data.last_instruction,
            note: '从本地标注文件加载',
          },
        ]
      : []
    await syncReviewRouteState(item.account_id, item.article_id, true)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '加载文章失败')
  } finally {
    articleLoading.value = false
  }
}

async function reloadArticle() {
  const [accountId, articleId] = selectedKey.value.split(':')
  if (!accountId || !articleId) return
  await selectArticle({ account_id: accountId, article_id: articleId })
  await loadArticles(true)
}

async function applyInstruction() {
  const text = instruction.value.trim()
  if (!text) {
    ElMessage.warning('请输入自然语言标注指令')
    return
  }
  const [accountId, articleId] = selectedKey.value.split(':')
  if (!accountId || !articleId) return

  applying.value = true
  try {
    const res = await wechatAnnotatorAPI.applyInstruction(accountId, articleId, text)
    articleDetail.value = normalizeArticleDetail(res.data.review_payload)
    instruction.value = text
    pushTimeline('已应用', text, `变更 ${res.data.changed || 0} 条标注`)
    ElMessage.success(`已应用 ${res.data.changed || 0} 条标注`)
    await loadArticles(true)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '应用指令失败')
  } finally {
    applying.value = false
  }
}

async function autoFillAnnotations(overwriteExisting) {
  const [accountId, articleId] = selectedKey.value.split(':')
  if (!accountId || !articleId) return

  autofilling.value = true
  try {
    const res = await wechatAnnotatorAPI.autoFillAnnotations(accountId, articleId, overwriteExisting)
    articleDetail.value = normalizeArticleDetail(res.data.review_payload)
    pushTimeline(
      overwriteExisting ? '自动预填(覆盖)' : '自动预填(仅空白)',
      '系统根据已提取结果自动填充结构化标注模板',
      `summary ${res.data.filled_summary || 0} · tags ${res.data.filled_tags || 0} · notes ${res.data.filled_notes || 0}`,
    )
    ElMessage.success(`自动预填完成：摘要 ${res.data.filled_summary || 0}，标签 ${res.data.filled_tags || 0}，备注 ${res.data.filled_notes || 0}`)
    await loadArticles(true)
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '自动预填失败')
  } finally {
    autofilling.value = false
  }
}

async function downloadHighRes(img, event) {
  event.stopPropagation()
  const [accountId, articleId] = selectedKey.value.split(':')
  if (!accountId || !articleId) return

  downloadingHires.value = img.image_id
  try {
    const res = await wechatAnnotatorAPI.downloadHighResImage(accountId, articleId, img.image_id)
    if (res.data.ok) {
      ElMessage.success(res.data.message || `下载成功：${res.data.file_size_kb}KB`)
      if (res.data.download_image_url) {
        img.url = res.data.download_image_url
        const imageResp = await fetch(res.data.download_image_url, { credentials: 'include' })
        if (imageResp.ok) {
          const blob = await imageResp.blob()
          const mime = blob.type || ''
          const suffix = mime.includes('png')
            ? '.png'
            : mime.includes('webp')
              ? '.webp'
              : mime.includes('gif')
                ? '.gif'
                : '.jpg'
            const saveMode = await saveBlobToUserPath(blob, `${img.image_id}_hires${suffix}`)
            if (saveMode === 'custom-path') {
              ElMessage.info('高清图已保存到你选择的本地路径')
            } else {
              ElMessage.info('高清图已下载到当前浏览器默认下载目录')
            }
        }
      }
    } else {
      ElMessage.warning(res.data.message || '暂无更高清版本')
    }
  } catch (err) {
    if (String(err?.name || '') === 'AbortError') {
      ElMessage.info('你已取消保存')
      return
    }
    ElMessage.error(err?.response?.data?.detail || '下载失败')
  } finally {
    downloadingHires.value = null
  }
}

async function exportKeptImages() {
  const [accountId, articleId] = selectedKey.value.split(':')
  if (!accountId || !articleId) return

  exporting.value = true
  try {
    const metaRes = await wechatAnnotatorAPI.getKeptImagesExportMeta(accountId, articleId)
    const exportVersion = metaRes?.data?.export_version
    const history = getExportHistory()
    const historyKey = `${accountId}:${articleId}`

    if (exportVersion && history[historyKey] === exportVersion) {
      ElMessage.warning('当前版本已下载过，已阻止重复下载')
      return
    }

    const res = await wechatAnnotatorAPI.exportKeptImages(accountId, articleId)
    if (res.status === 200 && res.data instanceof Blob) {
      await saveBlobToUserPath(res.data, `${articleId}_kept_images.zip`)
      if (exportVersion) {
        history[historyKey] = exportVersion
        setExportHistory(history)
      }
      ElMessage.success('已下载已保留图片集')
    } else {
      ElMessage.error('导出失败')
    }
  } catch (err) {
    if (String(err?.name || '') === 'AbortError') {
      ElMessage.info('你已取消保存')
      return
    }
    ElMessage.error(err?.response?.data?.detail || '导出失败')
  } finally {
    exporting.value = false
  }
}

async function saveAnnotations() {
  const [accountId, articleId] = selectedKey.value.split(':')
  if (!accountId || !articleId || !articleDetail.value) return

  const currentVersion = buildAnnotationVersion(articleDetail.value, instruction.value)
  if (currentVersion === lastSavedAnnotationVersion.value) {
    ElMessage.warning('当前标注内容与上次保存完全一致，已阻止重复保存')
    return
  }

  saving.value = true
  try {
    const annotations = (articleDetail.value.images || []).map((img) => ({
      image_id: img.image_id,
      local_path: img.local_path,
      manual_summary: img.manual_summary || '',
      manual_tags: String(img.manual_tags_text || '')
        .split(/[，,]/)
        .map((t) => t.trim())
        .filter(Boolean),
      manual_notes: img.manual_notes || '',
      scene_annotation: parseSceneAnnotationText(img.scene_annotation_text),
      scene_annotation_text: String(img.scene_annotation_text || '').trim(),
      keep_for_index: !!img.keep_for_index,
    }))

    const res = await wechatAnnotatorAPI.saveAnnotations(accountId, articleId, annotations, instruction.value.trim())
    if (res?.data?.duplicate) {
      lastSavedAnnotationVersion.value = currentVersion
      ElMessage.warning('当前标注已经保存过，未重复写入')
      return
    }
    pushTimeline('已保存', instruction.value.trim() || '手工修改', `保存 ${annotations.length} 张图片的标注`)
    const keptCount = articleDetail.value.images.filter((img) => img.keep_for_index).length
    ElMessage.success(`已保存标注和图片：保留 ${keptCount} 张，剔除 ${annotations.length - keptCount} 张`)
    lastSavedAnnotationVersion.value = currentVersion
    if (res?.data?.selected_images_path) {
      ElMessage.info(`已导出保留图片清单：${res.data.selected_images_path}`)
    }
    await loadArticles({ keepSelected: true, autoSelectFirst: true })
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

onMounted(async () => {
  restoreBrainDiagnosticHistory()
  restoreAgentPanelState()
  await restoreAgentServerState()
  await loadEvaluationTrendHistory()
  await loadRecentAgentTasks()
  if (agentTaskCard.value?.task_id) {
    refreshAgentTaskCard()
  }
  restoreLocalAccountOverviewState()
  restoreLocalAccountOverviewCache()
  await loadArticles({ keepSelected: false, autoSelectFirst: false })
  await loadLocalAccountOverview()
  await refreshDesktopProfiles()

  if (route.query.view === 'review') {
    showReviewWorkspace.value = true
    activeAnnotatorAccountId.value = String(route.query.account_id || '').trim()
    const routeArticleId = String(route.query.article_id || '').trim()
    const target = routeArticleId
      ? flatArticles.value.find((item) => item.article_id === routeArticleId && (!activeAnnotatorAccountId.value || item.account_id === activeAnnotatorAccountId.value))
      : (activeAnnotatorAccountId.value
          ? flatArticles.value.find((item) => item.account_id === activeAnnotatorAccountId.value)
          : flatArticles.value[0])
    if (target) {
      await selectArticle(target)
    }
  }
})

onBeforeUnmount(() => {
  stopAgentTaskPolling()
  if (agentServerPersistTimer) {
    clearTimeout(agentServerPersistTimer)
    agentServerPersistTimer = null
  }
  try {
    localStorage.setItem(AGENT_PANEL_STATE_STORAGE_KEY, JSON.stringify(snapshotAgentPanelState()))
  } catch {
    // ignore storage quota errors for local UI state
  }
  flushPersistAgentServerState()
})

watch(agentTaskCard, () => {
  syncAgentTaskPolling()
}, { deep: true })

watch([
  agentCommand,
  agentRunning,
  agentStatusText,
  agentLogs,
  agentActionFeedback,
  agentLeaveNoticeShown,
  agentDetachedRunning,
  crawlAccountId,
  selectedHistoryUrl,
  selectedAccountDisplayName,
], () => {
  persistAgentPanelState()
}, { deep: true })

watch(() => route.query.view, (view) => {
  if (view === 'review') return
  showReviewWorkspace.value = false
  activeAnnotatorAccountId.value = ''
  activeAnnotatorPublisherName.value = ''
})
</script>

<style scoped>
.wechat-annotator-page {
  min-height: calc(100vh - 60px);
  max-height: calc(100vh - 60px);
  padding: 18px;
  overflow: auto;
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.18), transparent 28%),
    radial-gradient(circle at top right, rgba(20, 184, 166, 0.12), transparent 24%),
    linear-gradient(180deg, #f4f7fb 0%, #eef3fa 100%);
}

.page-shell {
  display: grid;
  grid-template-columns: 280px 1fr 280px;
  gap: 18px;
  align-items: start;
}

.page-shell.agent-only {
  grid-template-columns: minmax(960px, 1fr);
  justify-content: center;
}

.page-shell.review-only {
  grid-template-columns: minmax(0, 1fr);
}

.page-shell.review-only .source-panel,
.page-shell.review-only .workspace {
  grid-column: 1 / -1;
}

.page-shell.agent-only .sidebar {
  position: relative;
  top: 0;
  max-height: none;
}

.card-glass {
  background: rgba(255, 255, 255, 0.88);
  border: 1px solid rgba(148, 163, 184, 0.18);
  backdrop-filter: blur(16px);
  box-shadow: 0 18px 50px rgba(15, 23, 42, 0.08);
}

.sidebar {
  border-radius: 22px;
  padding: 18px;
  position: sticky;
  top: 18px;
  max-height: calc(100vh - 96px);
  overflow: auto;
}

.sidebar-header h1,
.hero-copy h2 {
  margin: 6px 0 0;
  font-size: 28px;
  line-height: 1.2;
  color: #0f172a;
}

.sidebar-header p,
.hero-copy p,
.panel-desc {
  margin: 8px 0 0;
  color: #64748b;
  line-height: 1.6;
}

.kicker {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: #2563eb;
}

.workspace-overview-card,
.agent-summary-card,
.review-entry-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  margin-top: 14px;
  border-radius: 16px;
  border: 1px solid rgba(59, 130, 246, 0.14);
  background: linear-gradient(180deg, rgba(239, 246, 255, 0.92) 0%, rgba(255, 255, 255, 0.9) 100%);
}

.workspace-overview-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.workspace-overview-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.workspace-overview-account-row {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  overflow-y: hidden;
  padding-bottom: 4px;
  scroll-snap-type: x proximity;
}

.workspace-overview-account-row::-webkit-scrollbar {
  height: 8px;
}

.workspace-overview-account-row::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.45);
  border-radius: 999px;
}

.workspace-overview-account-chip {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 290px;
  flex: 0 0 auto;
  padding: 10px 12px;
  text-align: left;
  border-radius: 14px;
  border: 1px solid rgba(191, 219, 254, 0.9);
  background: rgba(255, 255, 255, 0.86);
  cursor: pointer;
  scroll-snap-align: start;
}

.workspace-overview-account-chip:hover {
  border-color: rgba(37, 99, 235, 0.32);
}

.workspace-overview-account-name {
  font-size: 12px;
  font-weight: 800;
  color: #0f172a;
}

.workspace-overview-account-meta {
  font-size: 11px;
  color: #64748b;
}

.brain-stats-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  margin-top: 14px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.86);
}

.brain-stats-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.brain-stats-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.brain-stats-metric-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.88);
}

.brain-stats-metric-card[data-tone='success'] {
  border-color: rgba(34, 197, 94, 0.22);
  background: rgba(240, 253, 244, 0.94);
}

.brain-stats-metric-card[data-tone='warning'] {
  border-color: rgba(245, 158, 11, 0.24);
  background: rgba(255, 251, 235, 0.95);
}

.brain-stats-metric-card[data-tone='danger'] {
  border-color: rgba(239, 68, 68, 0.24);
  background: rgba(254, 242, 242, 0.95);
}

.brain-stats-metric-label {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
}

.brain-stats-metric-value {
  font-size: 24px;
  font-weight: 800;
  color: #0f172a;
}

.brain-stats-metric-note {
  font-size: 12px;
  line-height: 1.5;
  color: #475569;
}

.brain-stats-reason-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.brain-stats-reason-chip {
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #1d4ed8;
  background: rgba(219, 234, 254, 0.9);
}

.evaluation-trend-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  margin-top: 14px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.88);
}

.evaluation-trend-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.evaluation-trend-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.evaluation-trend-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.evaluation-trend-metric-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.88);
}

.evaluation-trend-metric-card[data-tone='success'] {
  border-color: rgba(34, 197, 94, 0.24);
  background: rgba(240, 253, 244, 0.95);
}

.evaluation-trend-metric-card[data-tone='warning'] {
  border-color: rgba(245, 158, 11, 0.24);
  background: rgba(255, 251, 235, 0.95);
}

.evaluation-trend-metric-card[data-tone='danger'] {
  border-color: rgba(239, 68, 68, 0.24);
  background: rgba(254, 242, 242, 0.95);
}

.evaluation-trend-metric-label {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
}

.evaluation-trend-metric-value {
  font-size: 24px;
  font-weight: 800;
  color: #0f172a;
}

.evaluation-trend-metric-note {
  font-size: 12px;
  line-height: 1.5;
  color: #475569;
}

.evaluation-trend-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.evaluation-compare-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: #2563eb;
}

.evaluation-trend-chart-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: linear-gradient(180deg, rgba(239, 246, 255, 0.82), rgba(248, 250, 252, 0.94));
}

.evaluation-trend-chart-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
}

.evaluation-trend-chart-title {
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.evaluation-trend-chart-window,
.evaluation-trend-chart-caption,
.evaluation-trend-chart-labels {
  font-size: 12px;
  color: #475569;
}

.evaluation-trend-chart {
  width: 100%;
  height: 136px;
  overflow: visible;
}

.evaluation-trend-chart-grid-line {
  stroke: rgba(148, 163, 184, 0.28);
  stroke-width: 1;
  stroke-dasharray: 4 4;
}

.evaluation-trend-chart-line {
  fill: none;
  stroke: #2563eb;
  stroke-width: 3;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.evaluation-trend-chart-point {
  fill: #f59e0b;
  stroke: rgba(255, 255, 255, 0.94);
  stroke-width: 2;
}

.evaluation-trend-chart-point[data-tone='success'] {
  fill: #16a34a;
}

.evaluation-trend-chart-labels {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.evaluation-trend-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(248, 250, 252, 0.82);
}

.evaluation-trend-item-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.evaluation-trend-item-title {
  font-size: 13px;
  font-weight: 800;
  color: #0f172a;
}

.evaluation-trend-item-time {
  font-size: 11px;
  color: #64748b;
}

.evaluation-trend-item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: #2563eb;
}

.evaluation-trend-item-summary {
  font-size: 12px;
  line-height: 1.5;
  color: #475569;
}


.failure-diagnostic-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.94);
}

.failure-diagnostic-card[data-tone='warning'] {
  border-color: rgba(245, 158, 11, 0.22);
  background: rgba(255, 251, 235, 0.95);
}

.failure-diagnostic-card[data-tone='danger'] {
  border-color: rgba(239, 68, 68, 0.22);
  background: rgba(254, 242, 242, 0.95);
}

.failure-diagnostic-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.failure-diagnostic-title {
  font-size: 13px;
  font-weight: 800;
  color: #0f172a;
}

.failure-diagnostic-status {
  margin-top: 2px;
  font-size: 11px;
  color: #64748b;
}

.failure-diagnostic-summary,
.failure-diagnostic-detail {
  font-size: 12px;
  line-height: 1.6;
  color: #475569;
}

.failure-diagnostic-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.failure-diagnostic-chip-row span {
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #7c2d12;
  background: rgba(254, 215, 170, 0.9);
}


.local-account-overview-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  margin-top: 14px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.86);
}

.local-account-overview-card.compact {
  margin-top: 0;
  padding: 12px;
  background: rgba(248, 250, 252, 0.92);
}

.local-account-overview-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.local-account-overview-head-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

.history-panel-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.local-account-overview-collapsed-tip {
  font-size: 12px;
  color: #64748b;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(248, 250, 252, 0.86);
  border: 1px dashed rgba(148, 163, 184, 0.2);
}

.local-account-overview-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.local-account-overview-list.compact {
  max-height: 220px;
  overflow: auto;
}

.local-account-overview-filters {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.local-account-filter-chip {
  padding: 5px 10px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.92);
  color: #475569;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
}

.local-account-filter-chip[data-active='true'] {
  color: #1d4ed8;
  border-color: rgba(37, 99, 235, 0.24);
  background: rgba(219, 234, 254, 0.95);
}

.local-account-overview-item {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  padding: 12px;
  text-align: left;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.88);
  cursor: pointer;
  transition: border-color .18s ease, transform .18s ease, box-shadow .18s ease;
}

.local-account-overview-item.compact {
  padding: 10px 12px;
}

.local-account-overview-item:hover {
  border-color: rgba(37, 99, 235, 0.28);
  transform: translateY(-1px);
  box-shadow: 0 10px 20px rgba(37, 99, 235, 0.08);
}

.local-account-overview-title-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
}

.local-account-overview-actions {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.local-account-overview-name {
  font-size: 13px;
  font-weight: 800;
  color: #0f172a;
}

.local-account-overview-badge {
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #92400e;
  background: rgba(254, 243, 199, 0.95);
}

.local-account-overview-badge[data-tone='success'] {
  color: #166534;
  background: rgba(220, 252, 231, 0.95);
}

.local-account-overview-meta {
  font-size: 12px;
  color: #475569;
}

.local-account-overview-submeta {
  font-size: 11px;
  color: #64748b;
}

.agent-summary-title,
.review-entry-title {
  font-size: 13px;
  font-weight: 800;
  color: #0f172a;
}

.agent-summary-text,
.review-entry-text {
  font-size: 13px;
  line-height: 1.6;
  color: #475569;
}

.agent-summary-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-summary-stats span {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  color: #1d4ed8;
  background: rgba(219, 234, 254, 0.9);
}

.block-search {
  margin: 16px 0 12px;
}

.crawl-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  margin-bottom: 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.82);
}

.crawl-panel-header.compact {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.crawl-panel-inline-meta {
  display: inline-flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
  font-size: 11px;
  color: #64748b;
}

.crawl-panel-inline-meta span {
  padding: 4px 10px;
  border-radius: 999px;
  background: rgba(248, 250, 252, 0.92);
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.agent-advanced-panel {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.86);
}

.agent-inline-details {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  background: rgba(248, 250, 252, 0.86);
}

.agent-inline-details summary {
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  cursor: pointer;
  padding: 12px 14px;
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.agent-inline-details summary::-webkit-details-marker {
  display: none;
}

.agent-inline-details-body {
  padding: 0 12px 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.14);
}

.agent-advanced-panel summary {
  list-style: none;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  cursor: pointer;
  padding: 12px 14px;
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.agent-advanced-panel summary::-webkit-details-marker {
  display: none;
}

.agent-advanced-summary {
  font-size: 11px;
  font-weight: 600;
  color: #64748b;
}

.agent-advanced-content {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 0 12px 12px;
  border-top: 1px solid rgba(148, 163, 184, 0.14);
}

.agent-panel {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  margin-bottom: 12px;
  border-radius: 14px;
  background: rgba(255, 255, 255, 0.82);
}

.crawl-panel-title {
  font-size: 13px;
  font-weight: 700;
  color: #1e3a8a;
}

.crawl-account-search-row {
  display: flex;
  gap: 8px;
}

.account-candidate-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 180px;
  overflow-y: auto;
}

.account-candidate {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 4px;
  width: 100%;
  padding: 10px 12px;
  border: 1px solid rgba(59, 130, 246, 0.14);
  border-radius: 12px;
  background: rgba(239, 246, 255, 0.9);
  cursor: pointer;
  text-align: left;
  transition: border-color .18s ease, transform .18s ease, box-shadow .18s ease;
}

.account-candidate:hover {
  border-color: rgba(37, 99, 235, 0.32);
  transform: translateY(-1px);
  box-shadow: 0 10px 20px rgba(37, 99, 235, 0.08);
}

.account-candidate-name {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}

.account-candidate-meta {
  font-size: 11px;
  color: #64748b;
  line-height: 1.5;

.account-candidate-alias {
  font-size: 12px;
  color: #475569;
  line-height: 1.5;
}
}

.crawl-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-meta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}

.agent-meta-pill {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #334155;
  background: rgba(226, 232, 240, 0.9);
}

.agent-meta-pill[data-status='running'] {
  color: #1d4ed8;
  background: rgba(219, 234, 254, 0.95);
}

.agent-meta-text {
  font-size: 12px;
  color: #64748b;
}

.agent-restore-banner {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(59, 130, 246, 0.18);
  background: rgba(239, 246, 255, 0.92);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.agent-restore-banner[data-tone='warning'] {
  border-color: rgba(245, 158, 11, 0.24);
  background: rgba(255, 251, 235, 0.96);
}

.agent-restore-banner-title {
  font-size: 12px;
  font-weight: 800;
  color: #0f172a;
}

.agent-restore-banner-message {
  font-size: 12px;
  line-height: 1.5;
  color: #475569;
}

.agent-restore-banner-command {
  font-size: 12px;
  line-height: 1.5;
  color: #1e293b;
  word-break: break-word;
  padding: 8px 10px;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.78);
  border: 1px dashed rgba(148, 163, 184, 0.28);
}

.agent-restore-banner-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-brain-banner {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(59, 130, 246, 0.18);
  background: rgba(239, 246, 255, 0.92);
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.agent-brain-banner[data-tone='success'] {
  border-color: rgba(34, 197, 94, 0.18);
  background: rgba(240, 253, 244, 0.96);
}

.agent-brain-banner[data-tone='warning'] {
  border-color: rgba(245, 158, 11, 0.24);
  background: rgba(255, 251, 235, 0.96);
}

.agent-brain-banner-title {
  font-size: 12px;
  font-weight: 800;
  color: #0f172a;
}

.agent-brain-banner-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: #475569;
}

.agent-brain-plan {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 2px;
}

.agent-brain-plan-title {
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.agent-brain-plan-step {
  font-size: 12px;
  line-height: 1.6;
  color: #475569;
}

.agent-brain-diagnostics {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.72);
  border: 1px dashed rgba(148, 163, 184, 0.28);
}

.agent-brain-diagnostics-title {
  font-size: 12px;
  font-weight: 800;
  color: #0f172a;
}

.agent-brain-diagnostics-summary,
.agent-brain-diagnostics-detail {
  font-size: 12px;
  line-height: 1.6;
  color: #475569;
}

.agent-brain-diagnostics-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-brain-diagnostics-chips span {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #1d4ed8;
  background: rgba(219, 234, 254, 0.9);
}

.agent-brain-diagnostics-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}

.agent-brain-diagnostics-card {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.82);
}

.agent-brain-diagnostics-card[data-tone='success'] {
  border-color: rgba(34, 197, 94, 0.22);
  background: rgba(240, 253, 244, 0.92);
}

.agent-brain-diagnostics-card[data-tone='warning'] {
  border-color: rgba(245, 158, 11, 0.24);
  background: rgba(255, 251, 235, 0.95);
}

.agent-brain-diagnostics-card[data-tone='danger'] {
  border-color: rgba(239, 68, 68, 0.24);
  background: rgba(254, 242, 242, 0.95);
}

.agent-brain-diagnostics-card-title {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.agent-brain-diagnostics-card-value {
  font-size: 15px;
  font-weight: 800;
  color: #0f172a;
}

.agent-brain-diagnostics-card-note {
  font-size: 12px;
  line-height: 1.5;
  color: #475569;
}

.agent-brain-diagnostics-suggestions {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 2px;
}

.agent-brain-diagnostics-suggestions-title {
  font-size: 12px;
  font-weight: 800;
  color: #0f172a;
}

.agent-brain-diagnostics-suggestion {
  font-size: 12px;
  line-height: 1.6;
  color: #475569;
  padding-left: 14px;
  position: relative;
}

.agent-brain-diagnostics-suggestion::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  background: #2563eb;
}

.agent-orchestration-card {
  margin-top: 12px;
  padding: 12px 14px;
  border-radius: 12px;
  border: 1px solid rgba(14, 116, 144, 0.18);
  background: linear-gradient(180deg, rgba(240, 249, 255, 0.96), rgba(248, 250, 252, 0.96));
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-orchestration-card[data-status='partial_success'] {
  border-color: rgba(245, 158, 11, 0.24);
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.98), rgba(248, 250, 252, 0.96));
}

.agent-orchestration-card[data-status='failed'] {
  border-color: rgba(239, 68, 68, 0.24);
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.98), rgba(248, 250, 252, 0.96));
}

.agent-orchestration-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.agent-orchestration-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #0f766e;
}

.agent-orchestration-title {
  margin-top: 2px;
  font-size: 13px;
  font-weight: 800;
  color: #0f172a;
}

.agent-orchestration-status {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #0f766e;
  background: rgba(204, 251, 241, 0.92);
}

.agent-orchestration-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: #475569;
}

.agent-orchestration-route {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-orchestration-chip {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #155e75;
  background: rgba(224, 242, 254, 0.95);
}

.agent-orchestration-summary {
  font-size: 12px;
  line-height: 1.6;
  color: #334155;
}

.agent-orchestration-governance {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-top: 2px;
}

.agent-orchestration-section-title {
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.agent-memory-banner {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px 14px;
  border-radius: 14px;
  background: linear-gradient(180deg, rgba(241, 245, 249, 0.92), rgba(226, 232, 240, 0.88));
  border: 1px solid rgba(148, 163, 184, 0.28);
}

.agent-memory-banner[data-locked='true'] {
  border-color: rgba(245, 158, 11, 0.34);
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.98), rgba(254, 243, 199, 0.9));
}

.agent-memory-banner-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.agent-memory-banner-title {
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.agent-memory-lock-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #92400e;
  background: rgba(251, 191, 36, 0.22);
  border: 1px solid rgba(245, 158, 11, 0.3);
}

.agent-memory-banner-item {
  font-size: 12px;
  line-height: 1.6;
  color: #475569;
}

.agent-memory-banner-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 2px;
}

.agent-task-card {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(59, 130, 246, 0.18);
  background: linear-gradient(180deg, rgba(239, 246, 255, 0.96), rgba(255, 255, 255, 0.98));
}

.agent-task-card[data-status='deferred'] {
  border-color: rgba(245, 158, 11, 0.24);
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.98), rgba(255, 255, 255, 0.98));
}

.agent-task-card-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.agent-task-card-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.agent-task-card-title-row {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-task-card-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-task-card-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: #92400e;
}

.agent-task-card-title {
  margin-top: 2px;
  font-size: 13px;
  font-weight: 800;
  color: #0f172a;
}

.agent-task-card-status-pill {
  display: inline-flex;
  align-items: center;
  padding: 3px 8px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #475569;
  background: rgba(226, 232, 240, 0.92);
}

.agent-task-card-status-pill[data-status='completed'] {
  color: #166534;
  background: rgba(220, 252, 231, 0.95);
}

.agent-task-card-status-pill[data-status='failed'] {
  color: #b45309;
  background: rgba(255, 237, 213, 0.95);
}

.agent-task-card-status-pill[data-status='queued'],
.agent-task-card-status-pill[data-status='running'],
.agent-task-card-status-pill[data-status='deferred'] {
  color: #1d4ed8;
  background: rgba(219, 234, 254, 0.95);
}

.agent-task-card-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: #475569;
}

.agent-task-card-article-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.agent-task-card-summary {
  font-size: 12px;
  line-height: 1.6;
  color: #334155;
}

.agent-task-card-summary.muted {
  color: #64748b;
}

.agent-task-card-error {
  font-size: 12px;
  line-height: 1.6;
  color: #b91c1c;
}

.agent-task-card-events {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.agent-task-card-event {
  display: flex;
  gap: 8px;
  font-size: 12px;
  line-height: 1.5;
}

.agent-task-card-event-time {
  min-width: 120px;
  color: #64748b;
}

.agent-task-card-event-text {
  color: #334155;
}

.agent-latest-article-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-latest-article-meta {
  font-size: 12px;
  color: #64748b;
}

.agent-task-list-item-article-chip {
  display: inline-flex;
  max-width: 100%;
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(239, 246, 255, 0.92);
  color: #1d4ed8;
  font-size: 12px;
  line-height: 1.4;
}

.agent-latest-article-card {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  padding: 12px 14px;
  border-radius: 16px;
  border: 1px solid rgba(37, 99, 235, 0.18);
  background: linear-gradient(180deg, rgba(239, 246, 255, 0.88), rgba(255, 255, 255, 0.94));
}

.agent-latest-article-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
}

.crawl-status {
  font-size: 12px;
  color: #334155;
}

.desktop-action-feedback {
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.94);
}

.desktop-action-feedback[data-tone='success'] {
  background: linear-gradient(180deg, rgba(240, 253, 244, 0.96), rgba(255, 255, 255, 0.98));
  border-color: rgba(34, 197, 94, 0.18);
}

.desktop-action-feedback[data-tone='warning'] {
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.96), rgba(255, 255, 255, 0.98));
  border-color: rgba(245, 158, 11, 0.18);
}

.desktop-action-feedback[data-tone='error'] {
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.96), rgba(255, 255, 255, 0.98));
  border-color: rgba(239, 68, 68, 0.18);
}

.desktop-action-feedback-title {
  font-size: 12px;
  font-weight: 800;
  color: #0f172a;
}

.desktop-action-feedback-message {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: #475569;
  word-break: break-word;
}

.crawl-panel-tip {
  font-size: 11px;
  color: #475569;
  background: rgba(248, 250, 252, 0.95);
  border: 1px solid rgba(148, 163, 184, 0.16);
  border-radius: 10px;
  padding: 8px 10px;
  word-break: break-all;
}

.crawl-log-scroll {
  padding: 6px 0;
}

.crawl-log-item {
  display: flex;
  gap: 8px;
  font-size: 12px;
  line-height: 1.5;
  padding: 2px 0;
}

.crawl-log-time {
  color: #64748b;
  min-width: 62px;
}

.crawl-log-text {
  color: #1f2937;
  word-break: break-word;
}

.crawl-log-item[data-status='error'] .crawl-log-text {
  color: #b91c1c;
}

.crawl-log-item[data-status='warning'] .crawl-log-text {
  color: #92400e;
}

.crawl-log-item[data-status='success'] .crawl-log-text,
.crawl-log-item[data-status='done'] .crawl-log-text {
  color: #166534;
}

.history-panel {
  border-radius: 22px;
  padding: 16px 18px 14px;
  position: sticky;
  top: 18px;
  max-height: calc(100vh - 96px);
  overflow: hidden;
  display: flex;
  flex-direction: column;
  min-height: 0;
}

.panel-header.compact {
  align-items: center;
}

.history-toolbar {
  display: flex;
  gap: 10px;
  align-items: center;
  margin: 12px 0 10px;
}

.history-search {
  flex: 1;
}

.history-scrollbar {
  flex: 1;
  min-height: 0;
  height: calc(100vh - 228px);
  overflow-y: auto;
  overscroll-behavior: contain;
  -webkit-overflow-scrolling: touch;
  padding-right: 2px;
}

.article-chip {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 14px;
  padding: 10px 12px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: 0.18s ease;
  background: rgba(255, 255, 255, 0.8);
}

.article-chip:hover,
.article-chip.active {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.35);
  box-shadow: 0 10px 24px rgba(37, 99, 235, 0.08);
}

.article-chip-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.35;
}

.article-chip-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
  word-break: break-all;
}

.article-chip-author {
  margin-top: 4px;
  font-size: 12px;
  color: #475569;
}

.article-chip-stats {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
  margin-top: 8px;
  font-size: 12px;
  color: #2563eb;
}

.article-list {
  max-height: none;
}

.article-item {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 16px;
  padding: 14px;
  margin-bottom: 10px;
  cursor: pointer;
  transition: 0.2s ease;
  background: rgba(255, 255, 255, 0.78);
}

.article-item:hover,
.article-item.active {
  transform: translateY(-1px);
  border-color: rgba(37, 99, 235, 0.35);
  box-shadow: 0 12px 28px rgba(37, 99, 235, 0.08);
}

.article-item-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.4;
}

.article-item-meta {
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
  word-break: break-all;
}

.article-item-stats {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  margin-top: 10px;
}

.source-panel {
  position: sticky;
  top: 18px;
  border-radius: 22px;
  padding: 0;
  max-height: calc(100vh - 36px);
  display: flex;
  flex-direction: column;
  background: rgba(248, 250, 252, 0.9);
  border: 1px solid rgba(37, 99, 235, 0.22);
}

.source-panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.18);
  flex-shrink: 0;
}

.source-title {
  font-size: 14px;
  font-weight: 800;
  color: #0f172a;
}

.source-content {
  flex: 1;
  min-height: 0;
  padding: 14px 18px;
}

.source-text {
  font-size: 12px;
  color: #475569;
  line-height: 1.8;
  white-space: pre-wrap;
  word-break: break-word;
  margin-bottom: 16px;
}

.image-markers {
  border-top: 1px solid rgba(148, 163, 184, 0.18);
  padding-top: 12px;
}

.markers-title {
  font-size: 12px;
  font-weight: 800;
  color: #0f172a;
  margin-bottom: 10px;
}

.marker-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  margin-bottom: 8px;
  font-size: 11px;
}

.marker-badge {
  min-width: 20px;
  height: 20px;
  background: #2563eb;
  color: white;
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-weight: 800;
  flex-shrink: 0;
}

.marker-text {
  color: #64748b;
  line-height: 1.4;
  flex: 1;
}

.workspace {
  display: grid;
  grid-template-columns: minmax(280px, 340px) minmax(0, 1fr);
  gap: 16px;
  align-items: start;
  min-width: 0;
}

.workspace-main {
  display: flex;
  flex-direction: column;
  gap: 16px;
  min-width: 0;
}

.hero,
.control-panel,
.filter-bar,
.quick-filter-bar,
.image-card {
  border-radius: 22px;
  padding: 18px;
}

.hero {
  display: flex;
  justify-content: space-between;
  gap: 18px;
  align-items: center;
}

.dot {
  color: #cbd5e1;
  margin: 0 8px;
}

.hero-metrics {
  display: grid;
  grid-template-columns: repeat(3, 92px);
  gap: 12px;
}

.metric-card {
  padding: 14px 12px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.03);
  border: 1px solid rgba(148, 163, 184, 0.18);
  text-align: center;
}

.metric-label {
  font-size: 12px;
  color: #64748b;
}

.metric-value {
  margin-top: 8px;
  font-size: 22px;
  font-weight: 800;
  color: #0f172a;
}

.metric-value.positive {
  color: #16a34a;
}

.metric-value.negative {
  color: #dc2626;
}

.panel-header,
.filter-bar,
.quick-filter-bar {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.panel-title {
  font-size: 18px;
  font-weight: 800;
  color: #0f172a;
}

.panel-actions,
.quick-filter-actions,
.filter-right,
.quick-hints {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.quick-hints {
  margin-top: 12px;
}

.quick-hints :deep(.el-tag) {
  cursor: pointer;
}

.quick-filter-title,
.command-timeline-title {
  font-size: 14px;
  font-weight: 800;
  color: #0f172a;
}

.command-timeline {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid rgba(148, 163, 184, 0.18);
}

.command-item {
  border: 1px solid rgba(148, 163, 184, 0.18);
  border-radius: 16px;
  padding: 12px 14px;
  margin-top: 10px;
  background: rgba(248, 250, 252, 0.72);
}

.command-item-head {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  align-items: center;
}

.command-item-type {
  font-size: 12px;
  font-weight: 800;
  color: #2563eb;
}

.command-item-time {
  font-size: 12px;
  color: #94a3b8;
}

.command-item-text {
  margin-top: 8px;
  color: #0f172a;
  line-height: 1.6;
}

.command-item-note {
  margin-top: 6px;
  font-size: 12px;
  color: #64748b;
}

.gallery-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(310px, 1fr));
  gap: 16px;
  padding-bottom: 24px;
}

.dropped-panel {
  margin: 8px 0 16px;
  border-radius: 14px;
  padding: 16px;
  border: 1px solid rgba(245, 108, 108, 0.2);
  background: rgba(255, 240, 240, 0.4);
}
.dropped-panel-head {
  display: flex;
  align-items: center;
  cursor: pointer;
  font-size: 14px;
  font-weight: 600;
  color: #c0392b;
  user-select: none;
}
.dropped-toggle-hint {
  margin-left: auto;
  font-size: 12px;
  color: #909399;
}
.dropped-grid {
  margin-top: 12px;
  padding-bottom: 0;
}

.image-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.image-card.recommended {
  border-color: rgba(22, 163, 74, 0.22);
}

.image-card.dropped {
  border-color: rgba(220, 38, 38, 0.26);
  opacity: 0.92;
}

.image-card.reviewed {
  box-shadow: 0 14px 34px rgba(15, 23, 42, 0.08);
}

.image-topline {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: center;
}

.thumb {
  width: 100%;
  height: 240px;
  border-radius: 16px;
  overflow: hidden;
  background: #f8fafc;
  border: 1px solid rgba(148, 163, 184, 0.18);
}

.image-meta {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.image-id {
  font-size: 14px;
  font-weight: 800;
  color: #0f172a;
  word-break: break-all;
}

.image-submeta {
  font-size: 12px;
  color: #64748b;
}

.reason-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
}

.form-block {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.summary-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.image-card :deep(.el-textarea__inner) {
  line-height: 1.55;
  word-break: break-word;
  white-space: pre-wrap;
}

.summary-line {
  font-size: 13px;
  color: #0f172a;
  line-height: 1.6;
}

.summary-line.muted {
  color: #94a3b8;
}

.summary-label {
  font-weight: 700;
  color: #2563eb;
}

.empty-state {
  margin-top: 40px;
}

@media (max-width: 1420px) {
  .page-shell {
    grid-template-columns: 280px 1fr;
  }

  .source-panel {
    display: none;
  }

  .page-shell.review-only {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 1180px) {
  .page-shell {
    grid-template-columns: 1fr;
  }

  .page-shell.agent-only {
    grid-template-columns: 1fr;
  }

  .workspace-overview-head,
  .evaluation-trend-head,
  .evaluation-trend-chart-head,
  .crawl-panel-header.compact {
    flex-direction: column;
  }

  .workspace-overview-account-row,
  .brain-stats-grid,
  .evaluation-trend-grid {
    grid-template-columns: 1fr;
  }

  .workspace {
    grid-template-columns: 1fr;
  }

  .history-panel {
    position: relative;
    top: 0;
    max-height: none;
  }

  .history-scrollbar {
    height: auto;
    max-height: 42vh;
  }

  .hero {
    flex-direction: column;
    align-items: flex-start;
  }

  .hero-metrics {
    grid-template-columns: repeat(3, minmax(92px, 1fr));
    width: 100%;
  }
}

@media (max-width: 760px) {
  .wechat-annotator-page {
    padding: 12px;
  }

  .panel-header,
  .filter-bar,
  .quick-filter-bar {
    flex-direction: column;
    align-items: stretch;
  }

  .hero-metrics {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
}
</style>
