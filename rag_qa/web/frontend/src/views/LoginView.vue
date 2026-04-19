<template>
  <div class="login-shell">
    <div class="login-hero">
      <div class="hero-badge">EduRAG · 采矿安全智能问答系统</div>
      <h1>让矿山知识检索更快、更稳、更像一个真正的产品</h1>
      <p>基于 RAG、混合检索与实时反馈闭环，面向矿山安全场景的问答与知识管理平台。</p>
      <div class="hero-stats">
        <div><strong>Hybrid</strong><span>Dense + Sparse</span></div>
        <div><strong>Live</strong><span>反馈联动</span></div>
        <div><strong>Role</strong><span>主管权限控制</span></div>
      </div>
    </div>

    <div class="login-card">
      <div class="login-header">
        <div class="logo-mark"><el-icon size="28" color="#fff"><ChatDotRound /></el-icon></div>
        <div>
          <h2>登录系统</h2>
          <p>进入 EduRAG 工作台</p>
        </div>
      </div>

      <el-form ref="formRef" :model="form" :rules="rules" @submit.prevent="handleLogin">
        <el-form-item label="工号" prop="employeeId">
          <el-input
            v-model="form.employeeId"
            placeholder="请输入工号"
            :prefix-icon="User"
            clearable
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item label="密码" prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="请输入密码"
            :prefix-icon="Lock"
            clearable
            show-password
            @keyup.enter="handleLogin"
          />
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            :loading="loading"
            @click="handleLogin"
            class="login-btn"
          >
            {{ loading ? '登录中...' : '登录' }}
          </el-button>
        </el-form-item>
      </el-form>

      <div class="login-footer">
        <p class="demo-hint">演示账号：</p>
        <div class="demo-accounts">
          <span>主管账号：9526 / 9527 / 9528</span>
          <span>默认演示密码：由 EDURAG_DEFAULT_SUPERVISOR_PASSWORD 配置</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound, User, Lock } from '@element-plus/icons-vue'
import { authAPI } from '@/api'
import { useStore } from '@/store'

const router = useRouter()
const { setLogin } = useStore()
const formRef = ref(null)
const loading = ref(false)

const form = ref({
  employeeId: '',
  password: '',
})

const rules = {
  employeeId: [{ required: true, message: '请输入工号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

async function handleLogin() {
  if (!formRef.value) return
  
  try {
    await formRef.value.validate()
  } catch {
    return
  }

  loading.value = true
  try {
    const res = await authAPI.login(form.value.employeeId, form.value.password)
    const { token, employee_id, role, nickname, avatar } = res.data
    
    setLogin(token, {
      employee_id,
      role,
      nickname,
      avatar,
    })
    
    ElMessage.success('登录成功')
    router.push('/chat')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '登录失败')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-shell {
  width: 100%; height: 100vh; display: grid; grid-template-columns: 1.2fr minmax(360px, 420px);
  gap: 24px; align-items: center; padding: 32px; overflow: hidden;
  background:
    radial-gradient(circle at 12% 16%, rgba(37, 99, 235, 0.18), transparent 28%),
    radial-gradient(circle at 80% 84%, rgba(20, 184, 166, 0.14), transparent 30%),
    linear-gradient(145deg, #f8fafc 0%, #eef2ff 100%);
}

.login-shell::before,
.login-shell::after {
  content: '';
  position: absolute;
  inset: auto;
  border-radius: 999px;
  filter: blur(20px);
  pointer-events: none;
}

.login-hero {
  position: relative;
  color: #0f172a;
  padding: 40px 22px 40px 8vw;
  max-width: 820px;
}

.hero-badge {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 14px; border-radius: 999px;
  background: rgba(255,255,255,.7); border: 1px solid rgba(148,163,184,.22);
  color: #1d4ed8; font-weight: 700; font-size: 12px;
  box-shadow: 0 14px 34px rgba(15, 23, 42, .06);
}

.login-hero h1 {
  margin: 18px 0 14px;
  font-size: clamp(34px, 4vw, 58px);
  line-height: 1.08;
  font-weight: 900;
  letter-spacing: -0.04em;
  max-width: 13ch;
}

.login-hero p {
  max-width: 42rem;
  color: #475569;
  font-size: 18px;
  line-height: 1.8;
}

.hero-stats {
  display: flex; gap: 14px; flex-wrap: wrap; margin-top: 26px;
}

.hero-stats div {
  min-width: 132px; padding: 14px 16px; border-radius: 16px;
  background: rgba(255,255,255,.76); border: 1px solid rgba(148,163,184,.18);
  box-shadow: var(--edurag-shadow);
}

.hero-stats strong { display: block; font-size: 18px; color: #0f172a; }
.hero-stats span { font-size: 12px; color: #64748b; }

.login-card {
  width: 100%; max-width: 420px; justify-self: end;
  background: rgba(255,255,255,.88); backdrop-filter: blur(18px);
  border: 1px solid rgba(148,163,184,.18); border-radius: 26px;
  padding: 34px 32px; box-shadow: var(--edurag-shadow-strong);
  position: relative; z-index: 1;
}

.login-header { display: flex; align-items: center; gap: 14px; margin-bottom: 28px; }
.logo-mark {
  width: 52px; height: 52px; border-radius: 18px;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #1d4ed8, #0f766e);
  box-shadow: 0 14px 30px rgba(29, 78, 216, .25);
}
.login-header h2 { font-size: 24px; font-weight: 800; color: #0f172a; }
.login-header p { font-size: 13px; color: #64748b; margin-top: 3px; }

:deep(.el-form-item) { margin-bottom: 20px; }
:deep(.el-form-item__label) { font-size: 13px; color: #475569; font-weight: 600; }
:deep(.el-input__wrapper) {
  border-radius: 14px; background: rgba(248,250,252,.9); border: 1px solid rgba(148,163,184,.24);
  box-shadow: none; transition: all .25s ease;
}
:deep(.el-input__wrapper:hover) { border-color: rgba(37,99,235,.34); background: #fff; }
:deep(.el-input__wrapper.is-focus) {
  border-color: #2563eb; background: #fff; box-shadow: 0 0 0 4px rgba(37,99,235,.10);
}

.login-btn {
  width: 100%; height: 48px; font-size: 15px; font-weight: 800;
  border-radius: 14px; background: linear-gradient(135deg, #1d4ed8, #0ea5e9);
  border: none; box-shadow: 0 16px 30px rgba(37,99,235,.28);
}
.login-btn:hover { transform: translateY(-1px); box-shadow: 0 18px 34px rgba(37,99,235,.34); }

.login-footer { margin-top: 24px; padding-top: 18px; border-top: 1px dashed rgba(148,163,184,.26); }
.demo-hint { font-size: 12px; color: #64748b; margin: 0 0 10px; font-weight: 700; letter-spacing: .04em; }
.demo-accounts { display: grid; gap: 8px; }
.demo-accounts span {
  font-size: 12px; color: #334155; background: rgba(248,250,252,.88); padding: 10px 12px; border-radius: 12px;
  border: 1px solid rgba(148,163,184,.18); font-family: 'JetBrains Mono', 'Courier New', monospace;
}

@media (max-width: 980px) {
  .login-shell { grid-template-columns: 1fr; padding: 20px; }
  .login-hero { padding: 20px 8px; max-width: none; }
  .login-card { justify-self: stretch; max-width: none; }
}
</style>
