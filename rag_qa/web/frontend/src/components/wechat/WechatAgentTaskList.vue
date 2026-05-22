<template>
  <div v-if="taskList.length" class="agent-task-list-card">
    <div class="agent-task-list-header">
      <div>
        <div class="agent-task-card-kicker">最近任务</div>
        <div class="agent-task-list-title">默认收起，只看最近几条任务和文章标题。</div>
      </div>
      <div class="agent-task-list-header-actions">
        <el-button size="small" text @click="$emit('toggle')">{{ expanded ? '收起列表' : '展开列表' }}</el-button>
        <el-button size="small" plain :loading="loading" @click="$emit('refresh')">刷新列表</el-button>
      </div>
    </div>
    <div class="agent-task-list-summary-row">
      <span>全部 {{ stats.total }}</span>
      <span>进行中 {{ stats.active }}</span>
      <span>失败 {{ stats.failed }}</span>
      <span>已完成 {{ stats.completed }}</span>
    </div>
    <div v-if="expanded" class="agent-task-filter-row">
      <button type="button" class="local-account-filter-chip" :data-active="filter === 'all'" @click="$emit('update:filter', 'all')">全部</button>
      <button type="button" class="local-account-filter-chip" :data-active="filter === 'active'" @click="$emit('update:filter', 'active')">进行中</button>
      <button type="button" class="local-account-filter-chip" :data-active="filter === 'failed'" @click="$emit('update:filter', 'failed')">失败</button>
      <button type="button" class="local-account-filter-chip" :data-active="filter === 'completed'" @click="$emit('update:filter', 'completed')">已完成</button>
    </div>
    <div v-if="expanded" class="agent-task-list-items">
      <button
        v-for="task in visibleTasks"
        :key="task.task_id"
        type="button"
        class="agent-task-list-item"
        :data-active="selectedTaskId === task.task_id ? 'true' : 'false'"
        @click="$emit('select', task)"
      >
        <div class="agent-task-list-item-head">
          <span class="agent-task-list-item-title">{{ task.goal || '延后入库任务' }}</span>
          <span class="agent-task-list-item-status" :data-status="task.status">{{ formatStatus(task.status) }}</span>
        </div>
        <div class="agent-task-list-item-meta">
          <span>{{ task.account_id || '未记录账号' }}</span>
          <span>{{ Array.isArray(task.article_ids) ? task.article_ids.length : 0 }} 篇</span>
          <span>{{ formatTime(task.updated_at || task.created_at) }}</span>
        </div>
        <div v-if="getArticlePreview(task).length" class="agent-task-list-item-article-row">
          <span v-for="title in getArticlePreview(task)" :key="`${task.task_id}:${title}`" class="agent-task-list-item-article-chip">{{ title }}</span>
        </div>
        <div v-if="task.summary" class="agent-task-list-item-summary">{{ task.summary }}</div>
        <div v-if="getResultSummary(task).length" class="agent-task-list-item-meta">
          <span v-for="item in getResultSummary(task)" :key="`${task.task_id}:${item}`">{{ item }}</span>
        </div>
        <div class="agent-task-list-item-actions">
          <el-button size="small" text @click.stop="$emit('select', task)">选中</el-button>
          <el-button size="small" text @click.stop="$emit('detail', task)">详情</el-button>
          <el-button v-if="canOpenAccount(task)" size="small" text @click.stop="$emit('open-account', task)">进入账号</el-button>
          <el-button v-if="canOpenArticle(task)" size="small" text @click.stop="$emit('open-article', task)">进入文章</el-button>
          <el-button v-if="task.status === 'failed'" size="small" text type="warning" :loading="retryingId === task.task_id" @click.stop="$emit('retry', task.task_id)">重试</el-button>
        </div>
      </button>
      <div v-if="!visibleTasks.length" class="agent-task-list-empty">当前筛选条件下没有任务。</div>
    </div>
    <div v-else class="agent-task-list-collapsed-tip">最近任务已收起。展开后可查看最近 5 条任务、文章标题和快捷入口。</div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  taskList: { type: Array, default: () => [] },
  filteredTasks: { type: Array, default: () => [] },
  stats: { type: Object, default: () => ({ total: 0, active: 0, failed: 0, completed: 0 }) },
  expanded: { type: Boolean, default: false },
  filter: { type: String, default: 'all' },
  loading: { type: Boolean, default: false },
  selectedTaskId: { type: String, default: '' },
  retryingId: { type: String, default: '' },
  formatStatus: { type: Function, required: true },
  formatTime: { type: Function, required: true },
  getArticlePreview: { type: Function, required: true },
  getResultSummary: { type: Function, required: true },
  canOpenAccount: { type: Function, required: true },
  canOpenArticle: { type: Function, required: true },
})

defineEmits(['toggle', 'refresh', 'update:filter', 'select', 'detail', 'open-account', 'open-article', 'retry'])

const visibleTasks = computed(() => (Array.isArray(props.filteredTasks) ? props.filteredTasks : []).slice(0, 5))
</script>

<style scoped>
.agent-task-list-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px 14px;
  border-radius: 14px;
  border: 1px solid rgba(148, 163, 184, 0.22);
  background: rgba(248, 250, 252, 0.94);
}

.agent-task-card-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #92400e;
}

.agent-task-list-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.agent-task-list-header-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-task-list-title {
  margin-top: 2px;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.agent-task-list-summary-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  font-size: 12px;
  color: #64748b;
}

.agent-task-filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-task-list-collapsed-tip {
  font-size: 12px;
  color: #64748b;
}

.agent-task-list-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.agent-task-list-item {
  width: 100%;
  text-align: left;
  border: 1px solid rgba(148, 163, 184, 0.2);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.96);
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  cursor: pointer;
}

.agent-task-list-item[data-active='true'] {
  border-color: rgba(59, 130, 246, 0.3);
  box-shadow: 0 0 0 1px rgba(59, 130, 246, 0.12);
}

.agent-task-list-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.agent-task-list-item-title {
  font-size: 12px;
  font-weight: 700;
  color: #0f172a;
}

.agent-task-list-item-status {
  font-size: 11px;
  font-weight: 700;
  color: #475569;
}

.agent-task-list-item-status[data-status='completed'] {
  color: #15803d;
}

.agent-task-list-item-status[data-status='failed'] {
  color: #b45309;
}

.agent-task-list-item-status[data-status='queued'],
.agent-task-list-item-status[data-status='running'],
.agent-task-list-item-status[data-status='deferred'] {
  color: #1d4ed8;
}

.agent-task-list-item-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
  font-size: 12px;
  color: #64748b;
}

.agent-task-list-item-article-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
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

.agent-task-list-item-summary {
  font-size: 12px;
  line-height: 1.5;
  color: #334155;
}

.agent-task-list-item-actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.agent-task-list-empty {
  font-size: 12px;
  color: #64748b;
}
</style>