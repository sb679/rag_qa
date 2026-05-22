<template>
  <div class="login-shell motion-ready">
    <div class="login-hero">
      <div class="hero-badge">采矿安全智能问答系统</div>
      <h1>把安全规程、事故场景与作业经验接成一个可追溯的问答系统</h1>
      <p>面向采矿与冶金安全场景，覆盖规程问答、隐患解释、知识溯源和反馈闭环，不再只是一个泛化聊天页面。</p>
      <div class="hero-stats">
        <div><strong>规程问答</strong><span>采矿与冶金安全知识</span></div>
        <div><strong>知识溯源</strong><span>检索命中与来源可追踪</span></div>
        <div><strong>反馈闭环</strong><span>主管处理状态联动</span></div>
      </div>
    </div>

    <div class="login-card">
      <div class="login-header">
        <div class="logo-mark"><el-icon size="28" color="#fff"><ChatDotRound /></el-icon></div>
        <div>
          <h2>登录系统</h2>
          <p>进入采矿安全智能问答工作台</p>
        </div>
      </div>

      <div v-if="loginError" class="login-status error">
        <div class="login-status-title">登录失败</div>
        <div class="login-status-desc">{{ loginError }}</div>
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
          <span>默认演示密码：由系统环境变量统一配置</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { ChatDotRound, User, Lock } from '@element-plus/icons-vue'
import { authAPI } from '@/api'
import { useStore } from '@/store'

const router = useRouter()
const { setLogin } = useStore()
const formRef = ref(null)
const loading = ref(false)
const loginError = ref('')

const form = ref({
  employeeId: '',
  password: '',
})

const rules = {
  employeeId: [{ required: true, message: '请输入工号', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
}

watch(
  () => [form.value.employeeId, form.value.password],
  () => {
    if (loginError.value) {
      loginError.value = ''
    }
  }
)

async function handleLogin() {
  if (!formRef.value) return
  loginError.value = ''
  
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

    router.push('/chat')
  } catch (err) {
    const status = err?.response?.status
    if (status === 401) {
      loginError.value = '工号或密码不正确，请重新检查后再试。'
      return
    }
    if (status === 404) {
      loginError.value = '当前无法连接登录服务，请确认前端代理或后端服务是否正常。'
      return
    }
    loginError.value = err?.response?.data?.detail || '登录失败，请稍后重试。'
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
  animation: loginOrbFloat 12s ease-in-out infinite alternate;
}

.login-shell::before {
  width: 280px;
  height: 280px;
  top: 4%;
  left: 6%;
  background: rgba(37, 99, 235, 0.16);
}

.login-shell::after {
  width: 320px;
  height: 320px;
  right: -4%;
  bottom: 4%;
  background: rgba(20, 184, 166, 0.16);
  animation-duration: 15s;
}

.login-hero {
  position: relative;
  color: #0f172a;
  padding: 40px 22px 40px 8vw;
  max-width: 820px;
  opacity: 0;
  transform: translateY(24px);
  animation: loginReveal .8s cubic-bezier(.22,1,.36,1) forwards;
}

.hero-badge {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 14px; border-radius: 999px;
  background: rgba(255,255,255,.7); border: 1px solid rgba(148,163,184,.22);
  color: #1d4ed8; font-weight: 700; font-size: 12px;
  box-shadow: 0 14px 34px rgba(15, 23, 42, .06);
  opacity: 0;
  transform: translateY(18px);
  animation: loginReveal .7s cubic-bezier(.22,1,.36,1) .08s forwards;
}

.login-hero h1 {
  margin: 18px 0 14px;
  font-size: clamp(34px, 4vw, 58px);
  line-height: 1.08;
  font-weight: 900;
  letter-spacing: -0.04em;
  max-width: 13ch;
  opacity: 0;
  transform: translateY(20px);
  animation: loginReveal .82s cubic-bezier(.22,1,.36,1) .16s forwards;
}

.login-hero p {
  max-width: 42rem;
  color: #475569;
  font-size: 18px;
  line-height: 1.8;
  opacity: 0;
  transform: translateY(20px);
  animation: loginReveal .82s cubic-bezier(.22,1,.36,1) .24s forwards;
}

.hero-stats {
  display: flex; gap: 14px; flex-wrap: wrap; margin-top: 26px;
}

.hero-stats div {
  min-width: 132px; padding: 14px 16px; border-radius: 16px;
  background: rgba(255,255,255,.76); border: 1px solid rgba(148,163,184,.18);
  box-shadow: var(--edurag-shadow);
  opacity: 0;
  transform: translateY(20px) scale(.98);
  animation: loginReveal .72s cubic-bezier(.22,1,.36,1) forwards;
}

.hero-stats div:nth-child(1) { animation-delay: .3s; }
.hero-stats div:nth-child(2) { animation-delay: .38s; }
.hero-stats div:nth-child(3) { animation-delay: .46s; }

.hero-stats strong { display: block; font-size: 18px; color: #0f172a; }
.hero-stats span { font-size: 12px; color: #64748b; }

.login-card {
  width: 100%; max-width: 420px; justify-self: end;
  background: rgba(255,255,255,.88); backdrop-filter: blur(18px);
  border: 1px solid rgba(148,163,184,.18); border-radius: 26px;
  padding: 34px 32px; box-shadow: var(--edurag-shadow-strong);
  position: relative; z-index: 1;
  opacity: 0;
  transform: translateY(28px) scale(.985);
  animation: loginReveal .9s cubic-bezier(.22,1,.36,1) .18s forwards;
}

.login-header { display: flex; align-items: center; gap: 14px; margin-bottom: 28px; }
.logo-mark {
  width: 52px; height: 52px; border-radius: 18px;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(135deg, #1d4ed8, #0f766e);
  box-shadow: 0 14px 30px rgba(29, 78, 216, .25);
  animation: logoFloat 5.6s ease-in-out infinite;
}
.login-header h2 { font-size: 24px; font-weight: 800; color: #0f172a; }
.login-header p { font-size: 13px; color: #64748b; margin-top: 3px; }

.login-status {
  margin-bottom: 16px;
  padding: 12px 14px;
  border-radius: 16px;
  background: linear-gradient(180deg, rgba(254, 242, 242, .96), rgba(255, 255, 255, .98));
  border: 1px solid rgba(239, 68, 68, .18);
}

.login-status-title {
  font-size: 13px;
  font-weight: 800;
  color: #b91c1c;
}

.login-status-desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: #7f1d1d;
}

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

@keyframes loginReveal {
  from {
    opacity: 0;
    transform: translateY(22px) scale(.985);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes loginOrbFloat {
  from { transform: translate3d(0, 0, 0) scale(1); }
  to { transform: translate3d(24px, -18px, 0) scale(1.06); }
}

@keyframes logoFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-5px); }
}

@media (prefers-reduced-motion: reduce) {
  .login-shell::before,
  .login-shell::after,
  .login-hero,
  .hero-badge,
  .login-hero h1,
  .login-hero p,
  .hero-stats div,
  .login-card,
  .logo-mark {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}

@media (max-width: 980px) {
  .login-shell { grid-template-columns: 1fr; padding: 20px; }
  .login-hero { padding: 20px 8px; max-width: none; }
  .login-card { justify-self: stretch; max-width: none; }
}
</style>
