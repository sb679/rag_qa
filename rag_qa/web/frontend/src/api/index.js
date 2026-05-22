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
  listResiduals: (params = {}) => api.get('/dataset/residuals', { params }),
  cleanupResiduals: (payload) => api.post('/dataset/residuals/cleanup', payload),
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
  submit: (payload) => api.post('/feedback/submit', payload),
  cancel: (sessionId, messageIndex, userId) =>
    api.post('/feedback/cancel', { session_id: sessionId, message_index: messageIndex, user_id: userId }),
  getStats: () => api.get('/feedback/stats'),
  updateStatus: (payload) => api.post('/feedback/status', payload),
}

// ── 流式对话（RAG + LLM 对比） ───────────────────────────────────────────────
/**
 * @param callbacks {{
 *   onRetrievalInfo(info),  // 检索过程信息
 *   onToken(char),          // RAG 答案字符
 *   onLlmToken(char),       // LLM 对比答案字符
 *   onDone(data),
 *   onError(msg),
 *   signal?: AbortSignal,   // 可选：用于中断本次请求
 * }}
 */
export async function streamChat(query, sessionId, sourceFilter, includeSourceDetails, callbacks, options = {}) {
  const { onRetrievalInfo, onToken, onLlmToken, onDone, onError, signal } = callbacks || {}
  const { enableCompare = false } = options
  await _fetchSSE(
    '/api/chat/send',
    {
      query,
      session_id: sessionId,
      source_filter: sourceFilter,
      include_source_details: includeSourceDetails !== false,
      enable_compare: !!enableCompare,
    },
    (event) => {
      if      (event.type === 'retrieval_info') onRetrievalInfo?.(event.data)
      else if (event.type === 'token')          onToken?.(event.data)
      else if (event.type === 'llm_token')      onLlmToken?.(event.data)
      else if (event.type === 'done')           onDone?.(event.data)
      else if (event.type === 'error')          onError?.(event.data)
    },
    onError,
    { signal },
  )
}

export async function streamChatWithImage(query, imageFile, sessionId, sourceFilter, includeSourceDetails, callbacks, options = {}) {
  const { onRetrievalInfo, onToken, onLlmToken, onDone, onError, signal } = callbacks || {}
  const { enableCompare = false } = options
  const form = new FormData()
  form.append('query', query || '')
  if (sessionId) form.append('session_id', sessionId)
  if (sourceFilter) form.append('source_filter', sourceFilter)
  form.append('include_source_details', includeSourceDetails !== false ? 'true' : 'false')
  form.append('enable_compare', enableCompare ? 'true' : 'false')
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
    { isFormData: true, signal },
  )
}

export async function streamCompareChat(query, callbacks) {
  const { onToken, onDone, onError, signal } = callbacks || {}
  await _fetchSSE(
    '/api/chat/compare',
    { query },
    (event) => {
      if      (event.type === 'llm_token') onToken?.(event.data)
      else if (event.type === 'done')      onDone?.(event.data)
      else if (event.type === 'error')     onError?.(event.data)
    },
    onError,
    { signal },
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

export const wechatAnnotatorAPI = {
  listArticles: (accountId = '') => api.get('/wechat-annotator/articles', { params: accountId ? { account_id: accountId } : {} }),
  listAgentTasks: (limit = 20) => api.get('/wechat-annotator/agent/tasks', { params: { limit } }),
  getAgentTask: (taskId) => api.get(`/wechat-annotator/agent/tasks/${encodeURIComponent(taskId)}`),
  getEvaluationHistory: (limit = 12) => api.get('/wechat-annotator/agent/evaluation/history', { params: { limit } }),
  getEvaluationHistoryCompare: (accountId = '') => api.get('/wechat-annotator/agent/evaluation/history/compare', { params: accountId ? { account_id: accountId } : {} }),
  rerunEvaluationHistory: (historyId) => api.post(`/wechat-annotator/agent/evaluation/history/${encodeURIComponent(historyId)}/rerun`),
  getAgentSessionState: () => api.get('/wechat-annotator/agent/session-state'),
  saveAgentSessionState: (state) => api.put('/wechat-annotator/agent/session-state', { state }),
  clearAgentSessionState: () => api.delete('/wechat-annotator/agent/session-state'),
  retryAgentTask: (taskId) => api.post(`/wechat-annotator/agent/tasks/${encodeURIComponent(taskId)}/retry`),
  searchAccounts: (keyword = '') => api.get('/wechat-annotator/accounts/search', { params: { q: keyword } }),
  listDesktopProfiles: (operatorId = '') => api.get('/wechat-annotator/desktop/profiles', { params: operatorId ? { operator_id: operatorId } : {} }),
  deleteDesktopProfile: (profileName, operatorId = '') => api.delete(`/wechat-annotator/desktop/profiles/${encodeURIComponent(profileName)}`, {
    params: operatorId ? { operator_id: operatorId } : {},
  }),
  getArticle: (accountId, articleId) => api.get(`/wechat-annotator/articles/${encodeURIComponent(accountId)}/${encodeURIComponent(articleId)}`),
  applyInstruction: (accountId, articleId, instruction) => api.post(
    `/wechat-annotator/articles/${encodeURIComponent(accountId)}/${encodeURIComponent(articleId)}/apply-instruction`,
    { instruction },
  ),
  autoFillAnnotations: (accountId, articleId, overwriteExisting = false) => api.post(
    `/wechat-annotator/articles/${encodeURIComponent(accountId)}/${encodeURIComponent(articleId)}/autofill`,
    { overwrite_existing: !!overwriteExisting },
  ),
  downloadHighResImage: (accountId, articleId, imageId) => api.post(
    `/wechat-annotator/articles/${encodeURIComponent(accountId)}/${encodeURIComponent(articleId)}/images/${encodeURIComponent(imageId)}/download-hires`,
  ),
  getKeptImagesExportMeta: (accountId, articleId) => api.get(
    `/wechat-annotator/articles/${encodeURIComponent(accountId)}/${encodeURIComponent(articleId)}/export-kept-images`,
    { params: { metadata_only: true } },
  ),
  exportKeptImages: (accountId, articleId) => api.get(
    `/wechat-annotator/articles/${encodeURIComponent(accountId)}/${encodeURIComponent(articleId)}/export-kept-images`,
    { responseType: 'blob' },
  ),
  saveAnnotations: (accountId, articleId, annotations, lastInstruction = '') => api.put(
    `/wechat-annotator/articles/${encodeURIComponent(accountId)}/${encodeURIComponent(articleId)}/annotations`,
    { annotations, last_instruction: lastInstruction },
  ),
}

export async function streamWechatDesktopCapture(payload, callbacks = {}, options = {}) {
  const {
    onLoading, onDesktopReady, onChatSelected, onHistoryOpened, onArticleOpened,
    onCaptureStarted, onAutoScrolled, onCaptureStep, onProfileSaved, onCaptureFinished,
    onImportStart, onImportDone, onLog, onDone, onError,
  } = callbacks
  await _fetchSSE(
    '/api/wechat-annotator/desktop/capture/stream',
    payload,
    (event) => {
      if      (event.type === 'loading') onLoading?.(event)
      else if (event.type === 'desktop_ready') onDesktopReady?.(event)
      else if (event.type === 'chat_selected') onChatSelected?.(event)
      else if (event.type === 'history_opened') onHistoryOpened?.(event)
      else if (event.type === 'article_opened') onArticleOpened?.(event)
      else if (event.type === 'capture_started') onCaptureStarted?.(event)
      else if (event.type === 'auto_scrolled') onAutoScrolled?.(event)
      else if (event.type === 'capture_step') onCaptureStep?.(event)
      else if (event.type === 'profile_saved') onProfileSaved?.(event)
      else if (event.type === 'capture_finished') onCaptureFinished?.(event)
      else if (event.type === 'import_start') onImportStart?.(event)
      else if (event.type === 'import_done') onImportDone?.(event)
      else if (event.type === 'log') onLog?.(event)
      else if (event.type === 'done') onDone?.(event)
      else if (event.type === 'error') onError?.(event.data)
    },
    onError,
    { signal: options.signal },
  )
}

export async function streamWechatCrawlByArticleUrls(payload, callbacks = {}, options = {}) {
  const { onLoading, onResolved, onProgress, onItemDone, onDone, onError } = callbacks
  await _fetchSSE(
    '/api/wechat-annotator/crawl/article-urls/stream',
    payload,
    (event) => {
      if      (event.type === 'loading') onLoading?.(event)
      else if (event.type === 'resolved') onResolved?.(event)
      else if (event.type === 'progress') onProgress?.(event)
      else if (event.type === 'item_done') onItemDone?.(event)
      else if (event.type === 'done') onDone?.(event)
      else if (event.type === 'error') onError?.(event.data)
    },
    onError,
    { signal: options.signal },
  )
}

export async function streamWechatCrawlByHistoryAccount(payload, callbacks = {}, options = {}) {
  const { onLoading, onResolved, onProgress, onItemDone, onDone, onError } = callbacks
  await _fetchSSE(
    '/api/wechat-annotator/crawl/account-history/stream',
    payload,
    (event) => {
      if      (event.type === 'loading') onLoading?.(event)
      else if (event.type === 'resolved') onResolved?.(event)
      else if (event.type === 'progress') onProgress?.(event)
      else if (event.type === 'item_done') onItemDone?.(event)
      else if (event.type === 'done') onDone?.(event)
      else if (event.type === 'error') onError?.(event.data)
    },
    onError,
    { signal: options.signal },
  )
}

export async function streamWechatAgentCommand(payload, callbacks = {}, options = {}) {
  const { onLoading, onParsed, onStepStart, onStepDone, onNote, onDone, onError } = callbacks
  await _fetchSSE(
    '/api/wechat-annotator/agent/stream',
    payload,
    (event) => {
      if      (event.type === 'loading') onLoading?.(event)
      else if (event.type === 'parsed') onParsed?.(event)
      else if (event.type === 'step_start') onStepStart?.(event)
      else if (event.type === 'step_done') onStepDone?.(event)
      else if (event.type === 'agent_note') onNote?.(event)
      else if (event.type === 'done') onDone?.(event)
      else if (event.type === 'error') onError?.(event.data)
    },
    onError,
    { signal: options.signal },
  )
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
      signal:  opts.signal,
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
    // 用户主动 abort（例如切换会话）不算错误
    if (err?.name === 'AbortError') return
    onError?.(err.message || '网络错误')
  }
}
