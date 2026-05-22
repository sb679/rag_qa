<template>
  <el-dialog :model-value="visible" width="760px" title="任务详情" destroy-on-close @update:model-value="$emit('update:visible', $event)">
    <template v-if="task">
      <div class="agent-task-detail-grid">
        <div class="agent-task-detail-row">
          <span class="agent-task-detail-label">任务ID</span>
          <span class="agent-task-detail-value">{{ task.task_id }}</span>
        </div>
        <div class="agent-task-detail-row">
          <span class="agent-task-detail-label">状态</span>
          <span class="agent-task-detail-value">{{ formatStatus(task.status) }}</span>
        </div>
        <div class="agent-task-detail-row">
          <span class="agent-task-detail-label">账号</span>
          <span class="agent-task-detail-value">{{ task.account_id || '未记录' }}</span>
        </div>
        <div class="agent-task-detail-row">
          <span class="agent-task-detail-label">更新时间</span>
          <span class="agent-task-detail-value">{{ formatTime(task.updated_at || task.created_at) }}</span>
        </div>
      </div>
      <div v-if="task.summary" class="agent-task-detail-summary">{{ task.summary }}</div>
      <div v-if="resultSummary.length" class="agent-task-detail-chip-row">
        <span v-for="item in resultSummary" :key="`${task.task_id}:detail:${item}`" class="agent-task-detail-chip">{{ item }}</span>
      </div>
      <div v-if="articleEntries.length" class="agent-task-detail-section">
        <div class="agent-task-detail-section-head">
          <div class="agent-task-detail-section-title">本次涉及文章</div>
          <div class="agent-task-detail-section-meta">共 {{ articleEntries.length }} 篇</div>
        </div>
        <div class="agent-task-detail-article-list">
          <button
            v-for="entry in articleEntries"
            :key="`${task.task_id}:article:${entry.articleId}`"
            type="button"
            class="agent-task-detail-article-item"
            :data-resolved="entry.resolved ? 'true' : 'false'"
            :disabled="!entry.resolved"
            @click="$emit('open-resolved-article', entry)"
          >
            <span class="agent-task-detail-article-name">{{ entry.title }}</span>
            <span class="agent-task-detail-article-meta">{{ entry.accountId || '未记录账号' }} · {{ entry.articleId }} · {{ entry.resolved ? '可打开' : '本地未定位' }}</span>
          </button>
        </div>
      </div>
      <div v-if="errorText" class="agent-task-detail-section">
        <div class="agent-task-detail-section-head">
          <div class="agent-task-detail-section-title">最近错误</div>
          <div class="agent-task-detail-inline-actions">
            <el-button size="small" text @click="$emit('copy-error')">复制错误</el-button>
            <el-button v-if="errorText.length > 240" size="small" text @click="$emit('toggle-error-expanded')">{{ errorExpanded ? '收起' : '展开' }}</el-button>
          </div>
        </div>
        <div class="agent-task-detail-error">{{ errorPreview }}</div>
      </div>
      <div class="agent-task-detail-timeline">
        <div class="agent-task-detail-section-head">
          <div class="agent-task-detail-timeline-title">事件时间线</div>
          <div class="agent-task-detail-inline-actions">
            <el-button size="small" text @click="$emit('copy-timeline')">复制时间线</el-button>
            <el-button size="small" text @click="$emit('copy-diagnostic-summary')">复制诊断摘要</el-button>
          </div>
        </div>
        <div v-if="reversedEvents.length" class="agent-task-detail-events">
          <div v-for="item in reversedEvents" :key="`${task.task_id}:detail:${item.at}:${item.type}`" class="agent-task-detail-event">
            <div class="agent-task-detail-event-time">{{ formatTime(item.at) }}</div>
            <div class="agent-task-detail-event-body">
              <div class="agent-task-detail-event-message">{{ item.message }}</div>
              <div v-if="formatEventDetail(item)" class="agent-task-detail-event-detail">{{ formatEventDetail(item) }}</div>
            </div>
          </div>
        </div>
        <div v-else class="agent-task-detail-empty">当前任务还没有可显示的事件。</div>
      </div>
    </template>
    <template #footer>
      <div class="agent-task-detail-footer">
        <el-button v-if="task && canOpenAccount(task)" plain @click="$emit('open-account', task)">进入账号</el-button>
        <el-button v-if="task && canOpenArticle(task)" plain @click="$emit('open-article', task)">进入文章</el-button>
        <el-button v-if="task?.status === 'failed'" type="warning" plain :loading="retryingId === task?.task_id" @click="$emit('retry', task?.task_id)">重试任务</el-button>
        <el-button @click="$emit('update:visible', false)">关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  visible: { type: Boolean, default: false },
  task: { type: Object, default: null },
  articleEntries: { type: Array, default: () => [] },
  errorText: { type: String, default: '' },
  errorPreview: { type: String, default: '' },
  errorExpanded: { type: Boolean, default: false },
  retryingId: { type: String, default: '' },
  formatStatus: { type: Function, required: true },
  formatTime: { type: Function, required: true },
  formatEventDetail: { type: Function, required: true },
  buildResultSummary: { type: Function, required: true },
  canOpenAccount: { type: Function, required: true },
  canOpenArticle: { type: Function, required: true },
})

defineEmits([
  'update:visible',
  'toggle-error-expanded',
  'open-resolved-article',
  'copy-error',
  'copy-timeline',
  'copy-diagnostic-summary',
  'open-account',
  'open-article',
  'retry',
])

const resultSummary = computed(() => (props.task ? props.buildResultSummary(props.task) : []))
const reversedEvents = computed(() => {
  const events = Array.isArray(props.task?.events) ? props.task.events : []
  return events.slice().reverse()
})
</script>

<style scoped>
.agent-task-detail-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px 16px;
}

.agent-task-detail-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.agent-task-detail-label {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
}

.agent-task-detail-value {
  font-size: 12px;
  line-height: 1.5;
  color: #0f172a;
  word-break: break-word;
}

.agent-task-detail-summary {
  margin-top: 14px;
  font-size: 12px;
  line-height: 1.6;
  color: #334155;
}

.agent-task-detail-chip-row {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-task-detail-chip {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(219, 234, 254, 0.95);
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 700;
}

.agent-task-detail-section {
  margin-top: 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.agent-task-detail-section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.agent-task-detail-section-title {
  font-size: 13px;
  font-weight: 800;
  color: #0f172a;
}

.agent-task-detail-section-meta {
  font-size: 12px;
  color: #64748b;
}

.agent-task-detail-inline-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-task-detail-article-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-task-detail-article-item {
  width: 100%;
  padding: 10px 12px;
  border-radius: 12px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.94);
  text-align: left;
  display: flex;
  flex-direction: column;
  gap: 4px;
  cursor: pointer;
}

.agent-task-detail-article-item[data-resolved='true'] {
  border-color: rgba(59, 130, 246, 0.2);
  background: rgba(239, 246, 255, 0.94);
}

.agent-task-detail-article-item:disabled {
  cursor: not-allowed;
  opacity: 0.72;
}

.agent-task-detail-article-name {
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.agent-task-detail-article-meta {
  font-size: 12px;
  line-height: 1.5;
  color: #64748b;
  word-break: break-word;
}

.agent-task-detail-error {
  padding: 10px 12px;
  border-radius: 12px;
  background: rgba(254, 242, 242, 0.96);
  border: 1px solid rgba(239, 68, 68, 0.18);
  color: #b91c1c;
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}

.agent-task-detail-timeline {
  margin-top: 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.agent-task-detail-timeline-title {
  font-size: 13px;
  font-weight: 800;
  color: #0f172a;
}

.agent-task-detail-events {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.agent-task-detail-event {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 10px;
}

.agent-task-detail-event-time {
  font-size: 12px;
  color: #64748b;
}

.agent-task-detail-event-body {
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.agent-task-detail-event-message {
  font-size: 12px;
  color: #334155;
}

.agent-task-detail-event-detail {
  font-size: 12px;
  color: #64748b;
  line-height: 1.5;
}

.agent-task-detail-empty {
  font-size: 12px;
  color: #64748b;
}

.agent-task-detail-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

@media (max-width: 760px) {
  .agent-task-detail-grid {
    grid-template-columns: 1fr;
  }

  .agent-task-detail-event {
    grid-template-columns: 1fr;
    gap: 4px;
  }
}
</style>