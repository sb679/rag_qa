import { createRouter, createWebHistory } from 'vue-router'
import { useStore } from '@/store'
import LoginView           from '@/views/LoginView.vue'
import ChatView            from '@/views/ChatView.vue'
import KnowledgeView       from '@/views/KnowledgeView.vue'
import ConfigView          from '@/views/ConfigView.vue'
import DashboardView       from '@/views/DashboardView.vue'
import EmployeeManageView  from '@/views/EmployeeManageView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/login',     component: LoginView,           meta: { title: '登录' } },
    { path: '/',          redirect: '/chat' },
    { path: '/chat',      component: ChatView,            meta: { title: '智能问答', requiresAuth: true } },
    { path: '/knowledge', component: KnowledgeView,       meta: { title: '知识库', requiresAuth: true } },
    { path: '/config',    component: ConfigView,          meta: { title: '系统配置', requiresAuth: true } },
    { path: '/dashboard', component: DashboardView,       meta: { title: '系统驾驶仓', requiresAuth: true } },
    { path: '/employees', component: EmployeeManageView,  meta: { title: '员工管理', requiresAuth: true } },
  ],
})

router.beforeEach((to, from, next) => {
  const { isLoggedIn } = useStore()
  
  if (to.meta.requiresAuth && !isLoggedIn.value) {
    next('/login')
  } else if (to.path === '/login' && isLoggedIn.value) {
    next('/chat')
  } else {
    next()
  }
})

router.afterEach((to) => {
  document.title = `${to.meta.title || 'EduRAG'} · 采矿安全智能问答`
})

export default router
