<template>
  <div class="page motion-ready">
    <div class="page-inner">
      <div class="page-head">
        <div>
          <div class="page-kicker">Operations cockpit</div>
          <div class="page-title-row">
            <div class="page-title">
              <el-icon size="20"><DataAnalysis /></el-icon>
              系统驾驶舱
            </div>
            <el-tag type="success" size="small" effect="light">实时联动</el-tag>
          </div>
          <div class="page-desc">把问答轮次、知识库存量和反馈处理状态汇到同一块面板中，方便做演示、复盘和优化判断。</div>
        </div>
        <div class="page-head-badges">
          <div class="page-badge-card">
            <span>活跃会话</span>
            <strong>{{ stats.session_count }}</strong>
          </div>
          <div class="page-badge-card">
            <span>反馈总量</span>
            <strong>{{ stats.feedback_total }}</strong>
          </div>
        </div>
      </div>

      <el-skeleton v-if="loading" animated>
        <template #template>
          <div class="dashboard-skeleton-stack">
            <el-skeleton-item variant="image" class="skeleton-hero" />
            <div class="skeleton-stat-grid">
              <el-skeleton-item v-for="item in 4" :key="item" variant="rect" class="skeleton-stat-card" />
            </div>
            <el-skeleton-item variant="rect" class="skeleton-section" />
            <el-skeleton-item variant="rect" class="skeleton-section" />
          </div>
        </template>
      </el-skeleton>

      <div v-else-if="loadError" class="status-card error-card">
        <div class="status-icon">
          <el-icon size="26"><Warning /></el-icon>
        </div>
        <div class="status-copy">
          <div class="status-title">驾驶舱数据暂时不可用</div>
          <div class="status-desc">{{ loadError }}</div>
        </div>
        <el-button type="primary" plain @click="loadStats">重新加载</el-button>
      </div>

      <template v-else>
          <div class="hero-banner">
            <div>
              <div class="hero-kicker">运营态势总览</div>
              <div class="hero-title">从会话、知识库与反馈中汇总真实指标</div>
              <div class="hero-desc">用户提问、提交点赞或纠错后，这里的统计会随后端数据刷新，而不是停留在演示值。</div>
            </div>
            <div class="hero-pills">
              <div class="hero-pill">
                <span class="pill-label">知识向量</span>
                <strong>{{ stats.knowledge_vectors }}</strong>
                <small>面向当前知识库快照</small>
              </div>
              <div class="hero-pill">
                <span class="pill-label">会话轮次</span>
                <strong>{{ stats.question_turns }}</strong>
                <small>累计问答交互</small>
              </div>
              <div class="hero-pill">
                <span class="pill-label">反馈覆盖</span>
                <strong>{{ stats.feedback_total }}</strong>
                <small>来自真实用户动作</small>
              </div>
            </div>
          </div>

          <!-- 今日统计卡片 -->
          <div class="stat-cards">
            <div class="stat-card">
              <div class="stat-icon blue"><el-icon size="28"><ChatDotRound /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">{{ stats.session_count }}</div>
                <div class="stat-lbl">当前会话数</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon green"><el-icon size="28"><Document /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">{{ stats.knowledge_vectors.toLocaleString() }}</div>
                <div class="stat-lbl">知识向量总量</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon orange"><el-icon size="28"><Star /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">{{ stats.satisfaction_rate }}%</div>
                <div class="stat-lbl">反馈满意率</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon purple"><el-icon size="28"><User /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">{{ stats.unique_users }}</div>
                <div class="stat-lbl">反馈用户数</div>
              </div>
            </div>
          </div>

          <!-- 反馈概览 -->
          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="card-head">
                <el-icon><Timer /></el-icon>
                <span>反馈画像</span>
              </div>
            </template>
            <div class="compare-grid">
              <div class="compare-item">
                <div class="compare-label">点赞</div>
                <div class="compare-value good">{{ stats.feedback_like }}</div>
                <div class="compare-count">占比 {{ stats.feedback_total ? Math.round(stats.feedback_like / stats.feedback_total * 100) : 0 }}%</div>
              </div>
              <div class="compare-divider"></div>
              <div class="compare-item">
                <div class="compare-label">点踩</div>
                <div class="compare-value bad">{{ stats.feedback_dislike }}</div>
                <div class="compare-count">占比 {{ stats.feedback_total ? Math.round(stats.feedback_dislike / stats.feedback_total * 100) : 0 }}%</div>
              </div>
              <div class="compare-divider"></div>
              <div class="compare-item">
                <div class="compare-label">部分正确 / 纠错</div>
                <div class="compare-value pro">{{ stats.feedback_partial + stats.feedback_correction }}</div>
                <div class="compare-count">需要优化的回答</div>
              </div>
            </div>
          </el-card>

          <!-- 用户反馈统计 -->
          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="card-head">
                <el-icon><ChatLineRound /></el-icon>
                <span>用户反馈统计</span>
                <span class="card-sub">每条反馈可追溯到用户、问题、回答与反馈说明</span>
              </div>
            </template>
            <div class="feedback-grid">
              <div class="feedback-item">
                <el-icon size="32" color="#67c23a"><CircleCheck /></el-icon>
                <div class="feedback-num">{{ stats.feedback_like }}</div>
                <div class="feedback-label">点赞</div>
              </div>
              <div class="feedback-item">
                <el-icon size="32" color="#f56c6c"><CircleClose /></el-icon>
                <div class="feedback-num">{{ stats.feedback_dislike }}</div>
                <div class="feedback-label">点踩</div>
              </div>
              <div class="feedback-item">
                <el-icon size="32" color="#e6a23c"><Warning /></el-icon>
                <div class="feedback-num">{{ stats.feedback_partial }}</div>
                <div class="feedback-label">部分正确</div>
              </div>
              <div class="feedback-item">
                <el-icon size="32" color="#409eff"><Edit /></el-icon>
                <div class="feedback-num">{{ stats.feedback_correction }}</div>
                <div class="feedback-label">纠错</div>
              </div>
              <div class="feedback-item">
                <el-icon size="32" color="#94a3b8"><ChatLineRound /></el-icon>
                <div class="feedback-num">{{ stats.feedback_unfeedback }}</div>
                <div class="feedback-label">未反馈</div>
              </div>
            </div>
            <div class="feedback-toolbar">
              <div class="feedback-toolbar-copy">
                <div class="feedback-toolbar-title">按处理状态定位反馈</div>
                <div class="feedback-toolbar-desc">切到对应状态后，只展示这一类反馈，方便集中处理未处理、已查看、已修复或已忽略的问题。</div>
              </div>
              <div class="feedback-toolbar-controls">
                <el-input
                  v-model="feedbackUserKeyword"
                  clearable
                  size="small"
                  class="feedback-user-search"
                  placeholder="按用户名搜索定位"
                />
                <div class="feedback-status-filters">
                  <el-button
                    size="small"
                    :type="selectedFeedbackStatus === 'all' ? 'primary' : 'default'"
                    @click="selectedFeedbackStatus = 'all'"
                  >全部 {{ feedbackStatusCounts.all }}</el-button>
                  <el-button
                    v-for="option in feedbackStatusOptions"
                    :key="option.value"
                    size="small"
                    :type="selectedFeedbackStatus === option.value ? 'primary' : 'default'"
                    @click="selectedFeedbackStatus = option.value"
                  >{{ option.label }} {{ feedbackStatusCounts[option.value] || 0 }}</el-button>
                </div>
              </div>
            </div>
            <div v-if="groupedFeedbackUsers.length" class="feedback-user-board">
              <div class="feedback-user-board-head">
                <div>
                  <div class="feedback-user-board-title">用户反馈分组</div>
                  <div class="feedback-user-board-desc">不同用户统一收进同一块面板中，默认收起具体评价内容，需要时再展开。</div>
                </div>
                <div class="feedback-user-board-meta">共 {{ groupedFeedbackUsers.length }} 位用户</div>
              </div>
              <div class="feedback-user-carousel">
                <article v-for="userGroup in groupedFeedbackUsers" :key="userGroup.userId" class="feedback-user-panel">
                  <div class="feedback-user-head">
                    <div>
                      <div class="feedback-user-name">{{ userGroup.userId }}</div>
                      <div class="feedback-user-count">{{ userGroup.total }} 条反馈</div>
                    </div>
                    <div class="feedback-user-actions">
                      <el-button text size="small" @click.stop="expandUserTypes(userGroup)">展开类型</el-button>
                      <el-button text size="small" @click.stop="collapseUserTypes(userGroup)">收起类型</el-button>
                    </div>
                  </div>
                  <el-collapse
                    class="feedback-type-collapse"
                    :model-value="activeFeedbackTypes[userGroup.userId] || []"
                    @update:model-value="(value) => setActiveFeedbackTypes(userGroup.userId, value)"
                  >
                    <el-collapse-item v-for="typeGroup in userGroup.types" :key="`${userGroup.userId}-${typeGroup.type}`" :name="typeGroup.type">
                      <template #title>
                        <div class="feedback-type-head">
                          <span>{{ feedbackLabel(typeGroup.type) }}</span>
                          <span>{{ typeGroup.items.length }} 条</span>
                        </div>
                      </template>
                      <div class="feedback-detail-list">
                        <div v-for="item in typeGroup.items" :key="feedbackItemKey(item)" class="feedback-detail-item">
                        <div class="feedback-detail-head">
                          <div class="feedback-detail-tags">
                            <el-tag size="small" effect="light">{{ feedbackLabel(item.feedback_type) }}</el-tag>
                            <el-tag v-if="item.query_type" size="small" effect="plain" :type="item.query_type === '专业咨询' ? 'primary' : 'success'">{{ item.query_type }}</el-tag>
                            <el-tag v-if="item.strategy" size="small" effect="plain" type="warning">{{ item.strategy }}</el-tag>
                            <el-tag size="small" effect="light" :type="feedbackStatusTagType(item.status || 'pending')">{{ feedbackStatusLabel(item.status || 'pending') }}</el-tag>
                          </div>
                          <div class="feedback-detail-head-side">
                            <div class="feedback-detail-time">{{ formatTime(item.timestamp) }}</div>
                            <el-button text size="small" type="primary" @click="toggleFeedbackItem(item)">
                              {{ isFeedbackItemExpanded(item) ? '收起提问与回答' : '展开提问与回答' }}
                            </el-button>
                          </div>
                        </div>
                        <div v-if="isFeedbackItemExpanded(item)" class="feedback-detail-grid">
                          <div class="feedback-detail-block">
                            <div class="feedback-detail-label">用户问题</div>
                            <div class="feedback-detail-text" :class="{ expanded: isFeedbackTextExpanded(item, 'question') }">{{ item.question || '未找到原始问题' }}</div>
                            <el-button
                              v-if="shouldShowTextToggle(item.question)"
                              text
                              size="small"
                              type="primary"
                              class="feedback-expand-btn"
                              @click="toggleFeedbackText(item, 'question')"
                            >{{ isFeedbackTextExpanded(item, 'question') ? '收起问题' : '展开问题' }}</el-button>
                          </div>
                          <div class="feedback-detail-block">
                            <div class="feedback-detail-label">系统回答</div>
                            <div class="feedback-detail-text" :class="{ expanded: isFeedbackTextExpanded(item, 'answer') }">{{ item.answer || '未找到原始回答' }}</div>
                            <el-button
                              v-if="shouldShowTextToggle(item.answer)"
                              text
                              size="small"
                              type="primary"
                              class="feedback-expand-btn"
                              @click="toggleFeedbackText(item, 'answer')"
                            >{{ isFeedbackTextExpanded(item, 'answer') ? '收起回答' : '展开回答' }}</el-button>
                          </div>
                        </div>
                        <div v-if="isFeedbackItemExpanded(item)" class="feedback-detail-footer">
                          <div class="feedback-detail-block compact">
                            <div class="feedback-detail-label">反馈说明</div>
                            <div class="feedback-detail-text" :class="{ expanded: isFeedbackTextExpanded(item, 'content') }">{{ item.content || feedbackDefaultText(item.feedback_type) }}</div>
                            <el-button
                              v-if="shouldShowTextToggle(item.content || feedbackDefaultText(item.feedback_type))"
                              text
                              size="small"
                              type="primary"
                              class="feedback-expand-btn"
                              @click="toggleFeedbackText(item, 'content')"
                            >{{ isFeedbackTextExpanded(item, 'content') ? '收起说明' : '展开说明' }}</el-button>
                          </div>
                          <div class="feedback-detail-side">
                            <el-button
                              v-if="hasPanelInfo(item)"
                              text
                              size="small"
                              type="primary"
                              @click="toggleFeedbackContext(item)"
                            >{{ isFeedbackContextExpanded(item) ? '收起检索上下文' : '查看检索上下文' }}</el-button>
                            <div v-if="isSupervisor" class="feedback-status-editor">
                              <el-select
                                :model-value="item.status || 'pending'"
                                size="small"
                                placeholder="处理状态"
                                :disabled="updatingFeedbackKey === `${item.session_id}-${item.message_index}-${item.user_id}-${item.timestamp}`"
                                @change="(value) => updateFeedbackStatus(item, value)"
                              >
                                <el-option v-for="option in feedbackStatusOptions" :key="option.value" :label="option.label" :value="option.value" />
                              </el-select>
                            </div>
                            <div class="feedback-status-meta" v-if="item.status_updated_at || item.status_updated_by">
                              {{ item.status_updated_by || '系统' }} · {{ formatTime(item.status_updated_at) }}
                            </div>
                            <div class="feedback-session">{{ item.session_id }}</div>
                          </div>
                        </div>
                        <div v-if="isFeedbackItemExpanded(item) && isFeedbackContextExpanded(item) && hasPanelInfo(item)" class="feedback-context-panel">
                          <div class="feedback-context-meta">
                            <span>判定：{{ item.panel_info?.query_type || item.query_type || '未知' }}</span>
                            <span>策略：{{ item.panel_info?.strategy || item.strategy || '未记录' }}</span>
                            <span>候选：{{ item.panel_info?.candidate_count ?? '—' }}</span>
                            <span>最终命中：{{ item.panel_info?.final_count ?? '—' }}</span>
                          </div>
                          <div v-if="item.panel_info?.sources?.length" class="feedback-context-sources">
                            <div v-for="(source, sourceIndex) in item.panel_info.sources" :key="`${item.session_id}-${item.timestamp}-${sourceIndex}`" class="feedback-source-card">
                              <div class="feedback-source-head">
                                <div>
                                  <div class="feedback-source-title">{{ source.file_name || source.source || '未命名来源' }}</div>
                                  <div class="feedback-source-meta">{{ source.source || '未知来源' }}</div>
                                </div>
                                <div class="feedback-source-actions">
                                  <el-tag size="small" effect="plain">score {{ formatSourceScore(source.score) }}</el-tag>
                                  <el-button
                                    v-if="canDownloadSourceDocument(source)"
                                    text
                                    size="small"
                                    type="primary"
                                    @click="downloadSourceDocument(source)"
                                  >下载来源文档</el-button>
                                </div>
                              </div>
                              <div class="feedback-source-block">
                                <div class="feedback-detail-label">命中子块</div>
                                <div v-if="source.matched_children?.length" class="feedback-child-list">
                                  <div v-for="(child, childIndex) in source.matched_children" :key="`${sourceIndex}-${childIndex}`" class="feedback-child-item">
                                    <div class="feedback-child-score">子块 {{ childIndex + 1 }} · score {{ formatSourceScore(child.score) }}</div>
                                    <div class="feedback-context-text">{{ child.content || '未记录子块内容' }}</div>
                                  </div>
                                </div>
                                <div v-else class="feedback-context-text">{{ source.content || '未记录子块内容' }}</div>
                              </div>
                              <div class="feedback-source-block">
                                <div class="feedback-detail-label">父块内容</div>
                                <div class="feedback-context-text parent">{{ source.parent_content || '未记录父块内容' }}</div>
                              </div>
                            </div>
                          </div>
                          <div v-else class="empty-state">当前反馈未记录可展示的检索来源。</div>
                        </div>
                      </div>
                      </div>
                    </el-collapse-item>
                  </el-collapse>
                </article>
              </div>
            </div>
            <div v-else class="empty-state">暂无可追溯反馈明细</div>
          </el-card>

          <!-- 查询与最近反馈 -->
          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="card-head">
                <el-icon><PieChart /></el-icon>
                <span>查询轮次与近期反馈</span>
              </div>
            </template>
            <div class="recent-feedback-panel">
              <div class="type-rows compact">
                <div class="type-row compact">
                  <div class="type-label">问答轮次</div>
                  <el-progress :percentage="100" :stroke-width="12" color="#409eff" />
                  <div class="type-count">{{ stats.question_turns }} 轮</div>
                </div>
                <div class="type-row compact">
                  <div class="type-label">反馈覆盖</div>
                  <el-progress
                    :percentage="stats.question_turns ? Math.min(100, Math.round(stats.feedback_total / stats.question_turns * 100)) : 0"
                    :stroke-width="12"
                    color="#67c23a"
                  />
                  <div class="type-count">{{ stats.feedback_total }} 条</div>
                </div>
              </div>
              <div class="recent-list-shell">
                <div class="recent-list-head">
                  <span>最近反馈</span>
                  <span>{{ stats.recent_feedbacks.length }} 条</span>
                </div>
                <div class="recent-list compact">
                  <div v-for="item in stats.recent_feedbacks" :key="item.session_id + item.timestamp" class="recent-item compact">
                    <div class="recent-main">
                      <strong>{{ feedbackLabel(item.feedback_type) }}</strong>
                      <span>{{ item.user_id || item.session_id }}</span>
                    </div>
                    <div class="recent-meta">{{ formatTime(item.timestamp) }}</div>
                  </div>
                  <div v-if="!stats.recent_feedbacks.length" class="empty-state">暂无近期反馈</div>
                </div>
              </div>
            </div>
          </el-card>

      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import {
  DataAnalysis,
  ChatDotRound,
  Document,
  Star,
  User,
  Timer,
  ChatLineRound,
  CircleCheck,
  CircleClose,
  Warning,
  Edit,
  PieChart,
} from '@element-plus/icons-vue'
import { feedbackAPI, sessionAPI, knowledgeAPI, datasetAPI } from '@/api'
import { useStore } from '@/store'

const loading = ref(true)
const loadError = ref('')
const updatingFeedbackKey = ref('')
const feedbackStatusOptions = [
  { value: 'pending', label: '未处理' },
  { value: 'reviewed', label: '已查看' },
  { value: 'resolved', label: '已修复' },
  { value: 'ignored', label: '已忽略' },
]
const feedbackTypeOrder = ['unfeedback', 'like', 'dislike', 'partial_correct', 'correction']
const { state, isSupervisor } = useStore()
const stats = ref({
  session_count: 0,
  question_turns: 0,
  knowledge_vectors: 0,
  satisfaction_rate: 0,
  unique_users: 0,
  feedback_like: 0,
  feedback_dislike: 0,
  feedback_partial: 0,
  feedback_correction: 0,
  feedback_unfeedback: 0,
  feedback_total: 0,
  recent_feedbacks: [],
  feedback_details: [],
})
const selectedFeedbackStatus = ref('all')
const activeFeedbackTypes = ref({})
const expandedFeedbackItems = ref({})
const expandedFeedbackTexts = ref({})
const expandedFeedbackContexts = ref({})
const feedbackUserKeyword = ref('')

const filteredFeedbackDetails = computed(() => {
  const items = Array.isArray(stats.value.feedback_details) ? stats.value.feedback_details : []
  if (selectedFeedbackStatus.value === 'all') return items
  return items.filter((item) => String(item.status || 'pending') === selectedFeedbackStatus.value)
})

const feedbackStatusCounts = computed(() => {
  const items = Array.isArray(stats.value.feedback_details) ? stats.value.feedback_details : []
  const counts = { all: items.length, pending: 0, reviewed: 0, resolved: 0, ignored: 0 }
  for (const item of items) {
    const status = String(item.status || 'pending')
    if (Object.prototype.hasOwnProperty.call(counts, status)) {
      counts[status] += 1
    }
  }
  return counts
})

const groupedFeedbackUsers = computed(() => {
  const groups = new Map()
  const keyword = feedbackUserKeyword.value.trim().toLowerCase()
  for (const item of filteredFeedbackDetails.value || []) {
    const userId = item.user_id || '未知用户'
    if (keyword && !String(userId).toLowerCase().includes(keyword)) continue
    if (!groups.has(userId)) {
      groups.set(userId, {
        userId,
        total: 0,
        types: [],
      })
    }

    const group = groups.get(userId)
    group.total += 1

    let typeGroup = group.types.find((entry) => entry.type === item.feedback_type)
    if (!typeGroup) {
      typeGroup = { type: item.feedback_type, items: [] }
      group.types.push(typeGroup)
    }
    typeGroup.items.push(item)
  }

  return Array.from(groups.values())
    .map((group) => ({
      ...group,
      types: feedbackTypeOrder
        .map((type) => group.types.find((entry) => entry.type === type))
        .filter(Boolean)
        .map((entry) => ({
          ...entry,
          items: [...entry.items].sort((left, right) => String(right.timestamp || '').localeCompare(String(left.timestamp || ''))),
        })),
    }))
    .sort((left, right) => right.total - left.total || String(left.userId).localeCompare(String(right.userId)))
})

function feedbackLabel(type) {
  if (type === 'unfeedback') return '未反馈'
  if (type === 'like') return '点赞'
  if (type === 'dislike') return '点踩'
  if (type === 'partial_correct') return '部分正确'
  if (type === 'correction') return '纠错'
  return type || '未知'
}

function feedbackDefaultText(type) {
  if (type === 'unfeedback') return '当前回答还没有收到用户反馈。'
  if (type === 'like') return '用户认为回答基本正确。'
  if (type === 'dislike') return '用户认为回答存在明显问题。'
  if (type === 'partial_correct') return '用户标记为部分正确，但当时未填写详细说明。'
  if (type === 'correction') return '用户提交了纠错，但未返回具体内容。'
  return '未提供补充说明。'
}

function feedbackStatusLabel(status) {
  return feedbackStatusOptions.find((item) => item.value === status)?.label || '未处理'
}

function feedbackStatusTagType(status) {
  if (status === 'resolved') return 'success'
  if (status === 'reviewed') return 'primary'
  if (status === 'ignored') return 'info'
  return 'warning'
}

function feedbackItemKey(item) {
  return `${item.session_id}-${item.message_index}-${item.user_id}-${item.timestamp}`
}

function feedbackTextKey(item, field) {
  return `${feedbackItemKey(item)}-${field}`
}

function isFeedbackItemExpanded(item) {
  return !!expandedFeedbackItems.value[feedbackItemKey(item)]
}

function toggleFeedbackItem(item) {
  const key = feedbackItemKey(item)
  expandedFeedbackItems.value = {
    ...expandedFeedbackItems.value,
    [key]: !expandedFeedbackItems.value[key],
  }
}

function shouldShowTextToggle(text) {
  return String(text || '').trim().length > 180
}

function isFeedbackTextExpanded(item, field) {
  return !!expandedFeedbackTexts.value[feedbackTextKey(item, field)]
}

function toggleFeedbackText(item, field) {
  const key = feedbackTextKey(item, field)
  expandedFeedbackTexts.value = {
    ...expandedFeedbackTexts.value,
    [key]: !expandedFeedbackTexts.value[key],
  }
}

function hasPanelInfo(item) {
  if (!item?.panel_info || typeof item.panel_info !== 'object') return false
  const info = item.panel_info
  return !!(
    (Array.isArray(info.sources) && info.sources.length)
    || info.query_type
    || info.strategy
    || info.candidate_count != null
    || info.final_count != null
  )
}

function isFeedbackContextExpanded(item) {
  return !!expandedFeedbackContexts.value[feedbackItemKey(item)]
}

function toggleFeedbackContext(item) {
  const key = feedbackItemKey(item)
  expandedFeedbackContexts.value = {
    ...expandedFeedbackContexts.value,
    [key]: !expandedFeedbackContexts.value[key],
  }
}

function formatSourceScore(score) {
  const value = Number(score)
  if (!Number.isFinite(value)) return '0.000'
  return value.toFixed(3)
}

function canDownloadSourceDocument(source) {
  return !!String(source?.file_name || '').trim()
}

function downloadSourceDocument(source) {
  const fileName = String(source?.file_name || '').trim()
  if (!fileName) return
  const sourceName = String(source?.source || '').trim()
  const url = datasetAPI.downloadLegacyFileUrl(fileName, sourceName)
  window.open(url, '_blank', 'noopener,noreferrer')
}

async function updateFeedbackStatus(item, status) {
  const key = `${item.session_id}-${item.message_index}-${item.user_id}-${item.timestamp}`
  const previousStatus = item.status || 'pending'
  item.status = status
  updatingFeedbackKey.value = key
  try {
    await feedbackAPI.updateStatus({
      session_id: item.session_id,
      message_index: item.message_index,
      user_id: item.user_id,
      timestamp: item.timestamp,
      status,
      handler_id: state.user?.employee_id || '',
    })
    item.status_updated_by = state.user?.employee_id || ''
    item.status_updated_at = new Date().toISOString()
  } catch (err) {
    item.status = previousStatus
    console.error('更新反馈处理状态失败:', err)
  } finally {
    updatingFeedbackKey.value = ''
  }
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

function setActiveFeedbackTypes(userId, value) {
  activeFeedbackTypes.value = {
    ...activeFeedbackTypes.value,
    [userId]: Array.isArray(value) ? value : [],
  }
}

function expandUserTypes(userGroup) {
  setActiveFeedbackTypes(userGroup.userId, userGroup.types.map((item) => item.type))
}

function collapseUserTypes(userGroup) {
  setActiveFeedbackTypes(userGroup.userId, [])
}

function resetFeedbackExpansion() {
  activeFeedbackTypes.value = Object.fromEntries(
    groupedFeedbackUsers.value.map((group) => [group.userId, []])
  )
  expandedFeedbackItems.value = {}
  expandedFeedbackTexts.value = {}
  expandedFeedbackContexts.value = {}
}

watch(selectedFeedbackStatus, () => {
  resetFeedbackExpansion()
})

watch(feedbackUserKeyword, () => {
  resetFeedbackExpansion()
})

async function loadStats() {
  loading.value = true
  loadError.value = ''
  try {
    const [feedbackRes, sessionRes, knowledgeRes] = await Promise.all([
      feedbackAPI.getStats(),
      sessionAPI.list(),
      knowledgeAPI.status(),
    ])

    const sessions = sessionRes.data.sessions || []
    const questionTurns = sessions.reduce((sum, item) => sum + (item.message_count || 0), 0)
    const knowledge = knowledgeRes.data.knowledge || {}
    const feedback = feedbackRes.data.stats || {}

    stats.value = {
      session_count: sessions.length,
      question_turns: questionTurns,
      knowledge_vectors: Number(knowledgeRes.data.system?.total_vectors || knowledge.total_chunks || 0),
      satisfaction_rate: Math.round((feedback.satisfaction_rate || 0) * 100),
      unique_users: feedback.unique_users || 0,
      feedback_like: feedback.likes || feedback.like || 0,
      feedback_dislike: feedback.dislikes || feedback.dislike || 0,
      feedback_partial: feedback.partial_correct || 0,
      feedback_correction: feedback.corrections || feedback.correction || 0,
      feedback_unfeedback: feedback.no_feedback || 0,
      feedback_total: feedback.total_feedback || 0,
      recent_feedbacks: feedback.recent_feedbacks || [],
      feedback_details: feedback.detailed_feedbacks || [],
    }
    resetFeedbackExpansion()
  } catch (err) {
    loadError.value = err.response?.data?.detail || '暂时无法获取会话、知识库或反馈统计，请检查后端服务后重试。'
    console.error('获取驾驶仓数据失败:', err)
  } finally {
    loading.value = false
  }
}

function handleLiveRefresh() {
  loadStats()
}

onMounted(() => {
  loadStats()
  window.addEventListener('rag-activity-updated', handleLiveRefresh)
  window.addEventListener('rag-feedback-updated', handleLiveRefresh)
  window.addEventListener('rag-knowledge-updated', handleLiveRefresh)
})

onBeforeUnmount(() => {
  window.removeEventListener('rag-activity-updated', handleLiveRefresh)
  window.removeEventListener('rag-feedback-updated', handleLiveRefresh)
  window.removeEventListener('rag-knowledge-updated', handleLiveRefresh)
})
</script>

<style scoped>
.page {
  height: calc(100vh - 72px); overflow-y: auto;
  background:
    radial-gradient(circle at 8% 14%, rgba(59, 130, 246, .11), transparent 24%),
    radial-gradient(circle at 88% 86%, rgba(16, 185, 129, .11), transparent 26%),
    radial-gradient(circle at 74% 18%, rgba(249, 115, 22, .08), transparent 22%),
    linear-gradient(145deg, #f8fafc 0%, #eef2ff 52%, #ecfeff 100%);
}

.motion-ready .page-head,
.motion-ready .hero-banner,
.motion-ready .stat-card,
.motion-ready .section-card {
  opacity: 0;
  transform: translateY(18px);
  animation: dashboardReveal .76s cubic-bezier(.22,1,.36,1) forwards;
}

.motion-ready .page-head { animation-delay: .04s; }
.motion-ready .hero-banner { animation-delay: .12s; }
.motion-ready .stat-card:nth-child(1) { animation-delay: .18s; }
.motion-ready .stat-card:nth-child(2) { animation-delay: .24s; }
.motion-ready .stat-card:nth-child(3) { animation-delay: .3s; }
.motion-ready .stat-card:nth-child(4) { animation-delay: .36s; }
.motion-ready .section-card:nth-of-type(1) { animation-delay: .42s; }
.motion-ready .section-card:nth-of-type(2) { animation-delay: .5s; }
.motion-ready .section-card:nth-of-type(3) { animation-delay: .58s; }
.page-inner { max-width: 1280px; margin: 0 auto; padding: 28px 24px 36px; }
.page-head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 18px;
  align-items: end;
  margin-bottom: 24px;
}
.page-kicker {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .16em;
  text-transform: uppercase;
  color: #0f5bd8;
}
.page-title-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 6px;
}
.page-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 28px; font-weight: 900; color: #0f172a;
  letter-spacing: -0.03em;
}
.page-desc {
  margin-top: 10px;
  max-width: 62ch;
  font-size: 13px;
  line-height: 1.8;
  color: #64748b;
}
.page-head-badges {
  display: grid;
  grid-template-columns: repeat(2, minmax(120px, 1fr));
  gap: 12px;
}
.page-badge-card {
  min-width: 120px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255,255,255,.72);
  border: 1px solid rgba(148,163,184,.18);
  backdrop-filter: blur(12px);
  box-shadow: 0 12px 26px rgba(15,23,42,.06);
  animation: badgeFloat 6.4s ease-in-out infinite;
}
.page-badge-card:nth-child(2) { animation-delay: .8s; }
.page-badge-card span {
  display: block;
  font-size: 12px;
  color: #64748b;
}
.page-badge-card strong {
  display: block;
  margin-top: 8px;
  font-size: 22px;
  font-weight: 900;
  color: #0f172a;
}

.dashboard-skeleton-stack {
  display: grid;
  gap: 18px;
}

.skeleton-hero,
.skeleton-section,
.skeleton-stat-card {
  overflow: hidden;
  border-radius: 24px;
}

.skeleton-hero {
  width: 100%;
  height: 182px;
}

.skeleton-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}

.skeleton-stat-card {
  width: 100%;
  height: 102px;
}

.skeleton-section {
  width: 100%;
  height: 220px;
}

.status-card {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 22px 24px;
  border-radius: 24px;
  border: 1px solid rgba(148,163,184,.18);
  background: linear-gradient(180deg, rgba(255,255,255,.94), rgba(248,250,252,.94));
  box-shadow: 0 18px 36px rgba(15,23,42,.06);
}

.error-card {
  margin-bottom: 20px;
}

.status-icon {
  width: 52px;
  height: 52px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #b45309;
  background: rgba(251,191,36,.14);
  flex-shrink: 0;
}

.status-copy {
  flex: 1;
}

.status-title {
  font-size: 18px;
  font-weight: 800;
  color: #0f172a;
}

.status-desc {
  margin-top: 6px;
  font-size: 13px;
  line-height: 1.7;
  color: #64748b;
}

.hero-banner {
  display: grid; grid-template-columns: 1.5fr 1fr; gap: 16px;
  padding: 24px 26px; border-radius: 28px; margin-bottom: 20px;
  background: linear-gradient(135deg, #0f172a, #1d4ed8 60%, #0f766e);
  color: #fff; box-shadow: 0 24px 54px rgba(15, 23, 42, .16);
}
.hero-kicker { font-size: 12px; letter-spacing: .18em; text-transform: uppercase; opacity: .72; }
.hero-title { font-size: 30px; font-weight: 900; margin: 10px 0 8px; line-height: 1.08; letter-spacing: -.03em; max-width: 14ch; }
.hero-desc { font-size: 13px; line-height: 1.8; color: rgba(255,255,255,.78); max-width: 52ch; }
.hero-pills { display: grid; gap: 10px; align-self: center; }
.hero-pill {
  display: flex; flex-direction: column; gap: 10px;
  padding: 14px 16px; border-radius: 18px;
  background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.12);
  backdrop-filter: blur(10px);
  animation: badgeFloat 7s ease-in-out infinite;
}
.hero-pill:nth-child(2) { animation-delay: .8s; }
.hero-pill:nth-child(3) { animation-delay: 1.6s; }
.pill-label { font-size: 12px; color: rgba(255,255,255,.68); }
.hero-pill strong {
  font-size: 24px;
  font-weight: 900;
}
.hero-pill small {
  font-size: 11px;
  color: rgba(255,255,255,.72);
}

.stat-cards {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 16px; margin-bottom: 20px;
}
.stat-card {
  background: linear-gradient(180deg, rgba(255,255,255,.92), rgba(248,250,252,.92)); border-radius: 22px; padding: 22px;
  display: flex; align-items: center; gap: 16px;
  box-shadow: 0 18px 34px rgba(15,23,42,.06);
  border: 1px solid rgba(148,163,184,.16);
  transition: transform .18s ease, box-shadow .18s ease;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 14px 28px rgba(15,23,42,.10); }
.stat-icon {
  width: 52px; height: 52px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
}
.stat-icon.blue { background: #ecf5ff; color: #409eff; }
.stat-icon.green { background: #f0f9eb; color: #67c23a; }
.stat-icon.orange { background: #fdf6ec; color: #e6a23c; }
.stat-icon.purple { background: #f3f0ff; color: #9254de; }
.stat-num { font-size: 24px; font-weight: 700; color: #303133; }
.stat-lbl { font-size: 12px; color: #909399; margin-top: 2px; }

.section-card { margin-bottom: 20px; border-radius: 22px; overflow: hidden; box-shadow: 0 18px 36px rgba(15,23,42,.06); }
.card-head { display: flex; align-items: center; gap: 6px; font-size: 15px; font-weight: 700; color: #0f172a; }
.card-sub { margin-left: auto; font-size: 12px; color: #909399; }
.section-card :deep(.el-card__header) { background: rgba(248,250,252,.95); border-bottom: 1px solid rgba(148,163,184,.12); }
.section-card :deep(.el-card__body) { padding: 22px 24px; }

.compare-grid {
  display: flex; align-items: stretch; gap: 20px;
}
.compare-item { flex: 1; text-align: center; padding: 4px 6px; }
.compare-label { font-size: 13px; color: #909399; margin-bottom: 8px; }
.compare-value {
  font-size: 34px; font-weight: 800; color: #67c23a;
  margin-bottom: 4px;
}
.compare-value.pro { color: #409eff; }
.compare-value.good { color: #67c23a; }
.compare-value.bad { color: #f56c6c; }
.compare-count { font-size: 12px; color: #c0c4cc; }
.compare-divider {
  width: 1px; height: 60px; background: #e4e7ed;
}

.feedback-grid {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 24px;
}
.feedback-item {
  text-align: center; padding: 18px;
  background: linear-gradient(180deg, #fff, #f8fafc); border-radius: 14px; border: 1px solid rgba(148,163,184,.18);
  box-shadow: 0 10px 24px rgba(15,23,42,.04);
  transition: transform .18s ease, box-shadow .18s ease;
}

.feedback-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 28px rgba(15,23,42,.08);
}
.feedback-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-top: 18px;
  padding: 16px 18px;
  border-radius: 16px;
  background: rgba(248,250,252,.88);
  border: 1px solid rgba(148,163,184,.16);
}
.feedback-toolbar-copy { max-width: 56ch; }
.feedback-toolbar-controls {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 10px;
  min-width: min(420px, 100%);
}
.feedback-user-search {
  width: min(320px, 100%);
}
.feedback-toolbar-title {
  font-size: 14px;
  font-weight: 800;
  color: #0f172a;
}
.feedback-toolbar-desc {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.7;
  color: #64748b;
}
.feedback-status-filters {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  justify-content: flex-end;
}
.feedback-num {
  font-size: 28px; font-weight: 700; color: #303133;
  margin: 8px 0 4px;
}
.feedback-label { font-size: 13px; color: #909399; }
.feedback-user-board {
  margin-top: 18px;
  padding: 18px;
  border-radius: 18px;
  background: rgba(248,250,252,.82);
  border: 1px solid rgba(148,163,184,.16);
}
.feedback-user-board-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.feedback-user-board-title {
  font-size: 14px;
  font-weight: 800;
  color: #0f172a;
}
.feedback-user-board-desc,
.feedback-user-board-meta {
  font-size: 12px;
  color: #64748b;
}
.feedback-user-carousel {
  display: grid;
  grid-auto-flow: column;
  grid-auto-columns: minmax(320px, 420px);
  gap: 16px;
  overflow-x: auto;
  padding-bottom: 4px;
  scrollbar-width: thin;
}
.feedback-user-panel {
  padding: 16px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(255,255,255,.96), rgba(248,250,252,.96));
  border: 1px solid rgba(148,163,184,.18);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.75);
}
.feedback-user-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 12px;
  padding-right: 4px;
  margin-bottom: 10px;
}
.feedback-user-actions { display: flex; align-items: center; gap: 4px; }
.feedback-user-name { font-size: 14px; font-weight: 700; color: #0f172a; }
.feedback-user-count { font-size: 12px; color: #64748b; }
.feedback-type-collapse { display: grid; gap: 12px; }
.feedback-type-collapse :deep(.el-collapse) {
  border-top: none;
  border-bottom: none;
}
.feedback-type-collapse :deep(.el-collapse-item) {
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(148,163,184,.16);
  background: rgba(255,255,255,.88);
}
.feedback-type-collapse :deep(.el-collapse-item__header) {
  padding: 0 14px;
  background: rgba(248,250,252,.92);
  border-bottom: none;
}
.feedback-type-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
}
.feedback-type-collapse :deep(.el-collapse-item__content) {
  padding: 0 14px 14px;
}
.feedback-type-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  font-size: 13px;
  font-weight: 700;
  color: #334155;
}
.feedback-detail-list { display: grid; gap: 14px; padding-top: 8px; }
.feedback-detail-item {
  border: 1px solid rgba(148,163,184,.18);
  border-radius: 14px;
  background: linear-gradient(180deg, #fff, #f8fafc);
  padding: 14px 16px;
}
.feedback-detail-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.feedback-detail-head-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}
.feedback-detail-tags { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.feedback-detail-time { font-size: 12px; color: #94a3b8; white-space: nowrap; }
.feedback-detail-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.feedback-detail-block {
  border-radius: 12px;
  background: rgba(248,250,252,.95);
  border: 1px solid rgba(226,232,240,.9);
  padding: 12px 14px;
}
.feedback-detail-block.compact { flex: 1; }
.feedback-detail-label { font-size: 12px; color: #64748b; font-weight: 700; margin-bottom: 6px; }
.feedback-detail-text {
  font-size: 13px;
  color: #0f172a;
  line-height: 1.7;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  white-space: pre-wrap;
  word-break: break-word;
}
.feedback-detail-text.expanded {
  display: block;
  -webkit-line-clamp: unset;
  -webkit-box-orient: unset;
  overflow: visible;
}
.feedback-expand-btn {
  margin-top: 8px;
  padding-left: 0;
  padding-right: 0;
}
.feedback-detail-footer {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-top: 12px;
}
.feedback-detail-side {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}
.feedback-status-editor { min-width: 132px; }
.feedback-status-meta { font-size: 12px; color: #94a3b8; }
.feedback-session { font-size: 12px; color: #94a3b8; white-space: nowrap; }
.feedback-context-panel {
  margin-top: 14px;
  padding: 14px;
  border-radius: 14px;
  background: rgba(241,245,249,.9);
  border: 1px solid rgba(148,163,184,.18);
}
.feedback-context-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #475569;
  margin-bottom: 12px;
}
.feedback-context-sources {
  display: grid;
  gap: 12px;
}
.feedback-source-card {
  border-radius: 12px;
  background: rgba(255,255,255,.92);
  border: 1px solid rgba(203,213,225,.8);
  padding: 12px 14px;
}
.feedback-source-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.feedback-source-title {
  font-size: 13px;
  font-weight: 800;
  color: #0f172a;
}
.feedback-source-meta {
  margin-top: 4px;
  font-size: 12px;
  color: #64748b;
}
.feedback-source-block + .feedback-source-block {
  margin-top: 10px;
}
.feedback-context-text {
  font-size: 12px;
  line-height: 1.7;
  color: #1e293b;
  white-space: pre-wrap;
  word-break: break-word;
}
.feedback-context-text.parent {
  max-height: 240px;
  overflow: auto;
}
.feedback-child-list {
  display: grid;
  gap: 8px;
}
.feedback-child-item {
  border-radius: 10px;
  background: rgba(248,250,252,.96);
  border: 1px solid rgba(226,232,240,.92);
  padding: 10px 12px;
}
.feedback-child-score {
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
}
.empty-state { font-size: 13px; color: #94a3b8; }

.recent-feedback-panel {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(300px, 420px);
  gap: 18px;
  align-items: start;
}
.type-rows { display: flex; flex-direction: column; gap: 20px; }
.type-rows.compact {
  padding: 16px 18px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(248,250,252,.96), rgba(239,246,255,.92));
  border: 1px solid rgba(148,163,184,.16);
}
.type-row { display: flex; align-items: center; gap: 16px; }
.type-row.compact { gap: 12px; }
.type-label { width: 100px; font-size: 14px; color: #606266; flex-shrink: 0; }
.type-count { width: 80px; text-align: right; font-size: 13px; color: #909399; }

.recent-list-shell {
  padding: 14px;
  border-radius: 16px;
  background: rgba(248,250,252,.88);
  border: 1px solid rgba(148,163,184,.16);
}
.recent-list-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
  font-size: 13px;
  font-weight: 700;
  color: #334155;
}
.recent-list {
  display: grid;
  gap: 10px;
}
.recent-list.compact {
  max-height: 248px;
  overflow-y: auto;
  padding-right: 4px;
}
.recent-item {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 16px; border-radius: 16px; background: linear-gradient(180deg, #fff, #f8fafc); border: 1px solid rgba(148,163,184,.18);
  transition: transform .18s ease, box-shadow .18s ease;
}
.recent-item.compact {
  padding: 12px 14px;
  border-radius: 14px;
}

.recent-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 12px 24px rgba(15,23,42,.08);
}

@keyframes dashboardReveal {
  from {
    opacity: 0;
    transform: translateY(18px) scale(.99);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes badgeFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}

@media (prefers-reduced-motion: reduce) {
  .motion-ready .page-head,
  .motion-ready .hero-banner,
  .motion-ready .stat-card,
  .motion-ready .section-card,
  .page-badge-card,
  .hero-pill {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}
.recent-main { display: flex; flex-direction: column; gap: 4px; }
.recent-main strong { font-size: 13px; color: #111827; }
.recent-main span { font-size: 12px; color: #64748b; }
.recent-meta { font-size: 12px; color: #94a3b8; white-space: nowrap; }

@media (max-width: 960px) {
  .page-head,
  .compare-grid,
  .feedback-detail-grid,
  .stat-cards,
  .hero-banner {
    grid-template-columns: 1fr;
  }
  .skeleton-stat-grid {
    grid-template-columns: 1fr;
  }
  .page-title-row {
    align-items: flex-start;
    flex-direction: column;
  }
  .page-head-badges {
    grid-template-columns: 1fr 1fr;
  }
  .status-card {
    align-items: flex-start;
    flex-direction: column;
  }
  .feedback-user-head,
  .feedback-user-board-head,
  .feedback-type-head,
  .feedback-detail-head,
  .feedback-detail-footer,
  .feedback-toolbar,
  .feedback-source-head {
    flex-direction: column;
    align-items: stretch;
  }
  .feedback-detail-side {
    align-items: stretch;
  }
  .feedback-toolbar-controls,
  .feedback-user-search {
    width: 100%;
    min-width: 0;
  }
  .feedback-status-filters {
    justify-content: flex-start;
  }
  .feedback-user-carousel,
  .recent-feedback-panel {
    grid-auto-flow: row;
    grid-auto-columns: unset;
    grid-template-columns: 1fr;
  }
}
</style>
