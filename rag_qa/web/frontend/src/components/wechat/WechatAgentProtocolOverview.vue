<template>
  <div>
    <div v-if="handoffContractCards.length" class="handoff-contract-card">
      <div class="handoff-contract-head">
        <div>
          <div class="agent-summary-title">Handoff 契约诊断</div>
          <div class="review-entry-text">直接显示多 Agent 串联停在哪一跳、下一跳缺什么输入，以及当前为什么没有继续往后走。</div>
        </div>
      </div>
      <div class="handoff-contract-grid">
        <article
          v-for="item in handoffContractCards"
          :key="item.key"
          class="handoff-contract-item"
          :data-tone="item.tone"
        >
          <div class="handoff-contract-item-head">
            <div class="handoff-contract-item-title">{{ item.title }}</div>
            <div class="handoff-contract-item-status">{{ item.status }}</div>
          </div>
          <div class="handoff-contract-item-summary">{{ item.summary }}</div>
          <div v-if="item.chips.length" class="handoff-contract-chip-row">
            <span v-for="chip in item.chips" :key="`${item.key}:${chip}`">{{ chip }}</span>
          </div>
          <div v-if="item.detail" class="handoff-contract-item-detail">{{ item.detail }}</div>
        </article>
      </div>
    </div>

    <div class="agent-stage-strip">
      <article
        v-for="item in agentStageCards"
        :key="item.key"
        class="agent-stage-card"
        :data-tone="item.tone"
      >
        <div class="agent-stage-card-head">
          <div>
            <div class="agent-stage-card-kicker">{{ item.kicker }}</div>
            <div class="agent-stage-card-title">{{ item.title }}</div>
          </div>
          <div class="agent-stage-card-status">{{ item.status }}</div>
        </div>
        <div class="agent-stage-card-summary">{{ item.summary }}</div>
        <div v-if="item.metrics.length" class="agent-stage-card-metrics">
          <span v-for="metric in item.metrics" :key="`${item.key}:${metric}`">{{ metric }}</span>
        </div>
        <div v-if="item.detail" class="agent-stage-card-detail">{{ item.detail }}</div>
      </article>
    </div>
  </div>
</template>

<script setup>
defineProps({
  handoffContractCards: {
    type: Array,
    default: () => [],
  },
  agentStageCards: {
    type: Array,
    default: () => [],
  },
})
</script>

<style scoped>
.handoff-contract-card {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 16px;
  margin-top: 14px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.16);
  background: rgba(255, 255, 255, 0.88);
}

.handoff-contract-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
}

.handoff-contract-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
}

.handoff-contract-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(248, 250, 252, 0.88);
}

.handoff-contract-item[data-tone='success'] {
  border-color: rgba(34, 197, 94, 0.24);
  background: rgba(240, 253, 244, 0.95);
}

.handoff-contract-item[data-tone='warning'] {
  border-color: rgba(245, 158, 11, 0.24);
  background: rgba(255, 251, 235, 0.95);
}

.handoff-contract-item[data-tone='danger'] {
  border-color: rgba(239, 68, 68, 0.24);
  background: rgba(254, 242, 242, 0.95);
}

.handoff-contract-item-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.handoff-contract-item-title {
  font-size: 14px;
  font-weight: 800;
  color: #0f172a;
}

.handoff-contract-item-status {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #334155;
  background: rgba(226, 232, 240, 0.9);
}

.handoff-contract-item-summary {
  font-size: 13px;
  line-height: 1.6;
  color: #1e293b;
}

.handoff-contract-item-detail {
  font-size: 12px;
  line-height: 1.6;
  color: #475569;
}

.handoff-contract-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.handoff-contract-chip-row span {
  padding: 5px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #0f766e;
  background: rgba(204, 251, 241, 0.9);
}

.agent-stage-strip {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 14px 0;
}

.agent-stage-card {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 14px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.88);
  min-height: 182px;
}

.agent-stage-card[data-tone='success'] {
  border-color: rgba(34, 197, 94, 0.22);
  background: linear-gradient(180deg, rgba(240, 253, 244, 0.96), rgba(255, 255, 255, 0.92));
}

.agent-stage-card[data-tone='warning'] {
  border-color: rgba(245, 158, 11, 0.24);
  background: linear-gradient(180deg, rgba(255, 251, 235, 0.98), rgba(255, 255, 255, 0.92));
}

.agent-stage-card[data-tone='danger'] {
  border-color: rgba(239, 68, 68, 0.24);
  background: linear-gradient(180deg, rgba(254, 242, 242, 0.98), rgba(255, 255, 255, 0.92));
}

.agent-stage-card[data-tone='running'],
.agent-stage-card[data-tone='info'] {
  border-color: rgba(37, 99, 235, 0.2);
  background: linear-gradient(180deg, rgba(239, 246, 255, 0.96), rgba(255, 255, 255, 0.92));
}

.agent-stage-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.agent-stage-card-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #2563eb;
}

.agent-stage-card-title {
  margin-top: 2px;
  font-size: 16px;
  font-weight: 800;
  color: #0f172a;
}

.agent-stage-card-status {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #334155;
  background: rgba(226, 232, 240, 0.9);
  white-space: nowrap;
}

.agent-stage-card-summary {
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
}

.agent-stage-card-metrics {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.agent-stage-card-metrics span {
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  color: #1d4ed8;
  background: rgba(219, 234, 254, 0.9);
}

.agent-stage-card-detail {
  margin-top: auto;
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}

@media (max-width: 1080px) {
  .handoff-contract-grid,
  .agent-stage-strip {
    grid-template-columns: 1fr;
  }
}
</style>