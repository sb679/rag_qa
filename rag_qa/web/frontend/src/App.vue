<template>
  <div v-if="isLoggedIn" class="app-root">
    <!-- 顶部导航栏 -->
    <el-header class="app-header">
      <div class="header-brand">
        <el-icon :size="22" color="#409eff"><ChatDotRound /></el-icon>
        <span class="brand-name">EduRAG</span>
        <span class="brand-sub">采矿安全智能问答系统</span>
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
          <el-icon><DataAnalysis /></el-icon>驾驶仓
        </el-menu-item>
        <el-menu-item v-if="isSupervisor" index="/employees">
          <el-icon><User /></el-icon>员工管理
        </el-menu-item>
      </el-menu>

      <div class="header-right">
        <el-tag :type="online ? 'success' : 'warning'" size="small" effect="light">
          {{ online ? '● 系统正常' : '● 演示模式' }}
        </el-tag>
        
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
</template>

<script setup>
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { ChatDotRound, DataBoard, Setting, DataAnalysis, User, ArrowDown } from '@element-plus/icons-vue'
import { knowledgeAPI, authAPI } from '@/api'
import { useStore } from '@/store'

const route = useRoute()
const router = useRouter()
const { state, isLoggedIn, isSupervisor, logout, updateProfile: updateStoreProfile } = useStore()

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
    } catch {
      handleAuthExpired()
      return
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
  --edurag-bg: #f4f7fb;
  --edurag-surface: rgba(255, 255, 255, 0.88);
  --edurag-surface-strong: rgba(255, 255, 255, 0.96);
  --edurag-border: rgba(148, 163, 184, 0.18);
  --edurag-text: #0f172a;
  --edurag-text-soft: #64748b;
  --edurag-primary: #2563eb;
  --edurag-primary-2: #0ea5e9;
  --edurag-accent: #14b8a6;
  --edurag-warm: #f59e0b;
  --edurag-shadow: 0 16px 40px rgba(15, 23, 42, 0.08);
  --edurag-shadow-strong: 0 22px 60px rgba(15, 23, 42, 0.14);
  --edurag-radius: 18px;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body {
  font-family: 'Inter', 'PingFang SC', 'Microsoft YaHei', 'Segoe UI', sans-serif;
  background:
    radial-gradient(circle at 12% 12%, rgba(37, 99, 235, 0.12), transparent 30%),
    radial-gradient(circle at 88% 88%, rgba(20, 184, 166, 0.12), transparent 32%),
    linear-gradient(145deg, #f8fafc 0%, #eef2ff 52%, #ecfeff 100%);
  color: var(--edurag-text);
}

html { scroll-behavior: smooth; }
#app { min-height: 100vh; }

.app-root  { height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
.app-header {
  height: 60px !important;
  display: flex;
  align-items: center;
  padding: 0 24px;
  background: rgba(255, 255, 255, 0.82);
  border-bottom: 1px solid rgba(228, 231, 237, 0.72);
  box-shadow: 0 2px 14px rgba(15, 23, 42, 0.08);
  z-index: 100;
  flex-shrink: 0;
  backdrop-filter: blur(14px);
}
.header-brand { display: flex; align-items: center; gap: 8px; margin-right: 32px; white-space: nowrap; }
.brand-name   { font-size: 17px; font-weight: 800; background: linear-gradient(135deg, var(--edurag-primary) 0%, #7c3aed 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; background-clip: text; }
.brand-sub    { font-size: 12px; color: #909399; margin-left: 2px; font-weight: 500; }
.header-nav   { flex: 1; border-bottom: none !important; }
.header-nav .el-menu-item {
  font-size: 14px; height: 60px; line-height: 60px; font-weight: 500;
  transition: all 0.28s ease; border-radius: 12px 12px 0 0;
}
.header-nav .el-menu-item:hover { color: var(--edurag-primary); background: rgba(37, 99, 235, 0.05); }
.header-right { margin-left: 16px; display: flex; align-items: center; gap: 16px; }
.user-dropdown { cursor: pointer; }
.user-info {
  display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 999px;
  transition: all 0.28s ease; border: 1px solid transparent;
}
.user-info:hover { background: rgba(37, 99, 235, 0.08); border-color: rgba(37, 99, 235, 0.16); }
.user-name { font-size: 13px; color: #606266; font-weight: 600; }
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
</style>
