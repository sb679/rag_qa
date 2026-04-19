import { reactive, computed } from 'vue'

const state = reactive({
  token: localStorage.getItem('token') || null,
  user: JSON.parse(localStorage.getItem('user') || 'null'),
})

export const useStore = () => {
  const isLoggedIn = computed(() => !!state.token)
  const isSupervisor = computed(() => state.user?.role === 'supervisor')
  
  const setLogin = (token, user) => {
    state.token = token
    state.user = user
    localStorage.setItem('token', token)
    localStorage.setItem('user', JSON.stringify(user))
  }
  
  const logout = () => {
    state.token = null
    state.user = null
    localStorage.removeItem('token')
    localStorage.removeItem('user')
  }
  
  const updateProfile = (updates) => {
    state.user = { ...state.user, ...updates }
    localStorage.setItem('user', JSON.stringify(state.user))
  }
  
  return {
    state,
    isLoggedIn,
    isSupervisor,
    setLogin,
    logout,
    updateProfile,
  }
}
