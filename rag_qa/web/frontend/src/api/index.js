import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 30000 })

function getToken() {
  return localStorage.getItem('token')
}

function clearAuthState() {
  localStorage.removeItem('token')
  localStorage.removeItem('user')
  window.dispatchEvent(new CustomEvent('rag-auth-expired'))
}

api.interceptors.request.use((config) => {
  const token = getToken()
  if (token) {
    config.headers = config.headers || {}
    if (!config.headers.Authorization) {
      config.headers.Authorization = `Bearer ${token}`
    }
  }
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error?.response?.status === 401) {
      clearAuthState()
    }
    return Promise.reject(error)
  }
)

// ── 认证 ──────────────────────────────────────────────────────────────────────
export const authAPI = {
  login: (employeeId, password) => api.post('/users/login', { employee_id: employeeId, password }),
  logout: () => api.post('/users/logout'),
  getProfile: () => api.get('/users/profile'),
  updateProfile: (updates) => api.put('/users/profile', updates),
  uploadAvatar: (file) => {
    const form = new FormData()
    form.append('file', file)
    return api.post('/users/profile/avatar', form)
  },
}

// ── 用户管理 ──────────────────────────────────────────────────────────────────
export const userAPI = {
  listEmployees: () => api.get('/users/employees'),
  createEmployee: (employeeId, password, nickname) => api.post('/users/employees', { employee_id: employeeId, password, nickname }),
  updateEmployee: (employeeId, updates) => api.put(`/users/employees/${employeeId}`, updates),
  deleteEmployee: (employeeId) => api.delete(`/users/employees/${employeeId}`),
}

// ── 会话 ──────────────────────────────────────────────────────────────────────
export const sessionAPI = {
  list:     ()         => api.get('/sessions/'),
  create:   (metadata) => api.post('/sessions/', { metadata }),
  remove:   (id)       => api.delete(`/sessions/${id}`),
  messages: (id)       => api.get(`/sessions/${id}/messages`),
}

export const chatAPI = {
  examples: () => api.get('/chat/examples'),
}

// ── 知识库 ────────────────────────────────────────────────────────────────────
export const knowledgeAPI = {
  status: () => api.get('/knowledge/status'),
}

export const datasetAPI = {
  listFiles: (source = '') => api.get('/dataset/files', { params: source ? { source } : {} }),
  deleteFile: (fileId) => api.delete(`/dataset/files/${encodeURIComponent(fileId)}`),
  downloadFileUrl: (fileId) => `/api/dataset/files/${encodeURIComponent(fileId)}/download`,
  downloadLegacyFileUrl: (name, source = '') => {
    const qs = new URLSearchParams()
    qs.set('name', name)
    if (source) qs.set('source', source)
    return `/api/dataset/files/legacy/download?${qs.toString()}`
  },
}

// ── 反馈 ──────────────────────────────────────────────────────────────────────
export const feedbackAPI = {
  submit: (sessionId, messageIndex, userId, feedbackType, content) => 
    api.post('/feedback/submit', { session_id: sessionId, message_index: messageIndex, user_id: userId, feedback_type: feedbackType, content }),
  getStats: () => api.get('/feedback/stats'),
}

// ── 流式对话（RAG + LLM 对比） ───────────────────────────────────────────────
/**
 * @param callbacks {{
 *   onRetrievalInfo(info),  // 检索过程信息
 *   onToken(char),          // RAG 答案字符
 *   onLlmToken(char),       // LLM 对比答案字符
 *   onDone(data),
 *   onError(msg),
 * }}
 */
export async function streamChat(query, sessionId, sourceFilter, callbacks) {
  const { onRetrievalInfo, onToken, onLlmToken, onDone, onError } = callbacks
  await _fetchSSE(
    '/api/chat/send',
    { query, session_id: sessionId, source_filter: sourceFilter },
    (event) => {
      if      (event.type === 'retrieval_info') onRetrievalInfo?.(event.data)
      else if (event.type === 'token')          onToken?.(event.data)
      else if (event.type === 'llm_token')      onLlmToken?.(event.data)
      else if (event.type === 'done')           onDone?.(event.data)
      else if (event.type === 'error')          onError?.(event.data)
    },
    onError,
  )
}

export async function streamChatWithImage(query, imageFile, sessionId, sourceFilter, callbacks) {
  const { onRetrievalInfo, onToken, onLlmToken, onDone, onError } = callbacks
  const form = new FormData()
  form.append('query', query || '')
  if (sessionId) form.append('session_id', sessionId)
  if (sourceFilter) form.append('source_filter', sourceFilter)
  form.append('image', imageFile)

  await _fetchSSE(
    '/api/chat/send-image',
    form,
    (event) => {
      if      (event.type === 'retrieval_info') onRetrievalInfo?.(event.data)
      else if (event.type === 'token')          onToken?.(event.data)
      else if (event.type === 'llm_token')      onLlmToken?.(event.data)
      else if (event.type === 'done')           onDone?.(event.data)
      else if (event.type === 'error')          onError?.(event.data)
    },
    onError,
    { isFormData: true },
  )
}

// ── 文档上传（SSE 进度流） ───────────────────────────────────────────────────
/**
 * @param callbacks {{
 *   onProgress(step, pct),
 *   onDone(chunks, filename),
 *   onError(msg),
 * }}
 */
export async function uploadDocument(file, source, callbacks) {
  const { onProgress, onDone, onError } = callbacks
  const form = new FormData()
  form.append('file',   file)
  form.append('source', source)

  let doneReceived = false
  let streamError = ''

  await _fetchSSE(
    '/api/dataset/upload',
    form,
    (event) => {
      if      (event.type === 'progress') onProgress?.(event.step, event.pct)
      else if (event.type === 'done') {
        doneReceived = true
        onDone?.(event.chunks, event.filename)
      }
      else if (event.type === 'error') {
        streamError = event.data || '上传失败'
        onError?.(streamError)
      }
    },
    onError,
    { isFormData: true },
  )

  if (streamError) {
    throw new Error(streamError)
  }
  if (!doneReceived) {
    throw new Error('上传流程未正常结束，请查看后端日志')
  }
}

// ── 测试集生成（SSE 进度流） ─────────────────────────────────────────────────
/**
 * @param callbacks {{
 *   onLoading(msg),
 *   onProgress(current, total, item),
 *   onDone(dataset, savedPath),
 *   onError(msg),
 * }}
 */
export async function generateTestset(count, sourceFilter, callbacks) {
  const { onLoading, onProgress, onDone, onError } = callbacks
  await _fetchSSE(
    '/api/testgen/generate',
    { count, source_filter: sourceFilter },
    (event) => {
      if      (event.type === 'loading')  onLoading?.(event.message)
      else if (event.type === 'progress') onProgress?.(event.current, event.total, event.item)
      else if (event.type === 'done')     onDone?.(event.dataset, event.saved_path)
      else if (event.type === 'error')    onError?.(event.data)
    },
    onError,
  )
}

export const testgenAPI = {
  listDatasetFiles: () => api.get('/testgen/dataset-files'),
  appendToDatasetFile: (targetFile, dataset) => api.post('/testgen/append', { target_file: targetFile, dataset }),
}

// ── 通用 SSE 请求 ─────────────────────────────────────────────────────────────
async function _fetchSSE(url, body, onEvent, onError, opts = {}) {
  try {
    const isFormData = opts.isFormData || false
    const token = getToken()
    const headers = isFormData ? {} : { 'Content-Type': 'application/json' }
    if (token) {
      headers.Authorization = `Bearer ${token}`
    }
    const response = await fetch(url, {
      method:  'POST',
      headers,
      body:    isFormData ? body : JSON.stringify(body),
    })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)

    const reader  = response.body.getReader()
    const decoder = new TextDecoder()
    let   buffer  = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop()
      for (const line of lines) {
        if (!line.startsWith('data: ')) continue
        try { onEvent(JSON.parse(line.slice(6))) } catch { /* skip */ }
      }
    }
  } catch (err) {
    onError?.(err.message || '网络错误')
  }
}
