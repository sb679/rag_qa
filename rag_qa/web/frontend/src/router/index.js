import { createRouter, createWebHistory } from 'vue-router'
import { useStore } from '@/store'
const LoginView = () => import('@/views/LoginView.vue')
const ChatView = () => import('@/views/ChatView.vue')
const KnowledgeView = () => import('@/views/KnowledgeView.vue')
const ConfigView = () => import('@/views/ConfigView.vue')
const DashboardView = () => import('@/views/DashboardView.vue')
const EmployeeManageView = () => import('@/views/EmployeeManageView.vue')
const enableWechatAnnotator = import.meta.env.VITE_ENABLE_WECHAT_ANNOTATOR === 'true'
const routes = [
  { path: '/login',     component: LoginView,           meta: { title: '登录' } },
  { path: '/',          redirect: '/chat' },
  { path: '/chat',      component: ChatView,            meta: { title: '智能问答', requiresAuth: true } },
  { path: '/knowledge', component: KnowledgeView,       meta: { title: '知识库', requiresAuth: true } },
  { path: '/config',    component: ConfigView,          meta: { title: '系统配置', requiresAuth: true } },
  { path: '/dashboard', component: DashboardView,       meta: { title: '系统驾驶舱', requiresAuth: true } },
  { path: '/employees', component: EmployeeManageView,  meta: { title: '员工管理', requiresAuth: true } },
]

if (enableWechatAnnotator) {
  // WechatAnnotatorView 依赖独立子后端（wechat_annotator_main.py，端口 8001），默认关闭入口可避免日常启动时引入无关能力。
  routes.push({
    path: '/wechat-annotator',
    component: () => import('@/views/WechatAnnotatorView.vue'),
    meta: { title: '公众号多 Agent 工作台', requiresAuth: true, requiresSupervisor: true },
  })
}

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.beforeEach((to, from, next) => {
  const { isLoggedIn, isSupervisor } = useStore()
  
  if (to.meta.requiresAuth && !isLoggedIn.value) {
    next('/login')
  } else if (to.meta.requiresSupervisor && !isSupervisor.value) {
    next('/chat')
  } else if (to.path === '/login' && isLoggedIn.value) {
    next('/chat')
  } else {
    next()
  }
})

router.afterEach((to) => {
  document.title = `${to.meta.title || '采矿安全智能问答系统'} · 采矿安全智能问答`
})

export default router
