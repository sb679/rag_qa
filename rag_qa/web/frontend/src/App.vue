<template>
  <el-config-provider :locale="zhCn">
    <div v-if="isLoggedIn" class="app-root">
    <!-- 顶部导航栏 -->
    <el-header class="app-header">
      <div class="header-brand">
        <div class="brand-mark">
          <el-icon :size="20" color="#fff"><ChatDotRound /></el-icon>
        </div>
        <div class="brand-copy">
          <span class="brand-name">采矿安全智能问答系统</span>
          <span class="brand-sub">Knowledge retrieval, traceability and feedback loop</span>
        </div>
      </div>

      <el-menu
        :default-active="activeRoute"
        mode="horizontal"
        :ellipsis="false"
        class="header-nav"
        router
      >
        <el-menu-item index="/chat">
          <el-icon><ChatDotRound /></el-icon>智能问答
        </el-menu-item>
        <el-menu-item index="/knowledge">
          <el-icon><DataBoard /></el-icon>知识库
        </el-menu-item>
        <el-menu-item index="/config">
          <el-icon><Setting /></el-icon>系统配置
        </el-menu-item>
        <el-menu-item index="/dashboard">
          <el-icon><DataAnalysis /></el-icon>驾驶舱
        </el-menu-item>
        <el-menu-item v-if="showWechatAnnotatorEntry" index="/wechat-annotator">
          <el-icon><DataBoard /></el-icon>公众号多 Agent
        </el-menu-item>
        <el-menu-item v-if="isSupervisor" index="/employees">
          <el-icon><User /></el-icon>员工管理
        </el-menu-item>
      </el-menu>

      <div class="header-right">
        <div class="runtime-pill" :class="online ? 'online' : 'offline'">
          <span class="runtime-dot"></span>
          <span>{{ online ? '系统正常' : '演示模式' }}</span>
        </div>
        
        <el-dropdown @command="handleCommand" class="user-dropdown">
          <div class="user-info">
            <el-avatar :src="user?.avatar || defaultAvatar" size="32" class="clickable-avatar" @click.stop="openAvatarPreview(user?.avatar || defaultAvatar)" />
            <span class="user-name">{{ user?.nickname || '用户' }}</span>
            <el-icon class="is-icon"><ArrowDown /></el-icon>
          </div>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="profile">个人资料</el-dropdown-item>
              <el-dropdown-item command="logout">登出</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </el-header>

    <!-- 页面内容 -->
    <el-main class="app-main">
      <router-view />
    </el-main>

    <!-- 个人资料对话框 -->
    <el-dialog v-model="showProfileDialog" title="个人资料" width="400px">
      <el-form :model="profileForm" label-width="80px">
        <el-form-item label="工号">
          <el-input v-model="profileForm.employee_id" disabled />
        </el-form-item>
        <el-form-item label="头像">
          <div class="avatar-editor">
            <el-avatar :src="profileForm.avatar || user?.avatar || defaultAvatar" size="56" class="clickable-avatar" @click="openAvatarPreview(profileForm.avatar || user?.avatar || defaultAvatar)" />
            <el-upload
              :show-file-list="false"
              :before-upload="beforeAvatarUpload"
              :http-request="handleAvatarUpload"
              accept="image/*"
            >
              <el-button :loading="avatarUploading" size="small">上传头像</el-button>
            </el-upload>
          </div>
        </el-form-item>
        <el-form-item label="昵称">
          <el-input v-model="profileForm.nickname" />
        </el-form-item>
        <el-form-item label="新密码">
          <el-input v-model="profileForm.password" type="password" placeholder="不修改则留空" show-password />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showProfileDialog = false">取消</el-button>
        <el-button type="primary" @click="updateProfile" :loading="profileLoading">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="showAvatarPreview" title="头像预览" width="460px" center>
      <div class="avatar-preview-wrap">
        <img :src="avatarPreviewUrl || defaultAvatar" alt="avatar preview" class="avatar-preview-image" />
      </div>
    </el-dialog>
    </div>
    <router-view v-else />
  </el-config-provider>
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ChatDotRound, DataBoard, Setting, DataAnalysis, User, ArrowDown } from '@element-plus/icons-vue'
import zhCn from 'element-plus/es/locale/lang/zh-cn'
import { knowledgeAPI, authAPI } from '@/api'
import { useStore } from '@/store'

const route = useRoute()
const router = useRouter()
const { state, isLoggedIn, isSupervisor, logout, updateProfile: updateStoreProfile } = useStore()
const showWechatAnnotatorEntry = computed(() => isSupervisor.value && import.meta.env.VITE_ENABLE_WECHAT_ANNOTATOR === 'true')

const activeRoute = computed(() => route.path)
const user = computed(() => state.user)
const online = ref(false)
const showProfileDialog = ref(false)
const showAvatarPreview = ref(false)
const avatarPreviewUrl = ref('')
const profileLoading = ref(false)
const avatarUploading = ref(false)
const defaultAvatar = 'data:image/svg+xml,%3Csvg xmlns=%22http://www.w3.org/2000/svg%22 viewBox=%220 0 40 40%22%3E%3Ccircle cx=%2220%22 cy=%2220%22 r=%2220%22 fill=%22%23409eff%22/%3E%3Ctext x=%2220%22 y=%2226%22 text-anchor=%22middle%22 font-size=%2220%22 fill=%22white%22 font-weight=%22bold%22%3EU%3C/text%3E%3C/svg%3E'

const profileForm = ref({
  employee_id: '',
  avatar: '',
  nickname: '',
  password: '',
})

function handleAuthExpired() {
  logout()
  if (route.path !== '/login') {
    router.push('/login')
  }
  ElMessage.warning('登录状态已失效，请重新登录')
}

onMounted(async () => {
  window.addEventListener('rag-auth-expired', handleAuthExpired)

  if (isLoggedIn.value) {
    try {
      await authAPI.getProfile()
    } catch (err) {
      if (err?.response?.status === 401) {
        handleAuthExpired()
        return
      }
      ElMessage.warning('当前登录校验服务暂时不可用，已保留本地登录态，请稍后重试。')
    }
  }

  try {
    const res = await knowledgeAPI.status()
    online.value = res.data.system?.rag_available ?? false
  } catch {
    online.value = false
  }
  
  if (user.value) {
    profileForm.value.employee_id = user.value.employee_id
    profileForm.value.avatar = user.value.avatar
    profileForm.value.nickname = user.value.nickname
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('rag-auth-expired', handleAuthExpired)
})

async function handleCommand(command) {
  if (command === 'profile') {
    if (user.value) {
      profileForm.value.employee_id = user.value.employee_id
      profileForm.value.avatar = user.value.avatar
      profileForm.value.nickname = user.value.nickname
      profileForm.value.password = ''
    }
    showProfileDialog.value = true
  } else if (command === 'logout') {
    try {
      await authAPI.logout()
    } catch {}
    logout()
    router.push('/login')
    ElMessage.success('已登出')
  }
}

async function updateProfile() {
  profileLoading.value = true
  try {
    const updates = {}
    if (profileForm.value.nickname !== user.value.nickname) {
      updates.nickname = profileForm.value.nickname
    }
    if (profileForm.value.password) {
      updates.password = profileForm.value.password
    }
    
    if (Object.keys(updates).length > 0) {
      await authAPI.updateProfile(updates)
      updateStoreProfile(updates)
      ElMessage.success('更新成功')
    }
    showProfileDialog.value = false
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '更新失败')
  } finally {
    profileLoading.value = false
  }
}

function beforeAvatarUpload(file) {
  const isImage = file.type.startsWith('image/')
  if (!isImage) {
    ElMessage.error('请上传图片文件')
    return false
  }
  const isLt5M = file.size / 1024 / 1024 < 5
  if (!isLt5M) {
    ElMessage.error('头像大小不能超过 5MB')
    return false
  }
  return true
}

async function handleAvatarUpload(options) {
  avatarUploading.value = true
  try {
    const res = await authAPI.uploadAvatar(options.file)
    const avatar = res?.data?.avatar || ''
    profileForm.value.avatar = avatar
    updateStoreProfile({ avatar })
    options.onSuccess?.(res.data)
    ElMessage.success('头像上传成功')
  } catch (err) {
    options.onError?.(err)
    ElMessage.error(err?.response?.data?.detail || '头像上传失败')
  } finally {
    avatarUploading.value = false
  }
}

function openAvatarPreview(url) {
  avatarPreviewUrl.value = url || defaultAvatar
  showAvatarPreview.value = true
}
</script>

<style>
 :root {
  --edurag-bg: #f3f6fb;
  --edurag-surface: rgba(255, 255, 255, 0.74);
  --edurag-surface-strong: rgba(255, 255, 255, 0.9);
  --edurag-border: rgba(148, 163, 184, 0.22);
  --edurag-text: #0f172a;
  --edurag-text-soft: #64748b;
  --edurag-primary: #0f5bd8;
  --edurag-primary-2: #00a6c7;
  --edurag-accent: #0f766e;
  --edurag-warm: #f59e0b;
  --edurag-shadow: 0 22px 50px rgba(15, 23, 42, 0.08);
  --edurag-shadow-strong: 0 30px 80px rgba(15, 23, 42, 0.14);
  --edurag-shadow-soft: 0 12px 30px rgba(15, 23, 42, 0.06);
  --edurag-radius: 22px;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html {
  scroll-behavior: smooth;
  background: #edf3fb;
}
body {
  font-family: 'Trebuchet MS', 'PingFang SC', 'Microsoft YaHei', 'Segoe UI', sans-serif;
  background:
    radial-gradient(circle at 10% 10%, rgba(15, 91, 216, 0.12), transparent 24%),
    radial-gradient(circle at 76% 18%, rgba(20, 184, 166, 0.09), transparent 28%),
    radial-gradient(circle at 86% 84%, rgba(249, 115, 22, 0.08), transparent 22%),
    linear-gradient(155deg, #f8fbff 0%, #eef4ff 52%, #eefaf8 100%);
  color: var(--edurag-text);
}

#app { min-height: 100vh; }

.app-root  {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  position: relative;
  isolation: isolate;
}
.app-root::before,
.app-root::after {
  content: '';
  position: absolute;
  inset: auto;
  width: 420px;
  height: 420px;
  border-radius: 999px;
  pointer-events: none;
  filter: blur(70px);
  opacity: 0.5;
  z-index: -1;
}
.app-root::before {
  top: -140px;
  right: -120px;
  background: rgba(14, 165, 233, 0.16);
}
.app-root::after {
  left: -180px;
  bottom: -180px;
  background: rgba(15, 118, 110, 0.12);
}
.app-header {
  height: 72px !important;
  display: flex;
  align-items: center;
  padding: 0 28px;
  background: rgba(255, 255, 255, 0.7);
  border-bottom: 1px solid rgba(228, 231, 237, 0.48);
  box-shadow: 0 10px 28px rgba(15, 23, 42, 0.06);
  z-index: 100;
  flex-shrink: 0;
  backdrop-filter: blur(20px);
}
.header-brand {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-right: 32px;
  white-space: nowrap;
  flex: 0 0 auto;
}
.brand-mark {
  width: 42px;
  height: 42px;
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #0f172a 0%, #0f5bd8 55%, #14b8a6 100%);
  box-shadow: 0 16px 28px rgba(15, 91, 216, 0.24);
}
.brand-copy {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.brand-name   {
  font-size: 17px;
  font-weight: 900;
  letter-spacing: -0.02em;
  background: linear-gradient(135deg, #0f172a 0%, var(--edurag-primary) 52%, var(--edurag-accent) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.brand-sub    {
  font-size: 11px;
  color: #64748b;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}
.header-nav   {
  flex: 1 1 0;
  min-width: 0;
  border-bottom: none !important;
  overflow-x: auto;
  overflow-y: hidden;
  scrollbar-width: none;
  -ms-overflow-style: none;
}
.header-nav::-webkit-scrollbar { display: none; }
.header-nav .el-menu-item {
  font-size: 14px; height: 72px; line-height: 72px; font-weight: 700;
  white-space: nowrap;
  flex-shrink: 0;
  transition: all 0.28s ease; border-radius: 18px 18px 0 0;
}
.header-nav .el-menu-item:hover { color: var(--edurag-primary); background: rgba(15, 91, 216, 0.05); }
.header-right { margin-left: 16px; display: flex; align-items: center; gap: 16px; flex: 0 0 auto; min-width: max-content; }
.runtime-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.03em;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: rgba(255, 255, 255, 0.7);
  box-shadow: var(--edurag-shadow-soft);
}
.runtime-pill.online {
  color: #047857;
}
.runtime-pill.offline {
  color: #b45309;
}
.runtime-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: currentColor;
  box-shadow: 0 0 0 4px color-mix(in srgb, currentColor 14%, transparent);
}
.user-dropdown { cursor: pointer; }
.user-info {
  display: flex; align-items: center; gap: 8px; padding: 7px 10px 7px 8px; border-radius: 999px;
  transition: all 0.28s ease; border: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(255, 255, 255, 0.68);
  box-shadow: var(--edurag-shadow-soft);
}
.user-info:hover { background: rgba(255, 255, 255, 0.88); border-color: rgba(15, 91, 216, 0.16); }
.user-name { font-size: 13px; color: #334155; font-weight: 700; }
.is-icon { margin-left: 4px; }
.app-main     { flex: 1; padding: 0 !important; overflow: hidden; background: transparent; }
.avatar-editor { display: flex; align-items: center; gap: 12px; }
.clickable-avatar { cursor: zoom-in; }
.avatar-preview-wrap { display: flex; justify-content: center; }
.avatar-preview-image {
  width: 100%;
  max-width: 380px;
  max-height: 60vh;
  object-fit: contain;
  border-radius: 10px;
  border: 1px solid #ebeef5;
}

@media (max-width: 1440px) {
  .runtime-pill {
    display: none;
  }

  .header-nav .el-menu-item {
    padding: 0 12px;
    font-size: 13px;
  }
}

@media (max-width: 1080px) {
  .brand-sub {
    display: none;
  }
}

@media (max-width: 860px) {
  .app-header {
    padding: 0 18px;
  }

  .header-brand {
    margin-right: 12px;
  }

  .brand-name {
    font-size: 15px;
  }

  .header-right {
    gap: 10px;
  }

  .user-name {
    display: none;
  }

  .header-nav .el-menu-item {
    padding: 0 12px;
    font-size: 13px;
  }
}
</style>
