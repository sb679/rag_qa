<template>
  <div class="page">
    <div class="page-inner">
      <div class="page-title">
        <el-icon size="20"><Setting /></el-icon>
        系统配置
        <el-tag type="info" size="small" effect="light" style="margin-left:8px">只读</el-tag>
      </div>

      <el-skeleton :loading="loading" animated>
        <template #default>

          <div class="hero-banner">
            <div>
              <div class="hero-kicker">运行时配置快照</div>
              <div class="hero-title">当前系统通过真实后端配置驱动</div>
              <div class="hero-desc">这里展示模型、检索参数和流程架构的只读状态，方便快速核对当前部署是否符合预期。</div>
            </div>
            <div class="hero-pills">
              <div class="hero-pill">
                <span class="pill-label">模式</span>
                <strong>{{ cfg.mode }}</strong>
              </div>
              <div class="hero-pill">
                <span class="pill-label">集合</span>
                <strong>{{ cfg.collection }}</strong>
              </div>
              <div class="hero-pill">
                <span class="pill-label">切块</span>
                <strong>{{ cfg.chunk_size }}</strong>
              </div>
            </div>
          </div>

          <!-- 模型配置 -->
          <el-card shadow="never" class="cfg-card">
            <template #header>
              <div class="card-head"><el-icon><Cpu /></el-icon>模型配置</div>
            </template>
            <el-descriptions :column="2" border>
              <el-descriptions-item label="LLM 模型">
                <el-tag type="primary" effect="light">{{ cfg.llm_model }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="运行模式">
                <el-tag :type="cfg.rag_available ? 'success' : 'warning'" effect="light">
                  {{ cfg.mode }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="Embedding 模型">{{ cfg.embedding_model }}</el-descriptions-item>
              <el-descriptions-item label="Reranker 模型">{{ cfg.reranker_model }}</el-descriptions-item>
              <el-descriptions-item label="通用/专业判别模型">{{ cfg.query_classifier_model }}</el-descriptions-item>
              <el-descriptions-item label="检索策略分类模型">{{ cfg.strategy_classifier_model }}</el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- 检索参数 -->
          <el-card shadow="never" class="cfg-card">
            <template #header>
              <div class="card-head"><el-icon><Search /></el-icon>检索参数</div>
            </template>
            <el-descriptions :column="2" border>
              <el-descriptions-item label="初始召回数量 K">
                <el-tag effect="plain">{{ cfg.retrieval_k }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="重排后保留数量 M">
                <el-tag effect="plain">{{ cfg.candidate_m }}</el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="分块大小（父块 / 子块）">
                {{ cfg.chunk_size }} tokens
              </el-descriptions-item>
              <el-descriptions-item label="Milvus 集合">
                {{ cfg.collection }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <!-- 检索策略说明 -->
          <el-card shadow="never" class="cfg-card">
            <template #header>
              <div class="card-head"><el-icon><Operation /></el-icon>检索策略说明</div>
            </template>
            <el-table :data="strategies" :show-header="true" stripe>
              <el-table-column label="策略名称"   prop="name"   width="160" />
              <el-table-column label="适用场景"   prop="scene"  width="180" />
              <el-table-column label="触发信号"   prop="trigger" width="240" />
              <el-table-column label="原理简介"   prop="desc" />
            </el-table>
          </el-card>

          <!-- 流程架构 -->
          <el-card shadow="never" class="cfg-card">
            <template #header>
              <div class="card-head"><el-icon><Share /></el-icon>RAG 流程架构</div>
            </template>
            <div class="pipeline">
              <div v-for="(step, i) in pipeline" :key="i" class="pipe-step">
                <div class="pipe-num">{{ i + 1 }}</div>
                <div class="pipe-body">
                  <div class="pipe-title">{{ step.title }}</div>
                  <div class="pipe-detail">{{ step.detail }}</div>
                </div>
                <el-icon v-if="i < pipeline.length - 1" class="pipe-arrow" color="#c0c4cc">
                  <ArrowRight />
                </el-icon>
              </div>
            </div>
          </el-card>

        </template>
      </el-skeleton>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Setting, Cpu, Search, Operation, Share, ArrowRight } from '@element-plus/icons-vue'
import { knowledgeAPI } from '@/api'

const loading = ref(true)
const cfg     = ref({
  llm_model: 'qwen-plus', rag_available: false, mode: '演示模式',
  embedding_model: 'BGE-M3', reranker_model: 'BGE-Reranker-Large',
  query_classifier_model: 'bert_query_classifier_new',
  strategy_classifier_model: 'bert_strategy_classifier',
  retrieval_k: 5, candidate_m: 2, chunk_size: '1200/300', collection: 'edurag_final',
})

const strategies = [
  {
    name: '直接检索',
    scene: '事实型、定义型问题',
    trigger: '关键词清晰，目标对象单一，句式短平快',
    desc: '把用户问题直接编码后在向量库召回并重排，链路最短、时延最低，适合“某规程第几条”“某参数范围”这类直达型问法。',
  },
  {
    name: 'HyDE 假设文档',
    scene: '原理解释、机制推理',
    trigger: '问题偏抽象，直接检索召回语义不稳',
    desc: '先由 LLM 写出一段“可能正确”的假设答案，再用这段文本反向检索，等于先把问题翻译成更像知识库语言的查询。',
  },
  {
    name: '子查询分解',
    scene: '复合条件、多目标对比',
    trigger: '一句话里包含“比较/同时/分别/并且”等多约束',
    desc: '把复杂问题拆成多个子问题并行检索，再做聚合去重，能减少单次检索遗漏，常用于“A 与 B 对比并给出适用条件”。',
  },
  {
    name: '场景重构检索',
    scene: '现场描述冗长、口语化',
    trigger: '包含背景叙事、条件碎片、非标准术语',
    desc: '先把现场叙事重写成可检索的“标准场景问题”，再进入召回与重排，适合“我现在这个工况该怎么处置”类情境问法。',
  },
]

const pipeline = computed(() => [
  { title: '查询分类',   detail: `${cfg.value.query_classifier_model} → 通用知识 / 专业咨询` },
  { title: '策略选择',   detail: `${cfg.value.strategy_classifier_model} 自动选择 4 种检索策略` },
  { title: '混合检索',   detail: `BGE-M3 Dense + Sparse，Milvus 召回 K=${cfg.value.retrieval_k}` },
  { title: '重排序',     detail: `${cfg.value.reranker_model} CrossEncoder，精选 M=${cfg.value.candidate_m}` },
  { title: '答案生成',   detail: `${cfg.value.llm_model} + 上下文 + 历史对话 → 流式输出` },
])

onMounted(async () => {
  try {
    const res = await knowledgeAPI.status()
    Object.assign(cfg.value, res.data.system)
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.page {
  height: calc(100vh - 60px);
  overflow-y: auto;
  background:
    radial-gradient(circle at 8% 12%, rgba(34, 197, 94, .10), transparent 35%),
    radial-gradient(circle at 92% 80%, rgba(59, 130, 246, .12), transparent 40%),
    linear-gradient(145deg, #f8fafc, #eef2ff 55%, #ecfeff);
  animation: cfgBgShift 14s ease-in-out infinite alternate;
}
.page-inner { max-width: 1120px; margin: 0 auto; padding: 28px 24px; }
.page-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 18px; font-weight: 700; color: #303133; margin-bottom: 24px;
}

.hero-banner {
  display: grid; grid-template-columns: 1.5fr 1fr; gap: 18px; align-items: center;
  padding: 20px 22px; border-radius: 18px; margin-bottom: 20px;
  background: linear-gradient(135deg, #111827, #1d4ed8 55%, #0f766e);
  color: #fff; box-shadow: 0 20px 42px rgba(15, 23, 42, .16);
}
.hero-kicker { font-size: 12px; letter-spacing: .16em; text-transform: uppercase; opacity: .7; }
.hero-title { font-size: 22px; font-weight: 800; margin: 8px 0 6px; }
.hero-desc { font-size: 13px; line-height: 1.7; color: rgba(255,255,255,.78); }
.hero-pills { display: grid; gap: 10px; }
.hero-pill {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 14px; border-radius: 14px;
  background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.12);
  transition: transform .18s ease, background .18s ease;
}
.hero-pill:hover { transform: translateY(-2px); background: rgba(255,255,255,.16); }
.pill-label { font-size: 12px; color: rgba(255,255,255,.68); }
.cfg-card  { margin-bottom: 20px; border-radius: 12px; }
.card-head { display: flex; align-items: center; gap: 6px; font-size: 15px; font-weight: 600; color: #303133; }
.cfg-card :deep(.el-card__header) { background: rgba(248,250,252,.95); }
.cfg-card :deep(.el-card__body) { padding: 22px; }

.cfg-card :deep(.el-descriptions__table) { border-radius: 12px; overflow: hidden; }
.cfg-card :deep(.el-descriptions__label) { background: #f8fafc; color: #475569; }
.cfg-card :deep(.el-table) { border-radius: 12px; overflow: hidden; }
.cfg-card :deep(.el-table__header-wrapper th) { background: #f8fafc; color: #334155; }

/* 流程图 */
.pipeline   { display: flex; align-items: center; flex-wrap: wrap; gap: 0; }
.pipe-step  { display: flex; align-items: center; gap: 0; }
.pipe-num   {
  width: 28px; height: 28px; border-radius: 50%;
  background: linear-gradient(135deg, #2563eb, #38bdf8); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700; flex-shrink: 0;
}
.pipe-body  { margin: 0 10px; }
.pipe-title { font-size: 14px; font-weight: 600; color: #303133; }
.pipe-detail{ font-size: 12px; color: #909399; margin-top: 2px; max-width: 130px; }
.pipe-arrow { flex-shrink: 0; }

@keyframes cfgBgShift {
  from { background-position: 0% 0%, 100% 100%, 0% 0%; }
  to { background-position: 8% 10%, 88% 74%, 0% 0%; }
}
</style>
