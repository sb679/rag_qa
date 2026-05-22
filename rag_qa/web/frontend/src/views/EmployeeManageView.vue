<template>
  <div class="page motion-ready">
    <div class="page-inner">
      <div class="page-head">
        <div>
          <div class="page-kicker">Access control</div>
          <div class="page-title-row">
            <div class="page-title">
              <el-icon size="20"><User /></el-icon>
              员工账号管理
            </div>
            <el-tag v-if="!isSupervisor" type="warning" size="small" effect="light">仅主管可访问</el-tag>
            <el-tag v-else type="success" size="small" effect="light">主管工作区</el-tag>
          </div>
          <div class="page-desc">主管可以在这里查看账号创建记录、维护员工昵称和密码，并追踪系统内的账号管理动作。</div>
        </div>
        <div class="page-head-badges" v-if="isSupervisor">
          <div class="page-badge-card">
            <span>员工总数</span>
            <strong>{{ employees.length }}</strong>
          </div>
          <div class="page-badge-card">
            <span>当前筛选</span>
            <strong>{{ filteredEmployees.length }}</strong>
          </div>
        </div>
      </div>

      <div v-if="!isSupervisor" class="no-permission">
        <el-icon size="48" color="#c0c4cc"><Lock /></el-icon>
        <p>您没有权限访问此页面</p>
        <p class="hint">仅主管可以管理员工账号</p>
      </div>

      <template v-else>
        <div class="hero-banner">
          <div>
            <div class="hero-kicker">仅主管可见</div>
            <div class="hero-title">员工账号与创建记录</div>
            <div class="hero-desc">这里展示账号创建、创建者与最近更新时间，方便追溯系统管理动作。</div>
          </div>
          <div class="hero-pills">
            <div class="hero-pill">
              <span class="pill-label">员工总数</span>
              <strong>{{ employees.length }}</strong>
              <small>当前可管理账号</small>
            </div>
            <div class="hero-pill">
              <span class="pill-label">当前显示</span>
              <strong>{{ filteredEmployees.length }}</strong>
              <small>受关键词筛选影响</small>
            </div>
            <div class="hero-pill">
              <span class="pill-label">最近创建者</span>
              <strong>{{ latestCreator }}</strong>
              <small>按最新列表首项显示</small>
            </div>
          </div>
        </div>

        <!-- 创建员工按钮 -->
        <div class="toolbar">
          <div class="toolbar-copy">
            <div class="toolbar-title">账号列表</div>
            <div class="toolbar-desc">支持按工号、昵称或创建者快速筛选，适合答辩演示和日常维护。</div>
          </div>
          <el-input v-model="searchKeyword" placeholder="搜索工号、昵称或创建者" clearable class="search-input" />
          <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">
            创建员工账号
          </el-button>
        </div>

        <div v-if="actionFeedback" class="action-feedback" :class="actionFeedback.tone">
          <div class="action-feedback-main">
            <el-icon class="action-feedback-icon" size="20"><component :is="actionFeedback.icon" /></el-icon>
            <div class="action-feedback-copy">
              <div class="action-feedback-title">{{ actionFeedback.title }}</div>
              <div class="action-feedback-desc">{{ actionFeedback.desc }}</div>
            </div>
          </div>
          <el-button text size="small" @click="clearActionFeedback">关闭</el-button>
        </div>

        <div v-if="loadError" class="status-card error-card">
          <div class="status-icon">
            <el-icon size="26"><Warning /></el-icon>
          </div>
          <div class="status-copy">
            <div class="status-title">员工列表暂时无法加载</div>
            <div class="status-desc">{{ loadError }}</div>
          </div>
          <el-button type="primary" plain :loading="loading" @click="loadEmployees">重新加载</el-button>
        </div>

        <!-- 员工列表 -->
        <el-table :data="filteredEmployees" stripe v-loading="loading" class="employee-table">
          <el-table-column prop="employee_id" label="工号" width="120" />
          <el-table-column prop="nickname" label="昵称" width="150" />
          <el-table-column prop="created_at" label="创建时间" width="180" :formatter="formatTime" />
          <el-table-column prop="created_by" label="创建者" width="120" />
          <el-table-column label="账号年龄" width="120">
            <template #default="{ row }">
              {{ ageLabel(row.created_at) }}
            </template>
          </el-table-column>
          <el-table-column label="操作" width="200" align="center">
            <template #default="{ row }">
              <el-button text type="primary" size="small" @click="editEmployee(row)">编辑</el-button>
              <el-button text type="danger" size="small" @click="deleteEmployee(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <!-- 创建/编辑对话框 -->
      <el-dialog
        v-model="showCreateDialog"
        :title="editingEmployee ? '编辑员工' : '创建员工账号'"
        width="400px"
      >
        <el-form ref="formRef" :model="form" :rules="rules" label-width="80px">
          <el-form-item label="工号" prop="employee_id">
            <el-input
              v-model="form.employee_id"
              placeholder="请输入工号"
              :disabled="!!editingEmployee"
            />
          </el-form-item>
          <el-form-item label="昵称" prop="nickname">
            <el-input v-model="form.nickname" placeholder="请输入昵称" />
          </el-form-item>
          <el-form-item label="密码" prop="password">
            <el-input
              v-model="form.password"
              type="password"
              placeholder="请输入密码"
              show-password
            />
          </el-form-item>
        </el-form>
        <template #footer>
          <el-button @click="showCreateDialog = false">取消</el-button>
          <el-button type="primary" @click="submitForm" :loading="submitting">
            {{ editingEmployee ? '更新' : '创建' }}
          </el-button>
        </template>
      </el-dialog>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, computed } from 'vue'
import { Plus, User, Lock, Warning, CircleCheck } from '@element-plus/icons-vue'
import { userAPI } from '@/api'
import { useStore } from '@/store'

const { isSupervisor } = useStore()
const loading = ref(false)
const loadError = ref('')
const actionFeedback = ref(null)
const submitting = ref(false)
const employees = ref([])
const searchKeyword = ref('')
const showCreateDialog = ref(false)
const editingEmployee = ref(null)
const formRef = ref(null)

const filteredEmployees = computed(() => {
  const keyword = searchKeyword.value.trim().toLowerCase()
  if (!keyword) return employees.value
  return employees.value.filter((item) => {
    return [item.employee_id, item.nickname, item.created_by]
      .filter(Boolean)
      .some((text) => String(text).toLowerCase().includes(keyword))
  })
})

const latestCreator = computed(() => {
  if (!employees.value.length) return '-'
  return employees.value[0]?.created_by || '-'
})

const form = ref({
  employee_id: '',
  nickname: '',
  password: '',
})

const rules = {
  employee_id: [{ required: true, message: '请输入工号', trigger: 'blur' }],
  nickname: [{ required: true, message: '请输入昵称', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

const formatTime = (row) => {
  if (!row.created_at) return '-'
  const date = new Date(row.created_at)
  return date.toLocaleString('zh-CN')
}

const ageLabel = (createdAt) => {
  if (!createdAt) return '-'
  const diffDays = Math.max(0, Math.floor((Date.now() - new Date(createdAt).getTime()) / (1000 * 60 * 60 * 24)))
  return diffDays === 0 ? '今天' : `${diffDays} 天`
}

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

async function loadEmployees() {
  if (!isSupervisor.value) return
  loading.value = true
  loadError.value = ''
  try {
    const res = await userAPI.listEmployees()
    employees.value = res.data || []
  } catch (err) {
    loadError.value = err?.response?.data?.detail || '员工账号列表获取失败，请检查后端服务后重试。'
  } finally {
    loading.value = false
  }
}

function editEmployee(row) {
  editingEmployee.value = row
  form.value = {
    employee_id: row.employee_id,
    nickname: row.nickname,
    password: '',
  }
  showCreateDialog.value = true
}

async function deleteEmployee(row) {
  try {
    await ElMessageBox.confirm(
      `确定删除员工 ${row.nickname} (${row.employee_id}) 吗？`,
      '提示',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' }
    )
    await userAPI.deleteEmployee(row.employee_id)
    setActionFeedback('success', '员工账号已删除', `员工 ${row.nickname}（${row.employee_id}）已删除，列表正在刷新。`)
    loadEmployees()
  } catch (err) {
    if (err !== 'cancel') {
      setActionFeedback('error', '删除员工失败', err.response?.data?.detail || '删除请求未成功完成，请稍后重试。')
    }
  }
}

async function submitForm() {
  if (!formRef.value) return
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  submitting.value = true
  clearActionFeedback()
  try {
    if (editingEmployee.value) {
      const updates = {}
      if (form.value.nickname) updates.nickname = form.value.nickname
      if (form.value.password) updates.password = form.value.password
      await userAPI.updateEmployee(form.value.employee_id, updates)
      setActionFeedback('success', '员工资料已更新', `员工 ${form.value.employee_id} 的资料已保存。`)
    } else {
      await userAPI.createEmployee(
        form.value.employee_id,
        form.value.password,
        form.value.nickname
      )
      setActionFeedback('success', '员工账号已创建', `员工 ${form.value.nickname}（${form.value.employee_id}）已创建。`)
    }
    showCreateDialog.value = false
    editingEmployee.value = null
    form.value = { employee_id: '', nickname: '', password: '' }
    loadEmployees()
  } catch (err) {
    setActionFeedback('error', editingEmployee.value ? '更新员工失败' : '创建员工失败', err.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadEmployees)
</script>

<style scoped>
.page {
  height: calc(100vh - 72px);
  overflow-y: auto;
  background:
    radial-gradient(circle at 8% 10%, rgba(124, 58, 237, .10), transparent 24%),
    radial-gradient(circle at 88% 82%, rgba(20, 184, 166, .10), transparent 28%),
    radial-gradient(circle at 76% 18%, rgba(249, 115, 22, .08), transparent 22%),
    linear-gradient(145deg, #f8fafc 0%, #eef2ff 52%, #ecfeff 100%);
}

.motion-ready .page-head,
.motion-ready .hero-banner,
.motion-ready .toolbar,
.motion-ready .employee-table,
.motion-ready .no-permission {
  opacity: 0;
  transform: translateY(18px);
  animation: employeeReveal .76s cubic-bezier(.22,1,.36,1) forwards;
}

.motion-ready .page-head { animation-delay: .04s; }
.motion-ready .no-permission { animation-delay: .12s; }
.motion-ready .hero-banner { animation-delay: .12s; }
.motion-ready .toolbar { animation-delay: .2s; }
.motion-ready .employee-table { animation-delay: .28s; }

.page-inner {
  max-width: 1160px;
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
  animation: employeeFloat 6.4s ease-in-out infinite;
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

.hero-banner {
  display: grid;
  grid-template-columns: 1.5fr 1fr;
  gap: 16px;
  padding: 24px 26px;
  border-radius: 28px;
  margin-bottom: 20px;
  background: linear-gradient(135deg, #111827, #7c3aed 58%, #0f766e);
  color: #fff;
  box-shadow: 0 24px 54px rgba(15, 23, 42, .16);
}

.hero-kicker { font-size: 12px; letter-spacing: .18em; text-transform: uppercase; opacity: .72; }
.hero-title {
  font-size: 30px;
  font-weight: 900;
  margin: 10px 0 8px;
  line-height: 1.08;
  letter-spacing: -.03em;
  max-width: 16ch;
}
.hero-desc { font-size: 13px; line-height: 1.8; color: rgba(255,255,255,.78); max-width: 52ch; }
.hero-pills { display: grid; gap: 10px; }

.hero-pill {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 16px;
  border-radius: 18px;
  background: rgba(255,255,255,.10);
  border: 1px solid rgba(255,255,255,.12);
  backdrop-filter: blur(10px);
  animation: employeeFloat 7s ease-in-out infinite;
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

.no-permission {
  text-align: center;
  padding: 60px 20px;
  margin-top: 12px;
  background: linear-gradient(180deg, #fff, #f8fafc);
  border-radius: 24px;
  border: 1px solid rgba(148,163,184,.18);
  box-shadow: 0 16px 36px rgba(15,23,42,.06);
}

.no-permission p { font-size: 14px; color: #606266; margin: 12px 0; }
.no-permission .hint { font-size: 12px; color: #909399; }

.toolbar {
  margin-bottom: 20px;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 320px) auto;
  gap: 12px;
  align-items: center;
  padding: 16px 18px;
  border-radius: 22px;
  background: rgba(255,255,255,.74);
  border: 1px solid rgba(148,163,184,.18);
  box-shadow: 0 16px 36px rgba(15,23,42,.06);
  backdrop-filter: blur(12px);
}

.toolbar-copy {
  min-width: 0;
}

.toolbar-title {
  font-size: 15px;
  font-weight: 800;
  color: #0f172a;
}

.toolbar-desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.7;
  color: #64748b;
}

.search-input { max-width: 320px; }

.employee-table {
  background: #fff;
  border-radius: 22px;
  overflow: hidden;
  box-shadow: 0 16px 36px rgba(15,23,42,.06);
  border: 1px solid rgba(148,163,184,.18);
}

.status-card {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 20px;
  padding: 22px 24px;
  border-radius: 24px;
  border: 1px solid rgba(148,163,184,.18);
  background: linear-gradient(180deg, rgba(255,255,255,.94), rgba(248,250,252,.94));
  box-shadow: 0 16px 36px rgba(15,23,42,.06);
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
  margin-bottom: 20px;
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

.employee-table :deep(.el-table__header-wrapper th) { background: #f8fafc; color: #334155; }
.employee-table :deep(.el-table__row:hover > td) { background: #f8fbff !important; }

@keyframes employeeReveal {
  from {
    opacity: 0;
    transform: translateY(18px) scale(.99);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes employeeFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}

@media (max-width: 980px) {
  .page-head,
  .toolbar {
    grid-template-columns: 1fr;
  }

  .page-title-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .page-head-badges {
    grid-template-columns: 1fr 1fr;
  }

  .hero-banner {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .page-inner {
    padding: 20px 14px 30px;
  }

  .page-head-badges {
    grid-template-columns: 1fr;
  }

  .action-feedback,
  .status-card {
    align-items: flex-start;
    flex-direction: column;
  }
}

@media (prefers-reduced-motion: reduce) {
  .motion-ready .page-head,
  .motion-ready .hero-banner,
  .motion-ready .toolbar,
  .motion-ready .employee-table,
  .motion-ready .no-permission,
  .page-badge-card,
  .hero-pill {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}
</style>
