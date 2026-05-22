// 跨组件实例共享的聊天会话内存
//
// 为什么需要模块级单例：
//  - ChatView 在路由切换时会销毁重建；如果 messages / 在飞请求 / 流式回答
//    都放在 <script setup> 内，重建后全丢失。
//  - 把这些状态托管在一个模块级 reactive 对象里，所有 ChatView 实例共享，
//    路由切走再切回也能继续看到正在生成的回答与历史输入。
//
// 状态结构：
//  sessionStates[sid] = {
//    messages: [],        // 渲染消息列表
//    panelInfo: null,     // 右侧分析面板
//    panelVisible: false, // 是否手动展开右侧分析面板
//    llmAnswer: '',       // 通用 LLM 对比回答
//    isLoading: false,    // 是否正在请求
//    isTyping: false,     // 是否在等首包
//    currentQuery: '',    // 本次问题文案
//    activeMsg: null,     // 流式正在写入的助手消息引用
//    requestError: '',    // 最近一次请求失败文案
//    lastFailedQuery: '', // 最近一次失败时的问题文案
//    lastFailedHadImage: false, // 最近一次失败是否包含图片
//  }
import { reactive, ref } from 'vue'

export const sessionStates = reactive({})
export const currentSessionId = ref(null)
const CHAT_TRANSIENT_SNAPSHOT_KEY = 'chat:transient-sessions'

export function ensureSessionState(sid) {
  if (!sid) return null
  if (!sessionStates[sid]) {
    sessionStates[sid] = {
      messages: [],
      panelInfo: null,
      panelVisible: false,
      llmAnswer: '',
      isLoading: false,
      isTyping: false,
      currentQuery: '',
      activeMsg: null,
      requestError: '',
      lastFailedQuery: '',
      lastFailedHadImage: false,
    }
  }
  return sessionStates[sid]
}

export function dropSessionState(sid) {
  if (sid && sessionStates[sid]) delete sessionStates[sid]
  if (currentSessionId.value === sid) currentSessionId.value = null
}

function isTransientSessionState(state) {
  return !!(
    state?.isLoading ||
    state?.isTyping ||
    state?.activeMsg ||
    state?.requestError ||
    state?.lastFailedQuery ||
    state?.lastFailedHadImage
  )
}

function cloneMessages(messages) {
  if (!Array.isArray(messages)) return []
  return messages.map((message) => ({
    id: message?.id,
    role: message?.role,
    content: message?.content || '',
    time: message?.time || '',
    meta: message?.meta ? { ...message.meta } : null,
    feedback: message?.feedback ? { ...message.feedback } : null,
  }))
}

function buildInterruptedSessionState(rawState) {
  const messages = cloneMessages(rawState?.messages)
  const currentQuery = rawState?.currentQuery || rawState?.lastFailedQuery || ''
  const panelInfo = rawState?.panelInfo ? { ...rawState.panelInfo } : null
  const llmAnswer = rawState?.llmAnswer || ''
  let interruptedAssistant = false

  if (messages.length > 0) {
    const lastMessage = messages[messages.length - 1]
    if (lastMessage?.role === 'assistant') {
      lastMessage.meta = {
        ...(lastMessage.meta || {}),
        user_query: (lastMessage.meta && lastMessage.meta.user_query) || currentQuery,
        stream_status: 'interrupted',
        stream_error: '页面刷新导致流式回答中断，请重新发送。',
      }
      interruptedAssistant = true
    }
  }

  if (!interruptedAssistant && currentQuery) {
    messages.push({
      id: `restored-assistant-${Date.now()}`,
      role: 'assistant',
      content: '',
      time: rawState?.activeMsg?.time || '',
      meta: {
        query_type: panelInfo?.query_type || rawState?.activeMsg?.meta?.query_type || '专业咨询',
        strategy: panelInfo?.strategy || rawState?.activeMsg?.meta?.strategy || '',
        user_query: currentQuery,
        time: Number(panelInfo?.time || rawState?.activeMsg?.meta?.time || 0),
        panel_info: panelInfo,
        compare_answer: rawState?.activeMsg?.meta?.compare_answer || '',
        stream_status: 'interrupted',
        stream_error: '页面刷新导致流式回答中断，请重新发送。',
        had_image: !!rawState?.lastFailedHadImage,
      },
      feedback: null,
    })
  }

  return {
    messages,
    panelInfo,
    panelVisible: false,
    llmAnswer,
    isLoading: false,
    isTyping: false,
    currentQuery,
    activeMsg: null,
    requestError: '页面刷新导致上一轮回答中断，请重新发送。',
    lastFailedQuery: currentQuery,
    lastFailedHadImage: !!rawState?.lastFailedHadImage,
  }
}

export function persistTransientChatSnapshot() {
  try {
    const sessions = {}
    for (const [sid, state] of Object.entries(sessionStates)) {
      if (!isTransientSessionState(state)) continue
      sessions[sid] = {
        messages: cloneMessages(state.messages),
        panelInfo: state.panelInfo ? { ...state.panelInfo } : null,
        llmAnswer: state.llmAnswer || '',
        isLoading: !!state.isLoading,
        isTyping: !!state.isTyping,
        currentQuery: state.currentQuery || '',
        activeMsg: state.activeMsg
          ? {
              ...state.activeMsg,
              meta: state.activeMsg.meta ? { ...state.activeMsg.meta } : null,
              feedback: state.activeMsg.feedback ? { ...state.activeMsg.feedback } : null,
            }
          : null,
        requestError: state.requestError || '',
        lastFailedQuery: state.lastFailedQuery || '',
        lastFailedHadImage: !!state.lastFailedHadImage,
      }
    }

    const sessionIds = Object.keys(sessions)
    if (sessionIds.length === 0) {
      sessionStorage.removeItem(CHAT_TRANSIENT_SNAPSHOT_KEY)
      return false
    }

    const payload = {
      savedAt: Date.now(),
      currentSessionId: currentSessionId.value,
      sessions,
    }
    sessionStorage.setItem(CHAT_TRANSIENT_SNAPSHOT_KEY, JSON.stringify(payload))
    return true
  } catch (_) {
    return false
  }
}

export function restoreTransientChatSnapshot() {
  try {
    const raw = sessionStorage.getItem(CHAT_TRANSIENT_SNAPSHOT_KEY)
    if (!raw) return false
    const payload = JSON.parse(raw)
    if (!payload || typeof payload !== 'object' || !payload.sessions || typeof payload.sessions !== 'object') {
      sessionStorage.removeItem(CHAT_TRANSIENT_SNAPSHOT_KEY)
      return false
    }

    for (const [sid, rawState] of Object.entries(payload.sessions)) {
      sessionStates[sid] = buildInterruptedSessionState(rawState)
    }
    if (payload.currentSessionId && payload.sessions[payload.currentSessionId]) {
      currentSessionId.value = payload.currentSessionId
    }
    sessionStorage.removeItem(CHAT_TRANSIENT_SNAPSHOT_KEY)
    return true
  } catch (_) {
    try { sessionStorage.removeItem(CHAT_TRANSIENT_SNAPSHOT_KEY) } catch (_) {}
    return false
  }
}
