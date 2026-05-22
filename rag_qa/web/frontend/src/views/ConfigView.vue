<template>
  <div class="page motion-ready">
    <div class="page-inner">
      <div class="page-head">
        <div>
          <div class="page-kicker">Runtime snapshot</div>
          <div class="page-title-row">
            <div class="page-title">
              <el-icon size="20"><Setting /></el-icon>
              系统配置
            </div>
            <el-tag type="info" size="small" effect="light">只读</el-tag>
          </div>
          <div class="page-desc">这一页只保留对联调、排障和演示真正有帮助的配置快照，帮助你快速判断模型链路、检索参数和依赖健康状态。</div>
        </div>
      </div>

      <el-skeleton v-if="loading" animated>
        <template #template>
          <div class="config-skeleton-stack">
            <el-skeleton-item variant="image" class="skeleton-hero" />
            <div class="skeleton-snapshot-grid">
              <el-skeleton-item v-for="item in 4" :key="item" variant="rect" class="skeleton-snapshot-card" />
            </div>
            <el-skeleton-item variant="rect" class="skeleton-section" />
            <el-skeleton-item variant="rect" class="skeleton-section" />
          </div>
        </template>
      </el-skeleton>

      <div v-else-if="loadError" class="status-card error-card">
        <div class="status-icon">
          <el-icon size="26"><Operation /></el-icon>
        </div>
        <div class="status-copy">
          <div class="status-title">系统配置暂时无法加载</div>
          <div class="status-desc">{{ loadError }}</div>
        </div>
        <el-button type="primary" plain @click="loadConfig">重新加载</el-button>
      </div>

      <template v-else>

          <div class="hero-banner">
            <div>
              <div class="hero-kicker">运行时配置快照</div>
              <div class="hero-title">当前系统通过真实后端配置驱动</div>
              <div class="hero-desc">这里把项目文档里真正有价值的部分压缩为运行快照、链路说明和依赖状态，方便直接判断系统是否处于可用形态。</div>
            </div>
            <div class="hero-pills">
              <div class="hero-pill">
                <span class="pill-label">模式</span>
                <strong>{{ cfg.mode }}</strong>
                <small>当前运行模式</small>
              </div>
              <div class="hero-pill">
                <span class="pill-label">集合</span>
                <strong>{{ cfg.collection }}</strong>
                <small>Milvus 当前集合</small>
              </div>
              <div class="hero-pill">
                <span class="pill-label">切块</span>
                <strong>{{ cfg.chunk_size }}</strong>
                <small>父块 / 子块口径</small>
              </div>
              <div class="hero-pill">
                <span class="pill-label">向量数</span>
                <strong>{{ cfg.total_vectors }}</strong>
                <small>来自真实后端状态</small>
              </div>
            </div>
          </div>

          <div class="snapshot-grid">
            <div v-for="item in runtimeSnapshot" :key="item.label" class="snapshot-card">
              <div class="snapshot-label">{{ item.label }}</div>
              <div class="snapshot-value">{{ item.value }}</div>
              <div class="snapshot-desc">{{ item.desc }}</div>
            </div>
          </div>

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
              <el-descriptions-item label="Milvus 向量数">
                {{ cfg.total_vectors }}
              </el-descriptions-item>
              <el-descriptions-item label="初始化耗时">
                {{ initDurationLabel }}
              </el-descriptions-item>
            </el-descriptions>
          </el-card>

          <el-card shadow="never" class="cfg-card">
            <template #header>
              <div class="card-head"><el-icon><Share /></el-icon>依赖健康状态</div>
            </template>
            <div class="health-grid">
              <div v-for="item in dependencyStatus" :key="item.label" class="health-item">
                <div class="health-row">
                  <span class="health-label">{{ item.label }}</span>
                  <el-tag size="small" :type="item.ok ? 'success' : 'warning'" effect="light">
                    {{ item.ok ? '正常' : '待确认' }}
                  </el-tag>
                </div>
                <div class="health-desc">{{ item.desc }}</div>
              </div>
            </div>
          </el-card>

      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { Setting, Cpu, Search, Operation, Share } from '@element-plus/icons-vue'
import { knowledgeAPI } from '@/api'

const loading = ref(true)
const loadError = ref('')
const cfg     = ref({
  llm_model: 'qwen-plus', rag_available: false, mode: '演示模式',
  general_llm_model: 'deepseek-v4-flash', general_llm_base_url: 'https://api.deepseek.com',
  compare_llm_model: 'auto', compare_llm_base_url: '',
  embedding_model: 'BGE-M3', reranker_model: 'BGE-Reranker-Large',
  query_classifier_model: 'bert_query_classifier_new',
  strategy_classifier_model: 'bert_strategy_classifier',
  retrieval_k: 5, candidate_m: 2, chunk_size: '1200/300', collection: 'edurag_final',
  parent_chunk_size: 1200, child_chunk_size: 300, chunk_overlap: 50,
  chunking_mode: 'rule', chunking_mode_by_source: {}, semantic_model_path: 'models/bge-m3',
  semantic_sim_threshold: 0.74, semantic_min_chunk_size: 220, semantic_max_chunk_size: 520,
  retrieval_stack: 'BGE-M3 dense+sparse + Milvus hybrid search + BGE reranker',
  service_ready: false, milvus_connected: false, total_vectors: '连接中', init_duration_sec: null,
  dependency_checks: {},
})

const initDurationLabel = computed(() => {
  if (cfg.value.init_duration_sec === null || cfg.value.init_duration_sec === undefined) {
    return '未上报'
  }
  return `${cfg.value.init_duration_sec} s`
})

const runtimeSnapshot = computed(() => [
  {
    label: '服务状态',
    value: cfg.value.service_ready ? '可联调' : '降级中',
    desc: cfg.value.service_ready ? '后端与向量链路已具备完整问答条件。' : '当前仍可查看配置，但完整 RAG 能力未必可用。',
  },
  {
    label: '知识链路',
    value: cfg.value.milvus_connected ? 'Milvus 已连接' : 'Milvus 未就绪',
    desc: cfg.value.milvus_connected ? '知识入库、统计和专业检索可进入正常路径。' : '知识库统计、入库和专业检索会受影响。',
  },
  {
    label: '问答路由',
    value: `${cfg.value.query_classifier_model} + ${cfg.value.strategy_classifier_model}`,
    desc: '先区分通用知识/专业咨询，再对专业咨询选择具体检索策略。',
  },
  {
    label: '生成链路',
    value: `${cfg.value.general_llm_model} / ${cfg.value.llm_model}`,
    desc: '通用知识走通用直答模型，专业咨询走 RAG 主回答模型。',
  },
])

const modelGroups = computed(() => [
  {
    title: '回答模型',
    items: [
      { label: '专业回答模型', value: cfg.value.llm_model, tag: true, tagType: 'primary' },
      { label: '通用直答模型', value: cfg.value.general_llm_model || '未配置' },
      { label: '运行模式', value: cfg.value.mode, tag: true, tagType: cfg.value.rag_available ? 'success' : 'warning' },
      { label: '通用模型端点', value: shortBaseUrl(cfg.value.general_llm_base_url) },
      { label: '对比回答模型', value: cfg.value.compare_llm_model || '未启用' },
      { label: '对比模型端点', value: shortBaseUrl(cfg.value.compare_llm_base_url) },
    ],
  },
  {
    title: '检索模型',
    items: [
      { label: 'Embedding 模型', value: cfg.value.embedding_model },
      { label: 'Reranker 模型', value: cfg.value.reranker_model },
      { label: '语义分块模型', value: shortPath(cfg.value.semantic_model_path) },
      { label: '混合检索栈', value: cfg.value.retrieval_stack },
    ],
  },
  {
    title: '路由模型',
    items: [
      { label: '通用/专业判别模型', value: cfg.value.query_classifier_model },
      { label: '检索策略分类模型', value: cfg.value.strategy_classifier_model },
    ],
  },
])

function shortPath(value) {
  const text = String(value || '')
  const normalized = text.replace(/\\/g, '/')
  const parts = normalized.split('/')
  return parts.slice(-2).join('/') || text
}

function shortBaseUrl(value) {
  const text = String(value || '').trim()
  if (!text) return '未配置'
  return text.replace(/^https?:\/\//, '')
}

const dependencyStatus = computed(() => {
  const checks = cfg.value.dependency_checks || {}
  return [
    {
      label: 'LLM 客户端',
      ok: Boolean(checks.llm_client),
      desc: checks.llm_client ? `专业回答模型 ${cfg.value.llm_model} 可参与回答生成。` : '专业回答模型客户端未就绪，回答链路会受影响。',
    },
    {
      label: '通用直答模型',
      ok: Boolean(checks.general_llm_client),
      desc: checks.general_llm_client ? `通用直答模型 ${cfg.value.general_llm_model} 已接入。` : '通用直答模型未单独配置，可能回退到主模型。',
    },
    {
      label: '向量库 / Milvus',
      ok: Boolean(checks.milvus && checks.vector_store),
      desc: checks.milvus && checks.vector_store ? '向量检索与知识统计链路可用。' : '向量检索链路未完全就绪。',
    },
    {
      label: '查询分类器',
      ok: Boolean(checks.query_classifier),
      desc: checks.query_classifier ? `当前使用 ${cfg.value.query_classifier_model} 进行通用/专业分流。` : '查询分类器不可用时，系统会更依赖降级路径。',
    },
    {
      label: '策略选择器',
      ok: Boolean(checks.strategy_selector),
      desc: checks.strategy_selector ? '四策略路由已启用。' : '策略选择器未就绪时，专业咨询将难以稳定走到最优检索路径。',
    },
  ]
})

async function loadConfig() {
  loading.value = true
  loadError.value = ''
  try {
    const res = await knowledgeAPI.status()
    Object.assign(cfg.value, res.data.system)
  } catch (err) {
    loadError.value = err?.response?.data?.detail || '暂时无法获取系统配置快照，请检查后端服务后重试。'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  loadConfig()
})
</script>

<style scoped>
.page {
  height: calc(100vh - 72px);
  overflow-y: auto;
  background:
    radial-gradient(circle at 8% 12%, rgba(34, 197, 94, .10), transparent 24%),
    radial-gradient(circle at 92% 80%, rgba(59, 130, 246, .12), transparent 28%),
    radial-gradient(circle at 76% 18%, rgba(249, 115, 22, .08), transparent 22%),
    linear-gradient(145deg, #f8fafc, #eef2ff 55%, #ecfeff);
  animation: cfgBgShift 14s ease-in-out infinite alternate;
}

.motion-ready .page-head,
.motion-ready .hero-banner,
.motion-ready .snapshot-card,
.motion-ready .cfg-card {
  opacity: 0;
  transform: translateY(18px);
  animation: cfgReveal .76s cubic-bezier(.22,1,.36,1) forwards;
}

.motion-ready .page-head { animation-delay: .04s; }
.motion-ready .hero-banner { animation-delay: .12s; }
.motion-ready .snapshot-card:nth-child(1) { animation-delay: .18s; }
.motion-ready .snapshot-card:nth-child(2) { animation-delay: .24s; }
.motion-ready .snapshot-card:nth-child(3) { animation-delay: .3s; }
.motion-ready .snapshot-card:nth-child(4) { animation-delay: .36s; }
.motion-ready .cfg-card:nth-of-type(1) { animation-delay: .44s; }
.motion-ready .cfg-card:nth-of-type(2) { animation-delay: .52s; }
.motion-ready .cfg-card:nth-of-type(3) { animation-delay: .6s; }
.motion-ready .cfg-card:nth-of-type(4) { animation-delay: .68s; }
.motion-ready .cfg-card:nth-of-type(5) { animation-delay: .76s; }


.page-inner {
  max-width: 1180px;
  margin: 0 auto;
  padding: 28px 24px 36px;
}

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
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 28px;
  font-weight: 900;
  color: #0f172a;
  letter-spacing: -0.03em;
}

.page-desc {
  margin-top: 10px;
  max-width: 62ch;
  font-size: 13px;
  line-height: 1.8;
  color: #64748b;
}

.config-skeleton-stack {
  display: grid;
  gap: 18px;
}

.skeleton-hero,
.skeleton-section,
.skeleton-snapshot-card {
  overflow: hidden;
  border-radius: 24px;
}

.skeleton-hero {
  width: 100%;
  height: 182px;
}

.skeleton-snapshot-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
}

.skeleton-snapshot-card {
  width: 100%;
  height: 124px;
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
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 18px;
  align-items: center;
  padding: 24px 26px;
  border-radius: 28px;
  margin-bottom: 20px;
  background: linear-gradient(135deg, #111827, #1d4ed8 55%, #0f766e);
  color: #fff;
  box-shadow: 0 24px 54px rgba(15, 23, 42, .16);
}

.hero-kicker { font-size: 12px; letter-spacing: .16em; text-transform: uppercase; opacity: .7; }
.hero-title {
  font-size: 30px;
  font-weight: 900;
  margin: 10px 0 8px;
  line-height: 1.08;
  letter-spacing: -.03em;
  max-width: 16ch;
}
.hero-desc {
  font-size: 13px;
  line-height: 1.8;
  color: rgba(255,255,255,.78);
  max-width: 54ch;
}

.hero-pills { display: grid; gap: 10px; }

.hero-pill {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255,255,255,.10);
  border: 1px solid rgba(255,255,255,.12);
  transition: transform .18s ease, background .18s ease;
  backdrop-filter: blur(10px);
  animation: cfgFloat 7s ease-in-out infinite;
}
.hero-pill:nth-child(2) { animation-delay: .8s; }
.hero-pill:nth-child(3) { animation-delay: 1.6s; }
.hero-pill:nth-child(4) { animation-delay: 2.4s; }

.hero-pill:hover { transform: translateY(-2px); background: rgba(255,255,255,.16); }
.pill-label { font-size: 12px; color: rgba(255,255,255,.68); }
.hero-pill strong {
  font-size: 24px;
  font-weight: 900;
}
.hero-pill small {
  font-size: 11px;
  color: rgba(255,255,255,.72);
}

.cfg-card {
  margin-bottom: 20px;
  border-radius: 22px;
  overflow: hidden;
  box-shadow: 0 18px 36px rgba(15,23,42,.06);
}

.card-head { display: flex; align-items: center; gap: 6px; font-size: 15px; font-weight: 700; color: #0f172a; }
.cfg-card :deep(.el-card__header) { background: rgba(248,250,252,.95); border-bottom: 1px solid rgba(148,163,184,.12); }
.cfg-card :deep(.el-card__body) { padding: 22px; }

.snapshot-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 20px;
}

.snapshot-card {
  padding: 18px 18px;
  border-radius: 20px;
  background: rgba(255,255,255,.74);
  border: 1px solid rgba(148, 163, 184, .18);
  box-shadow: 0 10px 24px rgba(15, 23, 42, .06);
  backdrop-filter: blur(10px);
  transition: transform .18s ease, box-shadow .18s ease;
}
.snapshot-card:hover,
.health-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 28px rgba(15,23,42,.08);
}

.snapshot-label { font-size: 12px; color: #64748b; margin-bottom: 8px; }
.snapshot-value { font-size: 18px; font-weight: 800; color: #0f172a; margin-bottom: 6px; }
.snapshot-desc { font-size: 12px; line-height: 1.7; color: #475569; }

.cfg-card :deep(.el-descriptions__table) { border-radius: 12px; overflow: hidden; }
.cfg-card :deep(.el-descriptions__label) { background: #f8fafc; color: #475569; }

.health-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
}

.health-item {
  padding: 16px 18px;
  border-radius: 18px;
  background: #fff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 10px 24px rgba(15,23,42,.04);
  transition: transform .18s ease, box-shadow .18s ease;
}

@keyframes cfgReveal {
  from {
    opacity: 0;
    transform: translateY(18px) scale(.99);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes cfgFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}

.health-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.health-label { font-size: 14px; font-weight: 700; color: #0f172a; }
.health-desc { margin-top: 8px; font-size: 13px; line-height: 1.7; color: #475569; }

.model-groups { display: grid; gap: 16px; }
.model-group { display: grid; gap: 10px; }
.model-group-head { font-size: 13px; font-weight: 700; color: #0f172a; letter-spacing: .04em; }

@media (max-width: 1100px) {
  .page-head,
  .snapshot-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .skeleton-snapshot-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}

@media (max-width: 900px) {
  .page-title-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .hero-banner { grid-template-columns: 1fr; }
  .health-grid { grid-template-columns: 1fr; }
}

@media (max-width: 720px) {
  .page-inner { padding: 20px 14px; }
  .snapshot-grid,
  .page-head { grid-template-columns: 1fr; }
  .skeleton-snapshot-grid { grid-template-columns: 1fr; }
  .status-card {
    align-items: flex-start;
    flex-direction: column;
  }
}

@keyframes cfgBgShift {
  from { background-position: 0% 0%, 100% 100%, 0% 0%; }
  to { background-position: 8% 10%, 88% 74%, 0% 0%; }
}

@media (prefers-reduced-motion: reduce) {
  .motion-ready .page-head,
  .motion-ready .hero-banner,
  .motion-ready .snapshot-card,
  .motion-ready .cfg-card,
  .hero-pill {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}
</style>
