<template>
  <div class="page">
    <div class="page-inner">
      <div class="page-title">
        <el-icon size="20"><User /></el-icon>
        员工账号管理
        <el-tag v-if="!isSupervisor" type="warning" size="small" effect="light" style="margin-left:8px">仅主管可访问</el-tag>
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
            </div>
            <div class="hero-pill">
              <span class="pill-label">当前显示</span>
              <strong>{{ filteredEmployees.length }}</strong>
            </div>
            <div class="hero-pill">
              <span class="pill-label">最近创建者</span>
              <strong>{{ latestCreator }}</strong>
            </div>
          </div>
        </div>

        <!-- 创建员工按钮 -->
        <div class="toolbar">
          <el-input v-model="searchKeyword" placeholder="搜索工号或昵称" clearable class="search-input" />
          <el-button type="primary" :icon="Plus" @click="showCreateDialog = true">
            创建员工账号
          </el-button>
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
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, User, Lock } from '@element-plus/icons-vue'
import { userAPI } from '@/api'
import { useStore } from '@/store'

const { isSupervisor } = useStore()
const loading = ref(false)
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

async function loadEmployees() {
  if (!isSupervisor.value) return
  loading.value = true
  try {
    const res = await userAPI.listEmployees()
    employees.value = res.data || []
  } catch (err) {
    ElMessage.error('加载员工列表失败')
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
    ElMessage.success('删除成功')
    loadEmployees()
  } catch (err) {
    if (err !== 'cancel') {
      ElMessage.error(err.response?.data?.detail || '删除失败')
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
  try {
    if (editingEmployee.value) {
      const updates = {}
      if (form.value.nickname) updates.nickname = form.value.nickname
      if (form.value.password) updates.password = form.value.password
      await userAPI.updateEmployee(form.value.employee_id, updates)
      ElMessage.success('更新成功')
    } else {
      await userAPI.createEmployee(
        form.value.employee_id,
        form.value.password,
        form.value.nickname
      )
      ElMessage.success('创建成功')
    }
    showCreateDialog.value = false
    editingEmployee.value = null
    form.value = { employee_id: '', nickname: '', password: '' }
    loadEmployees()
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '操作失败')
  } finally {
    submitting.value = false
  }
}

onMounted(loadEmployees)
</script>

<style scoped>
.page {
  height: calc(100vh - 60px); overflow-y: auto;
  background:
    radial-gradient(circle at 8% 10%, rgba(124, 58, 237, .10), transparent 32%),
    radial-gradient(circle at 88% 82%, rgba(20, 184, 166, .10), transparent 34%),
    linear-gradient(145deg, #f8fafc 0%, #eef2ff 52%, #ecfeff 100%);
}
.page-inner { max-width: 1100px; margin: 0 auto; padding: 28px 24px; }
.page-title {
  display: flex; align-items: center; gap: 8px;
  font-size: 18px; font-weight: 700; color: #303133; margin-bottom: 24px;
}

.hero-banner {
  display: grid; grid-template-columns: 1.5fr 1fr; gap: 16px;
  padding: 20px 22px; border-radius: 18px; margin-bottom: 20px;
  background: linear-gradient(135deg, #111827, #7c3aed 58%, #0f766e);
  color: #fff; box-shadow: 0 20px 42px rgba(15, 23, 42, .16);
}
.hero-kicker { font-size: 12px; letter-spacing: .18em; text-transform: uppercase; opacity: .72; }
.hero-title { font-size: 22px; font-weight: 800; margin: 8px 0 6px; }
.hero-desc { font-size: 13px; line-height: 1.7; color: rgba(255,255,255,.78); }
.hero-pills { display: grid; gap: 10px; }
.hero-pill {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  padding: 12px 14px; border-radius: 14px;
  background: rgba(255,255,255,.10); border: 1px solid rgba(255,255,255,.12);
}
.pill-label { font-size: 12px; color: rgba(255,255,255,.68); }

.no-permission {
  text-align: center; padding: 60px 20px; margin-top: 12px;
  background: linear-gradient(180deg, #fff, #f8fafc); border-radius: 18px;
  border: 1px solid rgba(148,163,184,.18); box-shadow: 0 16px 36px rgba(15,23,42,.06);
}
.no-permission p { font-size: 14px; color: #606266; margin: 12px 0; }
.no-permission .hint { font-size: 12px; color: #909399; }

.toolbar { margin-bottom: 20px; display: flex; gap: 12px; align-items: center; }
.search-input { max-width: 320px; }
.employee-table { background: #fff; border-radius: 16px; overflow: hidden; box-shadow: 0 16px 36px rgba(15,23,42,.06); border: 1px solid rgba(148,163,184,.18); }
.employee-table :deep(.el-table__header-wrapper th) { background: #f8fafc; color: #334155; }
.employee-table :deep(.el-table__row:hover > td) { background: #f8fbff !important; }
</style>
