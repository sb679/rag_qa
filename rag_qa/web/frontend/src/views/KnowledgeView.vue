<template>
  <div class="page motion-ready">
    <div class="page-inner">
      <div class="page-head">
        <div>
          <div class="page-kicker">Knowledge assets</div>
          <div class="page-title-row">
            <div class="page-title">
              <el-icon size="20"><DataBoard /></el-icon>
              知识库概览
            </div>
            <el-tag type="success" size="small" effect="light">真实统计</el-tag>
          </div>
          <div class="page-desc">这一页聚焦知识资产本身，区分索引状态、当前可见文件与历史残留，避免把所有数量混在一起解释。</div>
        </div>
      </div>

      <el-skeleton v-if="loading" animated>
        <template #template>
          <div class="knowledge-skeleton-stack">
            <el-skeleton-item variant="image" class="skeleton-hero" />
            <div class="skeleton-stat-grid skeleton-stat-grid-five">
              <el-skeleton-item v-for="item in 5" :key="item" variant="rect" class="skeleton-stat-card" />
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
          <div class="status-title">知识库概览暂时无法加载</div>
          <div class="status-desc">{{ loadError }}</div>
        </div>
        <el-button type="primary" plain @click="loadOverview">重新加载</el-button>
      </div>

      <template v-else>
          <div v-if="actionFeedback" class="action-feedback" :class="actionFeedback.tone">
            <div class="action-feedback-main">
              <el-icon class="action-feedback-icon" size="20"><component :is="actionFeedback.icon" /></el-icon>
              <div class="action-feedback-copy">
                <div class="action-feedback-title">{{ actionFeedback.title }}</div>
                <div class="action-feedback-desc">{{ actionFeedback.desc }}</div>
              </div>
            </div>
            <el-button text size="small" @click="clearActionFeedback">知道了</el-button>
          </div>

          <div class="hero-banner">
            <div class="hero-copy">
              <div class="hero-kicker">知识资产与来源分布</div>
              <div class="hero-title">Milvus 真实分块统计 + 文档来源结构</div>
              <div class="hero-desc">页面把 3 个口径显式拆开：索引文档数看 Milvus，现存文件数看当前存储，历史向量数看两者之间的差值。</div>
            </div>
            <div class="hero-metrics">
              <div class="hero-metric">
                <span class="metric-name">索引文档数</span>
                <span class="metric-value">{{ indexedDocumentCount.toLocaleString() }}</span>
                <small>Milvus 当前去重口径</small>
              </div>
              <div class="hero-metric">
                <span class="metric-name">{{ currentFileMetricLabel }}</span>
                <span class="metric-value">{{ currentFileCountDisplay }}</span>
                <small>按当前可见存储统计</small>
              </div>
              <div class="hero-metric">
                <span class="metric-name">{{ historicalVectorMetricLabel }}</span>
                <span class="metric-value">{{ historicalVectorCountDisplay }}</span>
                <small>用于识别历史残留</small>
              </div>
            </div>
          </div>

          <div class="stat-cards">
            <div class="stat-card">
              <div class="stat-icon blue"><el-icon size="28"><Document /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">{{ indexedDocumentCount.toLocaleString() }}</div>
                <div class="stat-lbl">索引文档数</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon green"><el-icon size="28"><Grid /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">{{ currentFileCountDisplay }}</div>
                <div class="stat-lbl">{{ currentFileMetricLabel }}</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon orange"><el-icon size="28"><Search /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">{{ currentVectorCountDisplay }}</div>
                <div class="stat-lbl">{{ currentVectorMetricLabel }}</div>
              </div>
            </div>
            <div class="stat-card">
              <div class="stat-icon purple"><el-icon size="28"><Rank /></el-icon></div>
              <div class="stat-body">
                <div class="stat-num">{{ historicalVectorCountDisplay }}</div>
                <div class="stat-lbl">{{ historicalVectorMetricLabel }}</div>
              </div>
            </div>
          </div>

          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="card-head">
                <el-icon><Grid /></el-icon>
                <span>统计口径说明</span>
                <span class="card-sub">把索引状态、当前文件状态、历史残留状态拆开看</span>
              </div>
            </template>
            <div class="scope-grid">
              <div class="scope-item">
                <div class="scope-title">索引文档数</div>
                <div class="scope-value">{{ indexedDocumentCount.toLocaleString() }}</div>
                <div class="scope-desc">Milvus 当前索引中按文档去重后的数量，包含历史残留条目。</div>
              </div>
              <div class="scope-item">
                <div class="scope-title">{{ currentFileMetricLabel }}</div>
                <div class="scope-value">{{ currentFileCountDisplay }}</div>
                <div class="scope-desc">{{ currentFileMetricDesc }}</div>
              </div>
              <div class="scope-item">
                <div class="scope-title">{{ historicalVectorMetricLabel }}</div>
                <div class="scope-value">{{ historicalVectorCountDisplay }}</div>
                <div class="scope-desc">{{ historicalVectorMetricDesc }}</div>
              </div>
            </div>
            <div v-if="!storageEnumerated" class="scope-warning">
              当前无法直接枚举真实存储，因此页面回退为“索引侧可见文件”口径：当前展示 {{ fallbackIndexedFileCount.toLocaleString() }} 个索引中文档，
              对应 {{ fallbackIndexedVectorCount.toLocaleString() }} 条索引向量。历史残留向量仍无法仅凭这一口径准确判定。
            </div>
          </el-card>

          <el-card v-if="isSupervisor" class="section-card" shadow="never">
            <template #header>
              <div class="card-head action-head">
                <div class="action-title-wrap">
                  <el-icon><Operation /></el-icon>
                  <span>历史残留清理</span>
                </div>
                <div class="action-toolbar">
                  <el-button :loading="residualLoading" @click="openResidualPreview">预览残留</el-button>
                  <el-button
                    type="danger"
                    :loading="residualCleaning"
                    :disabled="!residualItems.length"
                    @click="confirmResidualCleanup"
                  >
                    确认清理
                  </el-button>
                </div>
              </div>
            </template>
            <div class="cleanup-grid">
              <div class="cleanup-item">
                <div class="cleanup-label">残留文档数</div>
                <div class="cleanup-value">{{ residualSummary.residual_document_count?.toLocaleString?.() ?? '—' }}</div>
                <div class="cleanup-desc">索引里还存在、但当前存储里已经找不到的历史文档数。</div>
              </div>
              <div class="cleanup-item">
                <div class="cleanup-label">残留向量数</div>
                <div class="cleanup-value">{{ residualSummary.residual_vector_count?.toLocaleString?.() ?? '—' }}</div>
                <div class="cleanup-desc">这些历史文档仍占用的 Milvus 向量数。</div>
              </div>
              <div class="cleanup-item">
                <div class="cleanup-label">处理策略</div>
                <div class="cleanup-value cleanup-text">先预览，后确认</div>
                <div class="cleanup-desc">默认先 dry-run 预览，再经过一次删除确认后才会实际清理。</div>
              </div>
            </div>
            <div class="cleanup-note">当前清理能力会优先按 file_id 删除；缺少 file_id 的历史条目会自动按 source + file_name 兜底删除。</div>
          </el-card>

          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="card-head">
                <el-icon><Folder /></el-icon>
                <span>数据来源分布</span>
                <span class="card-sub">总计 {{ indexedVectorCount.toLocaleString() }} 个分块，当前识别 {{ sourceRows.length }} 类来源</span>
                <el-button text size="small" type="primary" @click="sourceSectionExpanded = !sourceSectionExpanded">
                  {{ sourceSectionExpanded ? '收起' : '展开' }}
                </el-button>
              </div>
            </template>
            <div v-if="sourceSectionExpanded">
              <div class="source-toolbar">
                <div class="source-tip">
                  以 Milvus 中的 source 字段统计。像 tmp... 这类来源会被归并为“临时导入来源”，通常意味着历史临时入库或残留索引。
                </div>
                <el-input
                  v-model="sourceSearchKeyword"
                  clearable
                  size="small"
                  class="section-search"
                  placeholder="搜索来源名称"
                />
              </div>
              <div v-if="filteredSourceRows.length" class="source-rows scrollable-panel">
                <div v-for="(src, i) in filteredSourceRows" :key="src.name" class="source-row">
                  <div class="src-label">
                    <div class="src-title-row">
                      <span>{{ src.name }}</span>
                      <el-tag v-if="src.isResidual" size="small" type="warning" effect="light">临时来源</el-tag>
                    </div>
                    <small>{{ Math.round((src.ratio || 0) * 100) }}% 占比</small>
                    <small v-if="src.groupCount > 1">合并了 {{ src.groupCount }} 个临时 source</small>
                  </div>
                  <el-progress
                    :percentage="Math.round((src.ratio || (src.chunks / Math.max(indexedVectorCount, 1))) * 100)"
                    :stroke-width="12"
                    :color="progressColors[i % progressColors.length]"
                    class="src-bar"
                  />
                  <div class="src-count">{{ src.chunks.toLocaleString() }} 块</div>
                </div>
              </div>
              <div v-else class="empty-hint">没有匹配到来源名称</div>
            </div>
          </el-card>

          <el-card class="section-card" shadow="never">
            <template #header>
              <div class="card-head">
                <el-icon><Document /></el-icon>
                <span>知识文件清单</span>
                <span class="card-sub">共 {{ currentFileCountDisplay }} 个{{ storageEnumerated ? '当前存储可见文件' : '索引侧可见文件' }}</span>
                <el-button text size="small" type="primary" @click="fileSectionExpanded = !fileSectionExpanded">
                  {{ fileSectionExpanded ? '收起' : '展开' }}
                </el-button>
              </div>
            </template>
            <div v-if="fileSectionExpanded">
              <div class="file-toolbar">
                <div class="source-tip">支持按文件名或来源搜索；列表内部可滚动查看。</div>
                <el-input
                  v-model="fileSearchKeyword"
                  clearable
                  size="small"
                  class="section-search"
                  placeholder="搜索文件名或来源"
                />
              </div>
              <div v-if="filteredRawFiles.length" class="file-list scrollable-panel">
                <div v-for="(file, i) in filteredRawFiles" :key="`${file.file_id || file.name}-${i}`" class="file-item">
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
              <div v-else class="empty-hint">{{ rawFiles.length ? '没有匹配到文件' : '暂无原始上传文件' }}</div>
            </div>
          </el-card>

      </template>
    </div>

    <el-dialog
      v-model="residualDialogVisible"
      title="历史残留预览"
      width="920px"
      destroy-on-close
    >
      <div class="residual-toolbar">
        <el-select v-model="residualSourceFilter" clearable filterable placeholder="按来源筛选" class="residual-filter">
          <el-option v-for="item in residualSourceOptions" :key="item" :label="item" :value="item" />
        </el-select>
        <div class="residual-toolbar-actions">
          <el-button size="small" @click="selectAllFilteredResiduals">全选当前筛选</el-button>
          <el-button size="small" @click="clearResidualSelection">清空选择</el-button>
          <span class="residual-selection-tip">已选 {{ selectedResidualCount }} 项</span>
        </div>
      </div>

      <div class="residual-summary-row">
        <div class="residual-summary-box">
          <div class="cleanup-label">残留文档</div>
          <div class="cleanup-value">{{ filteredResidualItems.length.toLocaleString() }}</div>
        </div>
        <div class="residual-summary-box">
          <div class="cleanup-label">残留向量</div>
          <div class="cleanup-value">{{ filteredResidualVectorCount.toLocaleString() }}</div>
        </div>
        <div class="residual-summary-box">
          <div class="cleanup-label">当前返回条数</div>
          <div class="cleanup-value">{{ residualSummary.returned_count?.toLocaleString?.() ?? residualItems.length }}</div>
        </div>
      </div>

      <el-table
        ref="residualTableRef"
        :data="filteredResidualItems"
        stripe
        max-height="420"
        row-key="_residual_key"
        @selection-change="handleResidualSelectionChange"
      >
        <el-table-column type="selection" width="52" reserve-selection />
        <el-table-column prop="source" label="来源" min-width="120" />
        <el-table-column prop="name" label="文档名" min-width="300" show-overflow-tooltip />
        <el-table-column prop="chunks" label="向量数" min-width="100">
          <template #default="scope">
            {{ Number(scope.row.chunks || 0).toLocaleString() }}
          </template>
        </el-table-column>
        <el-table-column prop="delete_mode" label="删除方式" min-width="120">
          <template #default="scope">
            <el-tag size="small" effect="light" :type="scope.row.delete_mode === 'file_id' ? 'success' : 'warning'">
              {{ scope.row.delete_mode === 'file_id' ? 'file_id' : 'source+name' }}
            </el-tag>
          </template>
        </el-table-column>
      </el-table>

      <template #footer>
        <div class="dialog-actions">
          <el-button @click="residualDialogVisible = false">关闭</el-button>
          <el-button type="danger" :disabled="!selectedResidualCount" :loading="residualCleaning" @click="confirmResidualCleanup">
            删除选中项
          </el-button>
        </div>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { DataBoard, Document, Grid, Search, Rank, Folder, Operation, Monitor, CircleCheck, Warning } from '@element-plus/icons-vue'
import { knowledgeAPI, datasetAPI } from '@/api'
import { useStore } from '@/store'

const loading = ref(true)
const loadError = ref('')
const raw = ref({ system: {}, knowledge: { total_chunks: 0, total_books: 0, indexed_vector_count: 0, indexed_document_count: 0, sources: [], files: [] } })
const rawFiles = ref([])
const fileSummary = ref({ storage_enumerated: false, current_file_count: null, current_vector_count: null })
const sourceSectionExpanded = ref(false)
const fileSectionExpanded = ref(false)
const sourceSearchKeyword = ref('')
const fileSearchKeyword = ref('')
const residualDialogVisible = ref(false)
const residualLoading = ref(false)
const residualCleaning = ref(false)
const residualItems = ref([])
const residualSummary = ref({ residual_document_count: null, residual_vector_count: null, returned_count: 0 })
const residualTableRef = ref(null)
const residualSourceFilter = ref('')
const selectedResidualKeys = ref([])
const actionFeedback = ref(null)

const { isSupervisor } = useStore()

const stats = computed(() => raw.value.knowledge || {})
const sys = computed(() => raw.value.system || {})
const indexedDocumentCount = computed(() => Number(stats.value.indexed_document_count ?? stats.value.total_books ?? 0))
const indexedVectorCount = computed(() => Number(stats.value.indexed_vector_count ?? stats.value.total_chunks ?? sys.value.total_vectors ?? 0))
const storageEnumerated = computed(() => !!fileSummary.value.storage_enumerated)
const fallbackIndexedFileCount = computed(() => rawFiles.value.length)
const fallbackIndexedVectorCount = computed(() => rawFiles.value.reduce((sum, file) => sum + Number(file.chunks || 0), 0))
const currentFileCount = computed(() => storageEnumerated.value ? Number(fileSummary.value.current_file_count ?? rawFiles.value.length ?? 0) : null)
const currentVectorCount = computed(() => storageEnumerated.value ? Number(fileSummary.value.current_vector_count ?? 0) : null)
const historicalVectorCount = computed(() => {
  if (!storageEnumerated.value || currentVectorCount.value == null) return null
  return Math.max(indexedVectorCount.value - currentVectorCount.value, 0)
})
const currentFileCountDisplay = computed(() => {
  if (storageEnumerated.value) return currentFileCount.value == null ? '—' : currentFileCount.value.toLocaleString()
  return fallbackIndexedFileCount.value.toLocaleString()
})
const currentVectorCountDisplay = computed(() => {
  if (storageEnumerated.value) return currentVectorCount.value == null ? '—' : currentVectorCount.value.toLocaleString()
  return fallbackIndexedVectorCount.value.toLocaleString()
})
const historicalVectorCountDisplay = computed(() => historicalVectorCount.value == null ? '—' : historicalVectorCount.value.toLocaleString())
const currentFileMetricLabel = computed(() => storageEnumerated.value ? '现存文件数' : '索引侧文件数')
const currentVectorMetricLabel = computed(() => storageEnumerated.value ? '当前文件对应向量' : '索引侧可见向量')
const historicalVectorMetricLabel = computed(() => storageEnumerated.value ? '历史残留向量' : '历史向量数')
const currentFileMetricDesc = computed(() => storageEnumerated.value
  ? '当前存储目录里实际还能看到的原始文件数量。'
  : '对象存储未完成枚举时，退化显示索引中仍可识别到的文档数，不等同于真实现存文件数。')
const historicalVectorMetricDesc = computed(() => storageEnumerated.value
  ? '全库向量减去当前文件对应向量后的差值，用于识别历史残留索引。'
  : '要准确计算历史残留向量，必须先拿到真实存储文件清单；当前仅能展示索引侧统计。')
const sourceRows = computed(() => {
  const grouped = []
  const tempGroup = {
    name: '临时导入来源（历史残留）',
    chunks: 0,
    ratio: 0,
    isResidual: true,
    groupCount: 0,
  }
  for (const item of stats.value.sources || []) {
    const name = String(item.name || 'unknown')
    if (/^tmp[a-z0-9]+_/i.test(name)) {
      tempGroup.chunks += Number(item.chunks || 0)
      tempGroup.ratio += Number(item.ratio || 0)
      tempGroup.groupCount += 1
      continue
    }
    grouped.push({
      name,
      chunks: Number(item.chunks || 0),
      ratio: Number(item.ratio || 0),
      isResidual: false,
      groupCount: 1,
    })
  }
  if (tempGroup.groupCount > 0) grouped.push(tempGroup)
  return grouped.sort((a, b) => b.chunks - a.chunks)
})
const filteredSourceRows = computed(() => {
  const keyword = sourceSearchKeyword.value.trim().toLowerCase()
  if (!keyword) return sourceRows.value
  return sourceRows.value.filter((item) => String(item.name || '').toLowerCase().includes(keyword))
})
const filteredRawFiles = computed(() => {
  const keyword = fileSearchKeyword.value.trim().toLowerCase()
  if (!keyword) return rawFiles.value
  return rawFiles.value.filter((item) => {
    const name = String(item?.name || '').toLowerCase()
    const source = String(item?.source || '').toLowerCase()
    return name.includes(keyword) || source.includes(keyword)
  })
})
const residualSourceOptions = computed(() => Array.from(new Set(residualItems.value.map((item) => item.source).filter(Boolean))))
const filteredResidualItems = computed(() => {
  if (!residualSourceFilter.value) return residualItems.value
  return residualItems.value.filter((item) => item.source === residualSourceFilter.value)
})
const selectedResidualItems = computed(() => {
  const keySet = new Set(selectedResidualKeys.value)
  return residualItems.value.filter((item) => keySet.has(item._residual_key))
})
const selectedResidualCount = computed(() => selectedResidualItems.value.length)
const filteredResidualVectorCount = computed(() => filteredResidualItems.value.reduce((sum, item) => sum + Number(item.chunks || 0), 0))

const progressColors = ['#409eff', '#67c23a', '#f0a020']

function setActionFeedback(tone, title, desc) {
  actionFeedback.value = {
    tone,
    title,
    desc,
    icon: tone === 'success' ? CircleCheck : Warning,
  }
}

function clearActionFeedback() {
  actionFeedback.value = null
}

async function fetchOverview() {
  const [statusRes, filesRes] = await Promise.all([
    knowledgeAPI.status(),
    datasetAPI.listFiles(''),
  ])
  raw.value = statusRes.data || { system: {}, knowledge: {} }
  rawFiles.value = filesRes?.data?.files || []
  fileSummary.value = filesRes?.data?.summary || { storage_enumerated: false, current_file_count: null, current_vector_count: null }
  sourceSearchKeyword.value = ''
  fileSearchKeyword.value = ''
}

async function loadOverview() {
  loading.value = true
  loadError.value = ''
  try {
    await fetchOverview()
  } catch (err) {
    loadError.value = err?.response?.data?.detail || '暂时无法获取知识库统计或文件清单，请检查后端服务后重试。'
  } finally {
    loading.value = false
  }
}

function handleKnowledgeRefresh() {
  loading.value = true
  loadOverview()
}

async function loadResidualPreview() {
  residualLoading.value = true
  try {
    const res = await datasetAPI.listResiduals({ limit: 200 })
    residualItems.value = (res?.data?.items || []).map((item) => ({
      ...item,
      _residual_key: [item.file_id || '', item.source || '', item.name || ''].join('::'),
    }))
    residualSummary.value = res?.data?.summary || { residual_document_count: 0, residual_vector_count: 0, returned_count: 0 }
    residualSourceFilter.value = ''
    selectedResidualKeys.value = residualItems.value.map((item) => item._residual_key)
  } finally {
    residualLoading.value = false
  }
}

async function openResidualPreview() {
  try {
    await loadResidualPreview()
    residualDialogVisible.value = true
    await nextTick()
    selectAllFilteredResiduals()
    setActionFeedback(
      'success',
      '残留预览已刷新',
      `当前返回 ${residualItems.value.length.toLocaleString()} 条候选残留，可继续筛选后再执行清理。`,
    )
  } catch (err) {
    setActionFeedback('error', '残留预览失败', err?.response?.data?.detail || '暂时无法拉取残留预览，请稍后重试。')
  }
}

function handleResidualSelectionChange(rows) {
  selectedResidualKeys.value = (rows || []).map((item) => item._residual_key)
}

async function selectAllFilteredResiduals() {
  await nextTick()
  const table = residualTableRef.value
  if (!table) return
  table.clearSelection()
  filteredResidualItems.value.forEach((item) => table.toggleRowSelection(item, true))
  selectedResidualKeys.value = filteredResidualItems.value.map((item) => item._residual_key)
}

function clearResidualSelection() {
  residualTableRef.value?.clearSelection()
  selectedResidualKeys.value = []
}

async function confirmResidualCleanup() {
  if (!selectedResidualCount.value) {
    ElMessage.warning('请先选择要清理的残留项')
    return
  }

  try {
    await ElMessageBox.confirm(
      `确定删除这 ${selectedResidualCount.value} 个历史残留文档及其向量吗？该操作不可撤销。`,
      '清理确认',
      {
        type: 'warning',
        confirmButtonText: '确认删除',
        cancelButtonText: '取消',
      },
    )

    residualCleaning.value = true
    const res = await datasetAPI.cleanupResiduals({
      dry_run: false,
      confirm: true,
      items: selectedResidualItems.value.map((item) => ({
        file_id: item.file_id || '',
        source: item.source || '',
        name: item.name || '',
      })),
    })
    const deletedVectorCount = Number(res?.data?.summary?.deleted_vector_count || 0)
    const deletedDocumentCount = Number(res?.data?.summary?.deleted_document_count || 0)
    setActionFeedback(
      'success',
      '历史残留清理完成',
      `已清理 ${deletedDocumentCount.toLocaleString()} 个残留文档，并删除 ${deletedVectorCount.toLocaleString()} 条向量。`,
    )
    residualDialogVisible.value = false
    residualItems.value = []
    residualSummary.value = { residual_document_count: 0, residual_vector_count: 0, returned_count: 0 }
    handleKnowledgeRefresh()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      setActionFeedback('error', '历史残留清理失败', err?.response?.data?.detail || '清理请求未成功完成，请检查后端服务。')
    }
  } finally {
    residualCleaning.value = false
  }
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
    setActionFeedback('success', '文件删除完成', `文件“${file.name}”及其关联向量已删除，页面统计正在刷新。`)
    handleKnowledgeRefresh()
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      setActionFeedback('error', '文件删除失败', err?.response?.data?.detail || `文件“${file.name}”删除失败，请稍后重试。`)
    }
  }
}

onMounted(() => {
  loadOverview()
  window.addEventListener('rag-knowledge-updated', handleKnowledgeRefresh)
})

onBeforeUnmount(() => {
  window.removeEventListener('rag-knowledge-updated', handleKnowledgeRefresh)
})
</script>

<style scoped>
.page {
  height: calc(100vh - 72px);
  overflow-y: auto;
  background:
    radial-gradient(circle at 10% 15%, rgba(14, 165, 233, .12), transparent 26%),
    radial-gradient(circle at 86% 82%, rgba(16, 185, 129, .12), transparent 28%),
    radial-gradient(circle at 78% 18%, rgba(249, 115, 22, .08), transparent 22%),
    linear-gradient(145deg, #f8fafc 0%, #eef2ff 48%, #ecfeff 100%);
  animation: kbBgShift 14s ease-in-out infinite alternate;
}

.motion-ready .page-head,
.motion-ready .hero-banner,
.motion-ready .stat-card,
.motion-ready .section-card {
  opacity: 0;
  transform: translateY(18px);
  animation: pageReveal .76s cubic-bezier(.22,1,.36,1) forwards;
}

.motion-ready .page-head { animation-delay: .04s; }
.motion-ready .hero-banner { animation-delay: .12s; }
.motion-ready .stat-card:nth-child(1) { animation-delay: .18s; }
.motion-ready .stat-card:nth-child(2) { animation-delay: .24s; }
.motion-ready .stat-card:nth-child(3) { animation-delay: .3s; }
.motion-ready .stat-card:nth-child(4) { animation-delay: .36s; }
.motion-ready .stat-card:nth-child(5) { animation-delay: .42s; }
.motion-ready .section-card:nth-of-type(1) { animation-delay: .48s; }
.motion-ready .section-card:nth-of-type(2) { animation-delay: .56s; }
.motion-ready .section-card:nth-of-type(3) { animation-delay: .64s; }
.motion-ready .section-card:nth-of-type(4) { animation-delay: .72s; }

.page-inner { max-width: 1180px; margin: 0 auto; padding: 28px 24px 36px; }
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
.knowledge-skeleton-stack {
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

.skeleton-stat-grid-five {
  grid-template-columns: repeat(5, minmax(0, 1fr));
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

.action-feedback {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 18px;
  padding: 16px 18px;
  border-radius: 20px;
  border: 1px solid rgba(148,163,184,.18);
  box-shadow: 0 14px 28px rgba(15,23,42,.05);
}

.action-feedback.success {
  background: linear-gradient(180deg, rgba(240,253,244,.96), rgba(255,255,255,.96));
  border-color: rgba(34,197,94,.18);
}

.action-feedback.error {
  background: linear-gradient(180deg, rgba(254,242,242,.96), rgba(255,255,255,.96));
  border-color: rgba(239,68,68,.18);
}

.action-feedback-main {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  min-width: 0;
}

.action-feedback-icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.action-feedback.success .action-feedback-icon {
  color: #16a34a;
}

.action-feedback.error .action-feedback-icon {
  color: #dc2626;
}

.action-feedback-copy {
  min-width: 0;
}

.action-feedback-title {
  font-size: 14px;
  font-weight: 800;
  color: #0f172a;
}

.action-feedback-desc {
  margin-top: 4px;
  font-size: 12px;
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
.hero-title { font-size: 30px; font-weight: 900; margin: 10px 0 8px; line-height: 1.08; letter-spacing: -.03em; max-width: 16ch; }
.hero-desc { font-size: 13px; line-height: 1.7; color: rgba(255,255,255,.78); max-width: 48em; }
.hero-metrics { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; align-self: center; }
.hero-metric {
  background: rgba(255,255,255,.12); border: 1px solid rgba(255,255,255,.16);
  border-radius: 18px; padding: 14px 16px;
  backdrop-filter: blur(10px);
  animation: metricFloat 7s ease-in-out infinite;
}
.hero-metric:nth-child(2) { animation-delay: .8s; }
.hero-metric:nth-child(3) { animation-delay: 1.6s; }
.metric-name { display: block; font-size: 12px; color: rgba(255,255,255,.68); margin-bottom: 6px; }
.metric-value { font-size: 22px; font-weight: 800; }
.hero-metric small {
  display: block;
  margin-top: 8px;
  font-size: 11px;
  color: rgba(255,255,255,.72);
}

.stat-cards {
  display: grid; grid-template-columns: repeat(5, 1fr);
  gap: 16px; margin-bottom: 20px;
}
.stat-card {
  background: linear-gradient(180deg, rgba(255,255,255,.92), rgba(248,250,252,.92)); border-radius: 22px; padding: 22px;
  display: flex; align-items: center; gap: 16px;
  box-shadow: 0 18px 34px rgba(15,23,42,.06);
  transition: transform .18s ease, box-shadow .18s ease;
  border: 1px solid rgba(148,163,184,.16);
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 8px 22px rgba(15, 23, 42, .10); }
.stat-icon {
  width: 52px; height: 52px; border-radius: 12px;
  display: flex; align-items: center; justify-content: center;
}
.stat-icon.blue { background: #ecf5ff; color: #409eff; }
.stat-icon.green { background: #f0f9eb; color: #67c23a; }
.stat-icon.orange { background: #fdf6ec; color: #e6a23c; }
.stat-icon.purple { background: #f3f0ff; color: #9254de; }
.stat-icon.teal { background: #ecfeff; color: #06b6d4; }
.stat-num { font-size: 20px; font-weight: 700; color: #303133; }
.stat-lbl { font-size: 12px; color: #909399; margin-top: 2px; }

.section-card { margin-bottom: 20px; border-radius: 22px; overflow: hidden; box-shadow: 0 18px 36px rgba(15,23,42,.06); }
.card-head { display: flex; align-items: center; gap: 6px; font-size: 15px; font-weight: 700; color: #0f172a; }
.card-sub { margin-left: auto; font-size: 12px; color: #909399; }
.action-head { justify-content: space-between; }
.action-title-wrap { display: flex; align-items: center; gap: 6px; }
.action-toolbar { display: flex; align-items: center; gap: 8px; }
.section-card :deep(.el-card__header) { background: rgba(248,250,252,.95); }
.section-card :deep(.el-card__body) { padding: 22px; }

.scope-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.scope-item {
  border: 1px solid rgba(148,163,184,.18);
  border-radius: 18px;
  padding: 16px 18px;
  background: linear-gradient(180deg, #fff, #f8fafc);
  box-shadow: 0 10px 24px rgba(15,23,42,.04);
}
.scope-title { font-size: 13px; color: #606266; font-weight: 700; }
.scope-value { font-size: 22px; font-weight: 800; color: #111827; margin: 8px 0; }
.scope-desc { font-size: 12px; color: #6b7280; line-height: 1.7; }
.scope-warning {
  margin-top: 14px;
  font-size: 12px;
  color: #b45309;
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-radius: 12px;
  padding: 10px 12px;
}

.cleanup-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
}
.cleanup-item {
  border: 1px solid rgba(148,163,184,.18);
  border-radius: 18px;
  padding: 16px 18px;
  background: linear-gradient(180deg, #fff, #fff7ed);
  box-shadow: 0 10px 24px rgba(15,23,42,.04);
}
.cleanup-label { font-size: 13px; color: #606266; font-weight: 700; }
.cleanup-value { font-size: 22px; font-weight: 800; color: #111827; margin: 8px 0; }
.cleanup-text { font-size: 18px; }
.cleanup-desc { font-size: 12px; color: #6b7280; line-height: 1.7; }
.cleanup-note {
  margin-top: 14px;
  font-size: 12px;
  color: #7c2d12;
  background: #fff7ed;
  border: 1px solid #fdba74;
  border-radius: 12px;
  padding: 10px 12px;
}

.residual-summary-row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  margin-bottom: 16px;
}
.residual-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 16px;
}
.residual-filter {
  width: 220px;
}
.residual-toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.residual-selection-tip {
  font-size: 12px;
  color: #6b7280;
}
.residual-summary-box {
  border-radius: 18px;
  padding: 14px 16px;
  background: linear-gradient(180deg, #fff, #f8fafc);
  border: 1px solid rgba(148,163,184,.18);
  box-shadow: 0 10px 24px rgba(15,23,42,.04);
}
.dialog-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.source-rows { display: flex; flex-direction: column; gap: 16px; }
.source-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.file-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}
.section-search {
  width: min(280px, 100%);
  flex-shrink: 0;
}
.scrollable-panel {
  max-height: 360px;
  overflow-y: auto;
  padding-right: 4px;
}
.source-tip {
  font-size: 12px;
  color: #6b7280;
  line-height: 1.7;
  max-width: 720px;
}
.source-row { display: flex; align-items: center; gap: 16px; }
.src-label { width: 180px; font-size: 14px; color: #606266; flex-shrink: 0; }
.src-title-row { display: flex; align-items: center; gap: 8px; }
.src-label small { display: block; font-size: 12px; color: #909399; margin-top: 2px; }
.src-bar { flex: 1; }
.src-count { width: 80px; text-align: right; font-size: 13px; color: #909399; }

.file-list { display: flex; flex-direction: column; gap: 10px; }
.file-item {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 16px 18px; border-radius: 18px; background: linear-gradient(180deg, #fff, #f8fafc);
  border: 1px solid rgba(148,163,184,.18); box-shadow: 0 10px 24px rgba(15,23,42,.05);
  transition: transform .18s ease, box-shadow .18s ease;
}
.file-item:hover { transform: translateY(-2px); box-shadow: 0 14px 28px rgba(15,23,42,.08); }
.scope-item,
.cleanup-item,
.residual-summary-box,
.status-item,
.source-row,
.file-item {
  transition: transform .18s ease, box-shadow .18s ease;
}

.scope-item:hover,
.cleanup-item:hover,
.residual-summary-box:hover,
.status-item:hover,
.source-row:hover,
.file-item:hover {
  transform: translateY(-2px);
  box-shadow: 0 14px 28px rgba(15,23,42,.08);
}

@keyframes pageReveal {
  from {
    opacity: 0;
    transform: translateY(18px) scale(.99);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes metricFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}
.file-main { min-width: 0; }
.file-actions { display: flex; align-items: center; gap: 6px; flex-shrink: 0; }
.file-name {
  font-size: 13px; font-weight: 600; color: #303133;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.file-meta { font-size: 12px; color: #909399; margin-top: 2px; }
.file-chunks { font-size: 13px; font-weight: 700; color: #409eff; flex-shrink: 0; }
.empty-hint { font-size: 12px; color: #909399; }

.status-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.status-item {
  background: linear-gradient(180deg, #fff, #f8fafc); border-radius: 14px;
  padding: 14px 16px; text-align: center; border: 1px solid rgba(148,163,184,.18);
  box-shadow: 0 10px 24px rgba(15,23,42,.04);
}
.status-tag { margin-bottom: 8px; }
.status-name { font-size: 13px; color: #606266; font-weight: 500; margin-bottom: 4px; }
.status-val { font-size: 12px; color: #909399; }

@media (max-width: 960px) {
  .page-head,
  .cleanup-grid,
  .residual-summary-row,
  .scope-grid,
  .status-grid,
  .stat-cards,
  .hero-banner {
    grid-template-columns: 1fr;
  }
  .skeleton-stat-grid,
  .skeleton-stat-grid-five {
    grid-template-columns: 1fr;
  }
  .page-title-row {
    align-items: flex-start;
    flex-direction: column;
  }
  .action-feedback {
    align-items: flex-start;
    flex-direction: column;
  }
  .status-card {
    align-items: flex-start;
    flex-direction: column;
  }
  .residual-toolbar {
    flex-direction: column;
    align-items: stretch;
  }
  .source-toolbar,
  .file-toolbar,
  .source-row {
    flex-direction: column;
    align-items: stretch;
  }
  .section-search {
    width: 100%;
  }
  .src-label,
  .src-count {
    width: auto;
    text-align: left;
  }
  .action-head {
    align-items: flex-start;
    flex-direction: column;
  }
}

@keyframes kbBgShift {
  from { background-position: 0% 0%, 100% 100%, 0% 0%; }
  to { background-position: 9% 8%, 92% 74%, 0% 0%; }
}

@media (prefers-reduced-motion: reduce) {
  .motion-ready .page-head,
  .motion-ready .hero-banner,
  .motion-ready .stat-card,
  .motion-ready .section-card,
  .hero-metric {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}
</style>
