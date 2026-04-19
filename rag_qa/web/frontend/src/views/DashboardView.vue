<template>
  <div class="page">
    <div class="page-inner">
      <div class="page-title">
        <el-icon size="20"><DataAnalysis /></el-icon>
        系统驾驶仓
        <el-tag type="success" size="small" effect="light" style="margin-left:8px">实时联动</el-tag>
      </div>

      <el-skeleton :loading="loading" animated>
        <template #default>
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
              </div>
              <div class="hero-pill">
                <span class="pill-label">会话轮次</span>
                <strong>{{ stats.question_turns }}</strong>
              </div>
              <div class="hero-pill">
                <span class="pill-label">反馈覆盖</span>
                <strong>{{ stats.feedback_total }}</strong>
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
            </div>
          </el-card>

          <!-- 查询与最近反馈 -->
          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="card-head">
                <el-icon><PieChart /></el-icon>
                <span>查询轮次与近期反馈</span>
              </div>
            </template>
            <div class="type-rows">
              <div class="type-row">
                <div class="type-label">问答轮次</div>
                <el-progress :percentage="100" :stroke-width="16" color="#409eff" />
                <div class="type-count">{{ stats.question_turns }} 轮</div>
              </div>
              <div class="type-row">
                <div class="type-label">反馈覆盖</div>
                <el-progress
                  :percentage="stats.question_turns ? Math.min(100, Math.round(stats.feedback_total / stats.question_turns * 100)) : 0"
                  :stroke-width="16"
                  color="#67c23a"
                />
                <div class="type-count">{{ stats.feedback_total }} 条</div>
              </div>
            </div>
            <div class="recent-list">
              <div v-for="item in stats.recent_feedbacks" :key="item.session_id + item.timestamp" class="recent-item">
                <div class="recent-main">
                  <strong>{{ feedbackLabel(item.feedback_type) }}</strong>
                  <span>{{ item.session_id }}</span>
                </div>
                <div class="recent-meta">{{ formatTime(item.timestamp) }}</div>
              </div>
            </div>
          </el-card>

        </template>
      </el-skeleton>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'
import { feedbackAPI, sessionAPI, knowledgeAPI } from '@/api'

const loading = ref(true)
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
  feedback_total: 0,
  recent_feedbacks: [],
})

function feedbackLabel(type) {
  if (type === 'like') return '点赞'
  if (type === 'dislike') return '点踩'
  if (type === 'partial_correct') return '部分正确'
  if (type === 'correction') return '纠错'
  return type || '未知'
}

function formatTime(timestamp) {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
}

async function loadStats() {
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
      feedback_total: feedback.total_feedback || 0,
      recent_feedbacks: feedback.recent_feedbacks || [],
    }
  } catch (err) {
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
  height: calc(100vh - 60px); overflow-y: auto;
  background:
    radial-gradient(circle at 10% 14%, rgba(59, 130, 246, .11), transparent 32%),
    radial-gradient(circle at 88% 86%, rgba(16, 185, 129, .11), transparent 34%),
    linear-gradient(145deg, #f8fafc 0%, #eef2ff 52%, #ecfeff 100%);
}
.page-inner { max-width: 1280px; margin: 0 auto; padding: 28px 24px; }
.page-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 18px; font-weight: 700; color: #303133; margin-bottom: 24px;
}

.hero-banner {
  display: grid; grid-template-columns: 1.5fr 1fr; gap: 16px;
  padding: 20px 22px; border-radius: 18px; margin-bottom: 20px;
  background: linear-gradient(135deg, #0f172a, #1d4ed8 60%, #0f766e);
  color: #fff; box-shadow: 0 20px 42px rgba(15, 23, 42, .16);
}
.hero-kicker { font-size: 12px; letter-spacing: .18em; text-transform: uppercase; opacity: .72; }
.hero-title { font-size: 22px; font-weight: 800; margin: 8px 0 6px; }
.hero-desc { font-size: 13px; line-height: 1.7; color: rgba(255,255,255,.78); }
.hero-pills { display: grid; gap: 10px; align-self: center; }
.hero-pill {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 14px; border-radius: 14px;
  background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.12);
}
.pill-label { font-size: 12px; color: rgba(255,255,255,.68); }

.stat-cards {
  display: grid; grid-template-columns: repeat(4, 1fr);
  gap: 16px; margin-bottom: 20px;
}
.stat-card {
  background: #fff; border-radius: 12px; padding: 20px;
  display: flex; align-items: center; gap: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
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

.section-card { margin-bottom: 20px; border-radius: 12px; }
.card-head { display: flex; align-items: center; gap: 6px; font-size: 15px; font-weight: 600; color: #303133; }
.section-card :deep(.el-card__header) { background: rgba(248,250,252,.95); }
.section-card :deep(.el-card__body) { padding: 20px 22px; }

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
  text-align: center; padding: 16px;
  background: linear-gradient(180deg, #fff, #f8fafc); border-radius: 14px; border: 1px solid rgba(148,163,184,.18);
}
.feedback-num {
  font-size: 28px; font-weight: 700; color: #303133;
  margin: 8px 0 4px;
}
.feedback-label { font-size: 13px; color: #909399; }

.type-rows { display: flex; flex-direction: column; gap: 20px; }
.type-row { display: flex; align-items: center; gap: 16px; }
.type-label { width: 100px; font-size: 14px; color: #606266; flex-shrink: 0; }
.type-count { width: 80px; text-align: right; font-size: 13px; color: #909399; }

.recent-list { margin-top: 18px; display: grid; gap: 10px; }
.recent-item {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 14px; border-radius: 12px; background: #f8fafc; border: 1px solid rgba(148,163,184,.18);
}
.recent-main { display: flex; flex-direction: column; gap: 4px; }
.recent-main strong { font-size: 13px; color: #111827; }
.recent-main span { font-size: 12px; color: #64748b; }
.recent-meta { font-size: 12px; color: #94a3b8; white-space: nowrap; }
</style>
