<template>
  <div class="page">
    <div class="page-inner">
      <div class="page-title">
        <el-icon size="20"><DataBoard /></el-icon>
        知识库概览
        <el-tag type="success" size="small" effect="light" style="margin-left:8px">真实统计</el-tag>
      </div>

      <el-skeleton :loading="loading" animated>
        <template #default>
          <div class="hero-banner">
            <div class="hero-copy">
              <div class="hero-kicker">知识资产与来源分布</div>
              <div class="hero-title">Milvus 真实分块统计 + 文档来源结构</div>
              <div class="hero-desc">展示后端当前可用的向量数量、收录册数和每个来源的占比，不再使用笼统占位。</div>
            </div>
            <div class="hero-metrics">
              <div class="hero-metric">
                <span class="metric-name">向量总量</span>
                <span class="metric-value">{{ sys.total_vectors || stats.total_chunks }}</span>
              </div>
              <div class="hero-metric">
                <span class="metric-name">收录册数</span>
                <span class="metric-value">{{ displayBooks }}</span>
              </div>
              <div class="hero-metric">
                <span class="metric-name">平均每册</span>
                <span class="metric-value">{{ stats.avg_chunks_per_book || 0 }}</span>
              </div>
            </div>
          </div>

          <!-- 顶部统计卡片 -->
          <div class="stat-cards">
            <div class="stat-card">
              <div class="stat-icon blue"><el-icon size="28"><Document /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">{{ displayBooks }}</div>
                <div class="stat-lbl">收录书籍（册）</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon green"><el-icon size="28"><Grid /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">{{ stats.total_chunks.toLocaleString() }}</div>
                <div class="stat-lbl">向量分块总数</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon orange"><el-icon size="28"><Search /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">混合检索</div>
                <div class="stat-lbl">Dense + Sparse</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon purple"><el-icon size="28"><Rank /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">{{ stats.source_count || stats.sources.length }}</div>
                <div class="stat-lbl">来源维度</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon teal"><el-icon size="28"><Monitor /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">{{ sys.total_vectors || '—' }}</div>
                <div class="stat-lbl">集合向量数</div>
              </div>
            </div>
          </div>

          <!-- 数据来源分布 -->
          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="card-head">
                <el-icon><Folder /></el-icon>
                <span>数据来源分布</span>
                <span class="card-sub">总计 {{ stats.total_chunks.toLocaleString() }} 个分块，按来源比例拆解</span>
              </div>
            </template>
            <div class="source-rows">
              <div
                v-for="(src, i) in stats.sources"
                :key="i"
                class="source-row"
              >
                <div class="src-label">
                  <div>{{ src.name }}</div>
                  <small>{{ Math.round((src.ratio || 0) * 100) }}% 占比</small>
                </div>
                <el-progress
                  :percentage="Math.round((src.ratio || (src.chunks / stats.total_chunks)) * 100)"
                  :stroke-width="12"
                  :color="progressColors[i % progressColors.length]"
                  class="src-bar"
                />
                <div class="src-count">{{ src.chunks.toLocaleString() }} 块</div>
              </div>
            </div>
          </el-card>

          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="card-head">
                <el-icon><Document /></el-icon>
                <span>知识文件清单</span>
                <span class="card-sub">共 {{ rawFiles.length }} 个文件</span>
              </div>
            </template>
            <div v-if="rawFiles.length" class="file-list">
              <div v-for="(file, i) in rawFiles" :key="`${file.file_id || file.name}-${i}`" class="file-item">
                <div class="file-main">
                  <div class="file-name">{{ file.name }}</div>
                  <div class="file-meta">来源：{{ file.source || 'unknown' }}</div>
                </div>
                <div class="file-actions">
                  <div class="file-chunks">{{ file.chunks }} 块</div>
                  <el-button text type="primary" size="small" @click="viewRawFile(file)">查看</el-button>
                  <el-button text type="danger" size="small" :disabled="!file.can_delete" @click="deleteRawFile(file)">删除</el-button>
                </div>
              </div>
            </div>
            <div v-else class="empty-hint">暂无原始上传文件</div>
          </el-card>

          <!-- 处理流程说明 -->
          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="card-head">
                <el-icon><Operation /></el-icon>
                <span>文档处理流程</span>
              </div>
            </template>
            <el-steps :active="4" align-center finish-status="success">
              <el-step title="文档加载" description="PDF / Word / PPT + OCR" />
              <el-step title="文本分块" description="父块 1200 / 子块 300 tokens" />
              <el-step title="向量化" description="BGE-M3 (1024 维 Dense + Sparse)" />
              <el-step title="入库" description="Milvus 向量数据库" />
            </el-steps>
          </el-card>

          <!-- 系统状态 -->
          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="card-head">
                <el-icon><Monitor /></el-icon>
                <span>系统组件状态</span>
              </div>
            </template>
            <div class="status-grid">
              <div
                v-for="item in statusItems"
                :key="item.name"
                class="status-item"
              >
                <el-tag
                  :type="item.ok ? 'success' : 'danger'"
                  size="small"
                  effect="light"
                  class="status-tag"
                >{{ item.ok ? '正常' : '离线' }}</el-tag>
                <div class="status-name">{{ item.name }}</div>
                <div class="status-val">{{ item.value }}</div>
              </div>
            </div>
          </el-card>

        </template>
      </el-skeleton>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DataBoard, Document, Grid, Search, Rank, Folder, Operation, Monitor } from '@element-plus/icons-vue'
import { knowledgeAPI, datasetAPI } from '@/api'

const loading = ref(true)
const raw     = ref({ system: {}, knowledge: { total_chunks: 0, total_books: 0, sources: [], files: [] } })
const rawFiles = ref([])

const stats = computed(() => raw.value.knowledge)
const sys   = computed(() => raw.value.system)
const displayBooks = computed(() => rawFiles.value.length || stats.value.total_books || 0)

const progressColors = ['#409eff', '#67c23a', '#f0a020']

const statusItems = computed(() => [
  { name: 'Milvus 向量库',   ok: sys.value.milvus_connected, value: sys.value.milvus_connected ? '已连接' : '未连接（演示模式）' },
  { name: 'LLM 模型',        ok: true,                        value: sys.value.llm_model || 'qwen-plus' },
  { name: '查询判别模型',    ok: true,                        value: sys.value.query_classifier_model || 'bert_query_classifier_new' },
  { name: '策略分类模型',    ok: true,                        value: sys.value.strategy_classifier_model || 'bert_strategy_classifier' },
  { name: 'Embedding 模型',  ok: true,                        value: sys.value.embedding_model || 'BGE-M3' },
  { name: 'Reranker 模型',   ok: true,                        value: sys.value.reranker_model || 'BGE-Reranker-Large' },
  { name: '知识集合',        ok: true,                        value: sys.value.collection || 'edurag_final' },
  { name: '切块参数',        ok: true,                        value: sys.value.chunk_size || '1200/300' },
])

async function fetchOverview() {
  const [statusRes, filesRes] = await Promise.all([
    knowledgeAPI.status(),
    datasetAPI.listFiles(''),
  ])
  raw.value = statusRes.data
  rawFiles.value = filesRes?.data?.files || []
}

onMounted(async () => {
  try {
    await fetchOverview()
  } finally {
    loading.value = false
  }
})

function handleKnowledgeRefresh() {
  loading.value = true
  fetchOverview()
    .finally(() => {
      loading.value = false
    })
}

function viewRawFile(file) {
  const url = file.file_id
    ? datasetAPI.downloadFileUrl(file.file_id)
    : datasetAPI.downloadLegacyFileUrl(file.name, file.source)
  window.open(url, '_blank')
}

async function deleteRawFile(file) {
  if (!file.file_id) {
    ElMessage.warning('该文件是历史数据，缺少文件标识，暂不支持删除')
    return
  }

  try {
    await ElMessageBox.confirm(`确定删除文件“${file.name}”及其向量数据吗？`, '删除确认', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await datasetAPI.deleteFile(file.file_id)
    ElMessage.success('删除成功')
    handleKnowledgeRefresh()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      ElMessage.error(err?.response?.data?.detail || '删除失败')
    }
  }
}

onMounted(() => {
  window.addEventListener('rag-knowledge-updated', handleKnowledgeRefresh)
})

onBeforeUnmount(() => {
  window.removeEventListener('rag-knowledge-updated', handleKnowledgeRefresh)
})
</script>

<style scoped>
.page {
  height: calc(100vh - 60px);
  overflow-y: auto;
  background:
    radial-gradient(circle at 10% 15%, rgba(14, 165, 233, .12), transparent 34%),
    radial-gradient(circle at 86% 82%, rgba(16, 185, 129, .12), transparent 40%),
    linear-gradient(145deg, #f8fafc 0%, #eef2ff 48%, #ecfeff 100%);
  animation: kbBgShift 14s ease-in-out infinite alternate;
}
.page-inner  { max-width: 1120px; margin: 0 auto; padding: 28px 24px; }
.page-title  {
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
.hero-desc { font-size: 13px; line-height: 1.7; color: rgba(255,255,255,.78); max-width: 48em; }
.hero-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; align-self: center; }
.hero-metric {
  background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.16);
  border-radius: 14px; padding: 14px 16px;
}
.metric-name { display: block; font-size: 12px; color: rgba(255,255,255,.68); margin-bottom: 6px; }
.metric-value { font-size: 22px; font-weight: 800; }

/* 统计卡片 */
.stat-cards {
  display: grid; grid-template-columns: repeat(5, 1fr);
  gap: 16px; margin-bottom: 20px;
}
.stat-card {
  background: #fff; border-radius: 12px; padding: 20px;
  display: flex; align-items: center; gap: 16px;
  box-shadow: 0 1px 4px rgba(0,0,0,.06);
  transition: transform .18s ease, box-shadow .18s ease;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(15, 23, 42, .10); }
.stat-icon   {
  width: 52px; height: 52px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
}
.stat-icon.blue   { background: #ecf5ff; color: #409eff; }
.stat-icon.green  { background: #f0f9eb; color: #67c23a; }
.stat-icon.orange { background: #fdf6ec; color: #e6a23c; }
.stat-icon.purple { background: #f3f0ff; color: #9254de; }
.stat-icon.teal   { background: #ecfeff; color: #06b6d4; }
.stat-num    { font-size: 20px; font-weight: 700; color: #303133; }
.stat-lbl    { font-size: 12px; color: #909399; margin-top: 2px; }

/* 各板块 */
.section-card { margin-bottom: 20px; border-radius: 16px; overflow: hidden; box-shadow: 0 16px 36px rgba(15,23,42,.06); }
.card-head    { display: flex; align-items: center; gap: 6px; font-size: 15px; font-weight: 600; color: #303133; }
.card-sub     { margin-left: auto; font-size: 12px; color: #909399; }
.section-card :deep(.el-card__header) { background: rgba(248,250,252,.95); }
.section-card :deep(.el-card__body) { padding: 22px; }

/* 来源分布 */
.source-rows  { display: flex; flex-direction: column; gap: 16px; }
.source-row   { display: flex; align-items: center; gap: 16px; }
.src-label    { width: 180px; font-size: 14px; color: #606266; flex-shrink: 0; }
.src-label small { display: block; font-size: 12px; color: #909399; margin-top: 2px; }
.src-bar      { flex: 1; }
.src-count    { width: 80px; text-align: right; font-size: 13px; color: #909399; }

.file-list    { display: flex; flex-direction: column; gap: 10px; }
.file-item    {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 14px 16px; border-radius: 14px; background: linear-gradient(180deg, #fff, #f8fafc);
  border: 1px solid rgba(148,163,184,.18); box-shadow: 0 10px 24px rgba(15,23,42,.05);
  transition: transform .18s ease, box-shadow .18s ease;
}
.file-item:hover { transform: translateY(-2px); box-shadow: 0 14px 28px rgba(15,23,42,.08); }
.file-main    { min-width: 0; }
.file-actions {
  display: flex; align-items: center; gap: 6px; flex-shrink: 0;
}
.file-name    {
  font-size: 13px; font-weight: 600; color: #303133;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.file-meta    { font-size: 12px; color: #909399; margin-top: 2px; }
.file-chunks  { font-size: 13px; font-weight: 700; color: #409eff; flex-shrink: 0; }
.empty-hint   { font-size: 12px; color: #909399; }

/* 系统状态 */
.status-grid  { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.status-item  {
  background: linear-gradient(180deg, #fff, #f8fafc); border-radius: 14px;
  padding: 14px 16px; text-align: center; border: 1px solid rgba(148,163,184,.18);
  box-shadow: 0 10px 24px rgba(15,23,42,.04);
}
.status-tag   { margin-bottom: 8px; }
.status-name  { font-size: 13px; color: #606266; font-weight: 500; margin-bottom: 4px; }
.status-val   { font-size: 12px; color: #909399; }

@keyframes kbBgShift {
  from { background-position: 0% 0%, 100% 100%, 0% 0%; }
  to { background-position: 9% 8%, 92% 74%, 0% 0%; }
}
</style>
