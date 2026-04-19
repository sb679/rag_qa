<template>
  <div class="chat-layout">

    <!-- ═══════════════════════════════════════════════════════
         左侧：3-tab 功能侧边栏
    ════════════════════════════════════════════════════════════ -->
    <div class="sidebar" :class="{ collapsed: !sidebarOpen }">
      <div class="sidebar-pin" @click="sidebarOpen = !sidebarOpen" title="折叠/展开">
        <el-icon><ArrowLeft v-if="sidebarOpen" /><ArrowRight v-else /></el-icon>
      </div>

      <template v-if="sidebarOpen">
        <el-tabs v-model="activeTab" class="sidebar-tabs">

          <!-- ── Tab 1：会话列表 ── -->
          <el-tab-pane name="sessions">
            <template #label>
              <el-tooltip content="会话列表" placement="right" :show-after="300">
                <el-icon><ChatDotRound /></el-icon>
              </el-tooltip>
            </template>

            <el-button type="primary" :icon="Plus" class="new-session-btn" @click="createSession">
              新建对话
            </el-button>

            <div class="session-list">
              <div
                v-for="s in sessions" :key="s.session_id"
                class="session-item" :class="{ active: s.session_id === currentSessionId }"
                @click="switchSession(s.session_id)"
              >
                <div class="s-meta">
                  <div class="s-date">{{ fmtDate(s.updated_at) }}</div>
                  <div class="s-count">{{ s.message_count }} 条消息</div>
                </div>
                <el-button text size="small" :icon="Delete" class="s-del"
                  @click.stop="removeSession(s.session_id)" />
              </div>
              <div v-if="!sessions.length" class="empty-hint">暂无历史会话</div>
            </div>
          </el-tab-pane>

          <!-- ── Tab 2：数据集管理 ── -->
          <el-tab-pane v-if="isSupervisor" name="dataset">
            <template #label>
              <el-tooltip content="增量添加文档" placement="right" :show-after="300">
                <el-icon><FolderAdd /></el-icon>
              </el-tooltip>
            </template>

            <div class="tab-title">增量添加文档</div>
            <el-select v-model="uploadSource" class="source-select" placeholder="选择来源">
              <el-option label="采矿 (mining)" value="mining" />
            </el-select>

            <el-upload
              class="uploader"
              drag
              multiple
              :auto-upload="false"
              :show-file-list="false"
              accept=".pdf,.docx,.ppt,.pptx,.txt,.md,.jpg,.jpeg,.png,.webp,.bmp,.gif"
              :on-change="onFileSelected"
            >
              <el-icon size="32" color="#c0c4cc"><Upload /></el-icon>
              <div class="upload-text">拖拽文件到此处<br><small>支持 PDF / Word / PPT / TXT / 图片</small></div>
            </el-upload>

            <div v-if="uploadFiles.length" class="selected-file-list">
              <div v-for="(file, index) in uploadFiles" :key="`${file.name}-${index}`" class="selected-file">
                <el-icon><Document /></el-icon>
                <span>{{ file.name }}</span>
              </div>
            </div>

            <el-button
              v-if="uploadFiles.length"
              type="success"
              :loading="isUploading"
              class="process-btn"
              @click="doUpload"
            >{{ isUploading ? '处理中…' : '开始向量化入库' }}</el-button>

            <div v-if="uploadSteps.length" class="upload-steps">
              <div v-for="(step, i) in uploadSteps" :key="i" class="upload-step">
                <el-icon color="#67c23a"><SuccessFilled /></el-icon>
                {{ step }}
              </div>
              <el-progress v-if="isUploading" :percentage="uploadPct" :show-text="false"
                stroke-width="6" style="margin-top:6px" />
            </div>

            <div v-if="uploadError" class="upload-error">{{ uploadError }}</div>
          </el-tab-pane>

          <!-- ── Tab 3：测试集生成 ── -->
          <el-tab-pane v-if="isSupervisor" name="testgen">
            <template #label>
              <el-tooltip content="测试集生成" placement="right" :show-after="300">
                <el-icon><DataAnalysis /></el-icon>
              </el-tooltip>
            </template>

            <div class="tab-title">测试集生成</div>
            <div class="tg-label">模型：Randeng-BART-139M-QG</div>

            <div class="tg-count-row">
              <span>生成数量</span>
              <el-input-number v-model="tgCount" :min="1" :max="20" :step="1" size="small" />
            </div>

            <div class="tg-count-row">
              <span>知识来源</span>
              <el-select v-model="tgSource" size="small" placeholder="选择来源" style="width: 140px">
                <el-option label="全部来源" value="" />
                <el-option v-for="src in tgSources" :key="src" :label="src" :value="src" />
              </el-select>
            </div>

            <el-button
              type="primary"
              :loading="isGenerating"
              :icon="MagicStick"
              class="process-btn"
              @click="doGenerate"
              :disabled="isGenerating"
            >{{ isGenerating ? `生成中 (${tgCurrent}/${tgTotal})` : '开始生成' }}</el-button>

            <el-progress
              v-if="isGenerating"
              :percentage="tgTotal ? Math.round(tgCurrent/tgTotal*100) : 0"
              status="striped"
              striped-flow
              :duration="10"
              stroke-width="8"
              style="margin: 8px 0"
            />

            <!-- 生成结果列表 -->
            <div v-if="tgItems.length" class="tg-result">
              <div class="tg-result-head">
                已生成 {{ tgItems.length }} 条
                <div>
                  <el-button text :icon="Download" size="small" @click="exportDataset">导出 JSON</el-button>
                  <el-button text size="small" @click="openAppendDialog">追加到已有文件</el-button>
                </div>
              </div>
              <div v-for="(item, i) in tgItems" :key="i" class="tg-item">
                <div class="tg-q">Q{{ item.id }}. {{ item.question }}</div>
                <div class="tg-c">{{ truncate(item.context, 80) }}</div>
              </div>
            </div>
          </el-tab-pane>

        </el-tabs>
      </template>
    </div>

    <!-- ═══════════════════════════════════════════════════════
         中间：聊天区域
    ════════════════════════════════════════════════════════════ -->
    <div class="chat-main">
      <div class="messages-wrap" ref="messagesWrap">

        <!-- 欢迎屏 -->
        <div v-if="!messages.length" class="welcome">
          <div class="welcome-shell">
            <div class="welcome-badge">
              <span>RAG</span>
              <small>mine safety copilot</small>
            </div>
            <div class="welcome-icon">⛏</div>
            <h2>EduRAG 采矿安全助手</h2>
            <p>基于《采矿安全手册》的专业知识问答，并提供通用 LLM 对比回答</p>
            <div class="example-grid">
              <div v-for="q in examples" :key="q" class="ex-card" @click="fillAndSend(q)">
                {{ q }}
              </div>
            </div>
          </div>
        </div>

        <!-- 消息列表 -->
        <template v-else>
          <div v-for="msg in messages" :key="msg.id" class="msg-row" :class="msg.role">
            <div class="avatar" :class="msg.role">
              <span v-if="msg.role==='user'">你</span>
              <span v-else>RAG</span>
            </div>
             <div class="bubble-wrap">
                 <div v-if="msg.role === 'assistant' && msg.meta?.query_type" class="decision-pill-row">
                   <span class="decision-pill" :class="msg.meta.query_type === '专业咨询' ? 'pro' : 'general'">
                     {{ msg.meta.query_type === '专业咨询' ? '专业知识判定' : '通用知识判定' }}
                   </span>
                   <span v-if="msg.meta.strategy" class="decision-strategy">{{ msg.meta.strategy }}</span>
                 </div>
               <div class="bubble" :class="msg.role" v-html="renderMd(msg.content)"></div>
               <!-- 元数据条（仅助手消息） -->
               <div v-if="msg.role === 'assistant' && msg.meta" class="msg-meta">
                 <el-tag :type="msg.meta.query_type === '专业咨询' ? 'primary' : 'success'"
                   size="small" effect="plain">{{ msg.meta.query_type }}</el-tag>
                 <el-tag v-if="msg.meta.strategy" type="warning" size="small" effect="plain">
                   {{ msg.meta.strategy }}
                 </el-tag>
                 <span class="meta-time">⏱ {{ formatDuration(msg.meta.time) }}</span>
                 <span class="bubble-ts">{{ msg.time }}</span>
               </div>
               <!-- 反馈按钮（仅助手消息） -->
               <div v-if="msg.role === 'assistant'" class="feedback-actions">
                 <el-button
                   v-for="option in feedbackOptions"
                   :key="option.type"
                   text
                   size="small"
                   :type="msg.feedback?.type === option.type ? option.buttonType : 'info'"
                   @click="handleFeedback(msg, option.type)"
                 >
                   <el-icon><component :is="option.icon" /></el-icon>
                   {{ option.label }}
                 </el-button>
               </div>
             </div>
            <div v-if="msg.role==='user'" class="avatar user"><span>你</span></div>
          </div>

          <!-- 打字动画 -->
          <div v-if="isTyping" class="msg-row assistant">
            <div class="avatar assistant"><span>RAG</span></div>
            <div class="bubble assistant typing">
              <span class="dot"/><span class="dot"/><span class="dot"/>
            </div>
          </div>
        </template>
      </div>

      <!-- 输入区 -->
      <div class="input-zone">
        <div v-if="questionImageFile" class="question-image-bar">
          <div class="question-image-preview">
            <img :src="questionImagePreview" alt="待发送图片预览" />
            <div class="question-image-meta">
              <span>{{ questionImageFile.name }}</span>
              <small>图片将先做 OCR，再进入检索</small>
            </div>
          </div>
          <el-button text type="danger" @click="clearQuestionImage">移除图片</el-button>
        </div>

        <el-input v-model="inputText" type="textarea" :rows="3" resize="none"
          placeholder="输入问题… (Enter 发送，Shift+Enter 换行)"
          :disabled="isLoading" class="msg-input"
          @keydown.enter.exact.prevent="doSend"
          @keydown.shift.enter.exact="inputText += '\n'"
        />
        <div class="input-foot">
          <div class="input-options">
            <span class="option-label">来源详情</span>
            <el-switch
              v-model="includeSourceDetails"
              inline-prompt
              active-text="开"
              inactive-text="关"
              size="small"
            />
          </div>
          <el-upload
            class="question-image-uploader"
            :auto-upload="false"
            :show-file-list="false"
            accept="image/*"
            :on-change="onQuestionImageSelected"
          >
            <el-button :icon="Upload">图片提问</el-button>
          </el-upload>
          <span class="char-count">{{ inputText.length }} 字</span>
          <el-button type="primary" :loading="isLoading" :icon="Promotion"
            :disabled="!inputText.trim() && !questionImageFile" @click="doSend">发送</el-button>
        </div>
      </div>
    </div>

    <!-- ═══════════════════════════════════════════════════════
         右侧：分析面板（专业咨询时显示）
    ════════════════════════════════════════════════════════════ -->
    <transition name="panel-slide">
      <div class="analysis-panel" v-if="showPanel">

        <div class="panel-head"><el-icon><Search /></el-icon>检索分析</div>

        <!-- 查询分析 -->
        <div v-if="panelInfo" class="p-section">
          <div class="p-label">查询类型 / 检索策略</div>
          <div class="tag-row">
            <el-tag :type="panelInfo.query_type === '专业咨询' ? 'primary' : 'success'"
              effect="light" size="small">{{ panelInfo.query_type }}</el-tag>
            <el-tag v-if="panelInfo.strategy" type="warning" effect="light" size="small">
              {{ panelInfo.strategy }}
            </el-tag>
            <el-tag
              v-if="panelInfo.error_type"
              :type="panelInfo.error_type === 'rate_limit' ? 'danger' : (panelInfo.error_type === 'auth' ? 'warning' : 'info')"
              effect="light"
              size="small"
            >
              {{ formatRetrievalErrorType(panelInfo.error_type) }}<template v-if="panelInfo.error_code">({{ panelInfo.error_code }})</template>
            </el-tag>
          </div>
          <div v-if="panelInfo.error_message" class="error-hint">{{ truncate(panelInfo.error_message, 80) }}</div>
          <div v-if="panelInfo.query_type === '专业咨询'" class="count-row">
            <div class="cnt"><div class="cnt-n">{{ panelInfo.candidate_count }}</div><div class="cnt-l">初始召回</div></div>
            <el-icon color="#dcdfe6"><ArrowRight /></el-icon>
            <div class="cnt"><div class="cnt-n blue">{{ panelInfo.final_count }}</div><div class="cnt-l">精选</div></div>
            <span class="cost-time">{{ formatDuration(panelInfo.time) }}</span>
          </div>
        </div>

        <!-- 来源文档 -->
        <div v-if="panelInfo?.sources?.length" class="p-section">
          <div class="p-label">参考来源（{{ panelInfo.sources.length }} 篇）</div>
          <div v-for="(doc, i) in panelInfo.sources" :key="i" class="src-card" @click="openSourceDetail(doc, i)">
            <div class="src-top">
              <span class="src-idx">[{{ i+1 }}]</span>
              <span class="src-name">{{ doc.source }}</span>
              <span class="src-score">{{ Math.round(doc.score*100) }}%</span>
            </div>
            <div class="score-bar"><div class="score-fill" :style="{width: doc.score*100+'%'}"/></div>
            <div class="src-file" v-if="doc.file_name">📄 {{ doc.file_name }}</div>
            <div class="src-text">{{ truncate(doc.content, 120) }}</div>
            <div class="src-tip">点击查看完整父块与命中子块</div>
          </div>
        </div>

        <!-- 通用 LLM 对比回答 -->
        <div v-if="panelInfo?.query_type === '专业咨询'" class="p-section llm-section">
          <div class="p-label llm-label">
            <el-icon><ChatRound /></el-icon>
            通用 LLM 对比回答
            <el-tooltip content="不使用检索文档，直接由大模型回答，用于与 RAG 回答对比" placement="top">
              <el-icon color="#c0c4cc" style="cursor:help"><QuestionFilled /></el-icon>
            </el-tooltip>
          </div>
          <div v-if="!llmAnswer && isLoading" class="llm-loading">
            <el-icon class="spin"><Loading /></el-icon> 生成中…
          </div>
          <div v-else-if="llmAnswer" class="llm-content" v-html="renderMd(llmAnswer)"></div>
          <div v-else class="llm-placeholder">发送问题后此处显示对比回答</div>
        </div>

        <!-- 无专业检索时 -->
        <div v-if="panelInfo?.query_type === '通用知识'" class="no-retrieval">
          <el-icon size="36" color="#c0c4cc"><InfoFilled /></el-icon>
          <p>通用知识查询</p>
          <p class="hint">由 LLM 直接回答，无需检索文档</p>
        </div>

      </div>
    </transition>

    <el-dialog
      v-model="sourceDetailVisible"
      width="720px"
      title="参考来源详情"
      destroy-on-close
    >
      <template v-if="sourceDetail">
        <div class="detail-head">
          <el-tag type="primary" effect="light">来源：{{ sourceDetail.source }}</el-tag>
          <el-tag v-if="sourceDetail.file_name" type="info" effect="light">文件：{{ sourceDetail.file_name }}</el-tag>
          <el-tag type="success" effect="light">相似度：{{ Math.round((sourceDetail.score || 0) * 100) }}%</el-tag>
        </div>

        <div class="detail-section">
          <div class="detail-title">父块（完整）</div>
          <pre class="detail-block">{{ sourceDetail.parent_content || sourceDetail.content }}</pre>
        </div>

        <div class="detail-section" v-if="sourceDetail.matched_children?.length">
          <div class="detail-title">命中子块（{{ sourceDetail.matched_children.length }}）</div>
          <div v-for="(child, idx) in sourceDetail.matched_children" :key="idx" class="child-block">
            <div class="child-head">子块 {{ idx + 1 }} · 相似分 {{ Number(child.score || 0).toFixed(4) }}</div>
            <pre class="detail-block">{{ child.content }}</pre>
          </div>
        </div>
      </template>
    </el-dialog>

    <el-dialog v-model="appendDialogVisible" title="追加到已有问答对文件" width="520px">
      <el-form label-width="100px">
        <el-form-item label="目标文件">
          <el-select v-model="appendTargetFile" style="width: 100%" placeholder="选择要追加的文件">
            <el-option
              v-for="item in appendFiles"
              :key="item.name"
              :label="item.name"
              :value="item.name"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="appendDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="appendLoading" @click="confirmAppendToFile">确认追加</el-button>
      </template>
    </el-dialog>

  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import { marked } from 'marked'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Delete, Promotion, Search, ArrowLeft, ArrowRight,
  Loading, InfoFilled, ChatDotRound, FolderAdd, DataAnalysis,
  Upload, Document, SuccessFilled, Download, MagicStick,
  ChatRound, QuestionFilled, CircleCheck, CircleClose, Warning, Edit,
} from '@element-plus/icons-vue'
import { sessionAPI, streamChat, streamChatWithImage, uploadDocument, generateTestset, feedbackAPI, knowledgeAPI, testgenAPI, chatAPI } from '@/api'
import { useStore } from '@/store'

marked.setOptions({ breaks: true })

// ── 布局状态 ──────────────────────────────────────────────────────────────────
const sidebarOpen = ref(true)
const activeTab   = ref('sessions')
const showPanel   = computed(() =>
  !!panelInfo.value || (isLoading.value && currentQuery.value)
)

// ── 聊天状态 ──────────────────────────────────────────────────────────────────
const sessions         = ref([])
const currentSessionId = ref(null)
const messages         = ref([])
const inputText        = ref('')
const isLoading        = ref(false)
const isTyping         = ref(false)
const currentQuery     = ref('')
const questionImageFile = ref(null)
const questionImagePreview = ref('')
const includeSourceDetails = ref(false)

// 当前活跃消息（流式填充）
let _activeMsg = null

// 右侧面板
const panelInfo = ref(null)
const llmAnswer = ref('')
const sourceDetailVisible = ref(false)
const sourceDetail = ref(null)

const defaultExamples = [
  '矿井通风安全有哪些规定？',
  '瓦斯超标应该如何处理？',
  '顶板管理的主要安全措施？',
  '爆破作业安全规程是什么？',
  '矿山水害预防措施？',
  '采矿特种作业人员资质要求？',
]
const examples = ref([...defaultExamples])

const feedbackOptions = [
  { type: 'like', label: '点赞', icon: CircleCheck, buttonType: 'success' },
  { type: 'dislike', label: '点踩', icon: CircleClose, buttonType: 'danger' },
  { type: 'partial_correct', label: '部分正确', icon: Warning, buttonType: 'warning' },
  { type: 'correction', label: '纠错', icon: Edit, buttonType: 'primary' },
]

// ── 数据集管理状态 ────────────────────────────────────────────────────────────
const uploadFiles  = ref([])
const uploadSource = ref('mining')
const isUploading  = ref(false)
const uploadSteps  = ref([])
const uploadPct    = ref(0)
const uploadError  = ref('')

// ── 测试集生成状态 ────────────────────────────────────────────────────────────
const tgCount      = ref(20)
const tgSource     = ref('')
const tgSources    = ref([])
const isGenerating = ref(false)
const tgCurrent    = ref(0)
const tgTotal      = ref(0)
const tgItems      = ref([])
const tgDataset    = ref([])
const appendDialogVisible = ref(false)
const appendTargetFile = ref('')
const appendFiles = ref([])
const appendLoading = ref(false)

// ── 工具函数 ──────────────────────────────────────────────────────────────────
const { state, isSupervisor } = useStore()
const SESSION_GREETING = '江西理工大学的学子永不认输！很高兴为你服务，请问今天想了解哪方面的采矿安全问题？'
const renderMd = (t) => marked.parse(t || '')
const truncate = (s, n) => s?.length > n ? s.slice(0, n) + '…' : (s || '')
const formatRetrievalErrorType = (type) => {
  if (type === 'auth') return '鉴权错误'
  if (type === 'rate_limit') return '限流错误'
  if (type === 'upstream') return '上游服务异常'
  return '检索异常'
}
const formatDuration = (seconds) => {
  const value = Number(seconds) || 0
  if (value < 1) return `${Math.max(1, Math.round(value * 1000))}ms`
  if (value < 10) return `${value.toFixed(2)}s`
  return `${value.toFixed(1)}s`
}
const nowTime  = () => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
const fmtDate  = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  return `${(d.getMonth()+1).toString().padStart(2,'0')}-${d.getDate().toString().padStart(2,'0')} ` +
         `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}
const messagesWrap = ref(null)
const scrollBottom = () => nextTick(() => {
  if (messagesWrap.value) messagesWrap.value.scrollTop = messagesWrap.value.scrollHeight
})

function openSourceDetail(doc, index) {
  sourceDetail.value = {
    ...doc,
    index,
  }
  sourceDetailVisible.value = true
}

function dispatchActivityUpdate(detail = {}) {
  window.dispatchEvent(new CustomEvent('rag-activity-updated', { detail }))
}

function dispatchFeedbackUpdate(detail = {}) {
  window.dispatchEvent(new CustomEvent('rag-feedback-updated', { detail }))
}

// ── 反馈提交 ──────────────────────────────────────────────────────────────────
async function submitFeedback(msgId, type, content = null) {
  try {
    const msg = messages.value.find(m => m.id === msgId)
    if (!msg) return

    const messageIndex = messages.value.findIndex(m => m.id === msgId)
    if (messageIndex < 0) return

    await feedbackAPI.submit(
      currentSessionId.value,
      messageIndex,
      state.user.employee_id,
      type,
      content
    )

    msg.feedback = { type, content }
    dispatchFeedbackUpdate({ sessionId: currentSessionId.value, messageIndex, type })
    ElMessage.success(type === 'correction' ? '纠错已提交' : '反馈已提交')
  } catch (err) {
    ElMessage.error(err.response?.data?.detail || '反馈提交失败')
  }
}

async function handleFeedback(msg, type) {
  if (type === 'correction') {
    try {
      const { value } = await ElMessageBox.prompt('请补充正确说法或需要修正的内容', '提交纠错', {
        confirmButtonText: '提交',
        cancelButtonText: '取消',
        inputPlaceholder: '例如：顶板支护应改为...'
        ,
        inputType: 'textarea',
        inputValidator: (value) => !!value?.trim() || '请填写纠错内容',
      })
      await submitFeedback(msg.id, type, value.trim())
    } catch (err) {
      if (err !== 'cancel' && err !== 'close') {
        ElMessage.error('纠错提交失败')
      }
    }
    return
  }

  await submitFeedback(msg.id, type)
}

// ── 会话管理 ──────────────────────────────────────────────────────────────────
async function loadSessions() {
  try { sessions.value = (await sessionAPI.list()).data.sessions || [] } catch {}
}
async function createSession() {
  try {
    currentSessionId.value = (await sessionAPI.create()).data.session_id
    messages.value = [buildGreetingMessage()]
    panelInfo.value = null
    llmAnswer.value = ''
    await loadSessions()
    ElMessage.success('新建对话')
  } catch { ElMessage.error('创建失败') }
}
async function switchSession(id) {
  currentSessionId.value = id
  messages.value = []; panelInfo.value = null; llmAnswer.value = ''
  try {
    const res = await sessionAPI.messages(id)
    const raw = res.data.messages || []
    if (raw.length > 0) {
      messages.value = raw.map((m, i) => ({
        id:      i,
        role:    m.role,
        content: m.content,
        time:    m.time,
        meta:    m.meta || null,
      }))
      nextTick(scrollBottom)
    } else {
      messages.value = [buildGreetingMessage()]
      nextTick(scrollBottom)
    }
  } catch (e) { 
    console.warn('加载会话消息失败:', e)
  }
}

function buildGreetingMessage() {
  return {
    id: Date.now(),
    role: 'assistant',
    content: SESSION_GREETING,
    time: nowTime(),
    meta: null,
  }
}
async function removeSession(id) {
  try {
    await ElMessageBox.confirm('确定删除该对话吗？', '提示', { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' })
    await sessionAPI.remove(id)
    if (currentSessionId.value === id) { currentSessionId.value = null; messages.value = [] }
    await loadSessions()
    ElMessage.success('已删除')
  } catch (e) { if (e !== 'cancel') ElMessage.error('删除失败') }
}

// ── 发送消息 ──────────────────────────────────────────────────────────────────
async function doSend() {
  const query = inputText.value.trim()
  if (!query && !questionImageFile.value) return
  if (isLoading.value) return

  const requestStartedAt = performance.now()
  inputText.value = ''
  isLoading.value = true
  isTyping.value  = true
  panelInfo.value = null
  llmAnswer.value = ''
  currentQuery.value = query || (questionImageFile.value ? `图片提问：${questionImageFile.value.name}` : '')

  messages.value.push({
    id: Date.now(),
    role: 'user',
    content: query || (questionImageFile.value ? `图片提问：${questionImageFile.value.name}` : ''),
    time: nowTime(),
  })
  scrollBottom()

  // 占位助手消息
  _activeMsg = { id: Date.now() + 1, role: 'assistant', content: '', meta: null, time: nowTime() }
  let msgPushed = false

  const imageFile = questionImageFile.value
  const callbacks = {
    onRetrievalInfo(info) {
      panelInfo.value = info
      isTyping.value  = false
      if (!msgPushed) { messages.value.push(_activeMsg); msgPushed = true }
      _activeMsg.meta = {
        query_type: info.query_type,
        strategy: info.strategy,
        time: info.time,
      }
      scrollBottom()
    },
    onToken(char) {
      if (!msgPushed) { isTyping.value = false; messages.value.push(_activeMsg); msgPushed = true }
      _activeMsg.content += char
      scrollBottom()
    },
    onLlmToken(char) {
      llmAnswer.value += char
    },
    onDone(data) {
      if (data?.session_id) currentSessionId.value = data.session_id
      const elapsedSeconds = Math.max(0, (performance.now() - requestStartedAt) / 1000)
      if (_activeMsg && panelInfo.value) {
        panelInfo.value = {
          ...panelInfo.value,
          time: elapsedSeconds,
        }
        _activeMsg.meta = {
          query_type: panelInfo.value.query_type,
          strategy:   panelInfo.value.strategy,
          time:       elapsedSeconds,
        }
      }
      isLoading.value = false
      isTyping.value  = false
      dispatchActivityUpdate({ sessionId: currentSessionId.value, query: currentQuery.value })
      loadSessions()
    },
    onError(msg) {
      ElMessage.error('请求失败：' + msg)
      isLoading.value = false; isTyping.value = false
    },
  }

  try {
    if (imageFile) {
      await streamChatWithImage(
        query,
        imageFile,
        currentSessionId.value,
        null,
        includeSourceDetails.value,
        callbacks,
      )
    } else {
      await streamChat(
        query,
        currentSessionId.value,
        null,
        includeSourceDetails.value,
        callbacks,
      )
    }
  } finally {
    clearQuestionImage()
  }
}
function fillAndSend(q) { inputText.value = q; doSend() }

function onQuestionImageSelected(file) {
  const rawFile = file.raw
  if (!rawFile) return
  clearQuestionImage()
  questionImageFile.value = rawFile
  questionImagePreview.value = URL.createObjectURL(rawFile)
}

function clearQuestionImage() {
  if (questionImagePreview.value) {
    URL.revokeObjectURL(questionImagePreview.value)
  }
  questionImageFile.value = null
  questionImagePreview.value = ''
}

// ── 数据集上传 ────────────────────────────────────────────────────────────────
function onFileSelected(file, fileList) {
  uploadFiles.value = (fileList || [])
    .map(item => item.raw)
    .filter(Boolean)
  uploadSteps.value = []
  uploadPct.value   = 0
  uploadError.value = ''
}
async function doUpload() {
  if (!isSupervisor.value) {
    ElMessage.warning('仅主管可上传知识库文件')
    return
  }
  if (!uploadFiles.value.length) return
  isUploading.value  = true
  uploadSteps.value  = []
  uploadPct.value    = 0
  uploadError.value = ''

  try {
    const files = [...uploadFiles.value]
    let totalChunks = 0

    for (let index = 0; index < files.length; index += 1) {
      const file = files[index]
      uploadSteps.value.push(`开始处理：${file.name}`)

      await uploadDocument(file, uploadSource.value, {
        onProgress(step, pct) {
          uploadSteps.value.push(step)
          uploadPct.value = Math.min(100, Math.round(((index + pct / 100) / files.length) * 100))
        },
        onDone(chunks, filename) {
          totalChunks += chunks
          uploadSteps.value.push(`✅ 完成！${filename} 新增 ${chunks} 个向量块`)
          uploadPct.value = Math.round(((index + 1) / files.length) * 100)
        },
        onError(msg) {
          uploadSteps.value.push(`❌ ${file.name}：${msg}`)
        },
      })
    }

    ElMessage.success(`已完成 ${files.length} 个文件入库，共 ${totalChunks} 个向量块`)
    uploadFiles.value = []
    window.dispatchEvent(new CustomEvent('rag-knowledge-updated', {
      detail: { source: uploadSource.value, files: files.map(file => file.name), chunks: totalChunks },
    }))
  } catch (err) {
    const message = err?.message || '上传失败'
    uploadError.value = message
    ElMessage.error('上传失败：' + message)
  } finally {
    isUploading.value = false
  }
}

// ── 测试集生成 ────────────────────────────────────────────────────────────────
async function doGenerate() {
  if (!isSupervisor.value) {
    ElMessage.warning('仅主管可生成测试问答对')
    return
  }
  isGenerating.value = true
  tgCurrent.value    = 0
  tgTotal.value      = tgCount.value
  tgItems.value      = []
  tgDataset.value    = []

  await generateTestset(tgCount.value, tgSource.value, {
    onLoading(msg)  { ElMessage.info(msg) },
    onProgress(cur, total, item) {
      tgCurrent.value = cur
      tgTotal.value   = total
      tgItems.value.push(item)
    },
    onDone(dataset, savedPath) {
      tgDataset.value    = dataset
      isGenerating.value = false
      ElMessage.success(`生成完成！已保存到 ${savedPath}`)
    },
    onError(msg) {
      ElMessage.error('生成失败：' + msg)
      isGenerating.value = false
    },
  })
}

function exportDataset() {
  const blob = new Blob([JSON.stringify(tgDataset.value, null, 2)], { type: 'application/json' })
  const a    = document.createElement('a')
  a.href     = URL.createObjectURL(blob)
  a.download = `testset_${Date.now()}.json`
  a.click()
}

async function initTestgenSources() {
  if (!isSupervisor.value) return
  try {
    const res = await knowledgeAPI.status()
    const sources = (res?.data?.knowledge?.sources || []).map(item => item.name).filter(Boolean)
    tgSources.value = Array.from(new Set(sources))
    if (!tgSource.value && tgSources.value.includes('mining')) {
      tgSource.value = 'mining'
    }
  } catch {
    tgSources.value = []
  }
}

async function loadExamples() {
  try {
    const res = await chatAPI.examples()
    const items = res?.data?.items || []
    if (items.length >= 6) {
      examples.value = items.slice(0, 6)
    }
  } catch {
    examples.value = [...defaultExamples]
  }
}

async function openAppendDialog() {
  if (!tgDataset.value.length) {
    ElMessage.warning('请先生成问答对再执行追加')
    return
  }
  try {
    const res = await testgenAPI.listDatasetFiles()
    appendFiles.value = res?.data?.files || []
    appendTargetFile.value = appendFiles.value[0]?.name || ''
    appendDialogVisible.value = true
  } catch (err) {
    ElMessage.error(err?.response?.data?.detail || '获取文件列表失败')
  }
}

async function confirmAppendToFile() {
  if (!appendTargetFile.value) {
    ElMessage.warning('请选择目标文件')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确认将当前 ${tgDataset.value.length} 条问答对追加到 ${appendTargetFile.value} 吗？`,
      '追加确认',
      { type: 'warning', confirmButtonText: '确认追加', cancelButtonText: '取消' },
    )
    appendLoading.value = true
    const res = await testgenAPI.appendToDatasetFile(appendTargetFile.value, tgDataset.value)
    const data = res?.data || {}
    ElMessage.success(`追加成功：新增 ${data.appended || 0} 条，总计 ${data.total || 0} 条`)
    appendDialogVisible.value = false
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      ElMessage.error(err?.response?.data?.detail || '追加失败')
    }
  } finally {
    appendLoading.value = false
  }
}

onMounted(async () => {
  await loadSessions()
  if (!isSupervisor.value && activeTab.value !== 'sessions') {
    activeTab.value = 'sessions'
  }
  await initTestgenSources()
  await loadExamples()
})
</script>

<style scoped>
/* ── 整体布局 ─────────────────────────────────────────────────────────────── */
.chat-layout {
  display: flex;
  height: calc(100vh - 60px);
  overflow: hidden;
  position: relative;
}

/* ── 左侧侧边栏 ───────────────────────────────────────────────────────────── */
.sidebar {
  width: 230px; min-width: 230px;
  background: #fff;
  border-right: 1px solid #e4e7ed;
  display: flex; flex-direction: column;
  transition: width .2s, min-width .2s;
  overflow: hidden; position: relative;
}
.sidebar.collapsed { width: 44px; min-width: 44px; }
.sidebar-pin {
  position: absolute; top: 10px; right: 8px; z-index: 10;
  cursor: pointer; color: #909399; padding: 4px;
  border-radius: 4px; transition: color .15s;
}
.sidebar-pin:hover { color: #409eff; }

:deep(.sidebar-tabs)              { flex: 1; overflow: hidden; }
:deep(.sidebar-tabs .el-tabs__header) { padding: 8px 8px 0; margin: 0; }
:deep(.sidebar-tabs .el-tabs__content) { padding: 8px; overflow-y: auto; height: calc(100% - 48px); }
:deep(.sidebar-tabs .el-tabs__item)   { padding: 0 12px; }

.new-session-btn { width: 100%; margin-bottom: 10px; }
.session-list    { display: flex; flex-direction: column; gap: 4px; }
.session-item    {
  display: flex; align-items: center; gap: 6px;
  padding: 8px; border-radius: 8px; cursor: pointer;
  transition: background .15s;
}
.session-item:hover  { background: #f5f7fa; }
.session-item.active { background: #ecf5ff; }
.s-meta   { flex: 1; min-width: 0; }
.s-date   { font-size: 12px; color: #303133; }
.s-count  { font-size: 11px; color: #909399; }
.s-del    { opacity: 0; transition: opacity .15s; }
.session-item:hover .s-del { opacity: 1; }
.empty-hint { font-size: 12px; color: #c0c4cc; text-align: center; padding: 16px 0; }

/* 数据/测试 tab 通用 */
.tab-title   { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 10px; }
.source-select { width: 100%; margin-bottom: 8px; }
:deep(.uploader .el-upload-dragger) {
  padding: 16px; border-radius: 8px; text-align: center;
}
.upload-text { font-size: 12px; color: #909399; margin-top: 6px; line-height: 1.5; }
.selected-file {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #606266;
  background: #f5f7fa; padding: 6px 10px; border-radius: 6px; margin: 8px 0;
  overflow: hidden; white-space: nowrap; text-overflow: ellipsis;
}
.process-btn  { width: 100%; margin: 8px 0; }
.upload-steps { display: flex; flex-direction: column; gap: 4px; }
.upload-step  { font-size: 12px; color: #606266; display: flex; align-items: center; gap: 4px; }

/* 测试集 */
.tg-label    { font-size: 11px; color: #909399; margin-bottom: 8px; }
.tg-count-row {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 8px; font-size: 13px; color: #606266;
}
.tg-result   { margin-top: 10px; }
.tg-result-head {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 12px; color: #606266; font-weight: 600; margin-bottom: 6px;
}
.tg-item     { background: #f8f9fb; border-radius: 6px; padding: 8px; margin-bottom: 6px; }
.tg-q        { font-size: 12px; color: #303133; font-weight: 500; margin-bottom: 4px; }
.tg-c        { font-size: 11px; color: #909399; }

/* ── 聊天区 ───────────────────────────────────────────────────────────────── */
.chat-main {
  flex: 1; display: flex; flex-direction: column; min-width: 0;
  background:
    radial-gradient(circle at 12% 18%, rgba(34, 197, 94, .14), transparent 38%),
    radial-gradient(circle at 88% 78%, rgba(59, 130, 246, .14), transparent 42%),
    linear-gradient(145deg, #f8fafc 0%, #eef2ff 42%, #eff6ff 100%);
  animation: bgFlow 12s ease-in-out infinite alternate;
}
.messages-wrap {
  flex: 1; overflow-y: auto; padding: 24px 28px;
  display: flex; flex-direction: column; gap: 18px;
}

/* 欢迎 */
.welcome       { text-align: center; margin: auto; padding: 32px 0; }
.welcome-shell {
  display: inline-flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 28px 30px; border-radius: 24px;
  background: linear-gradient(180deg, rgba(255,255,255,.92), rgba(248,250,252,.95));
  box-shadow: 0 18px 40px rgba(15, 23, 42, .08);
  border: 1px solid rgba(148, 163, 184, .18);
}
.welcome-badge {
  display: inline-flex; flex-direction: column; align-items: center; gap: 2px;
  padding: 8px 14px; border-radius: 999px;
  background: linear-gradient(135deg, #0f172a, #2563eb);
  color: #fff; box-shadow: 0 10px 24px rgba(37, 99, 235, .24);
}
.welcome-badge span { font-size: 13px; font-weight: 700; letter-spacing: .12em; }
.welcome-badge small { font-size: 10px; opacity: .82; text-transform: uppercase; }
.welcome-icon  {
  width: 68px; height: 68px; border-radius: 22px;
  display: flex; align-items: center; justify-content: center;
  background: linear-gradient(145deg, #fff8e1, #ffe6a6);
  font-size: 34px; box-shadow: inset 0 1px 0 rgba(255,255,255,.8);
}
.welcome h2    { font-size: 22px; font-weight: 800; letter-spacing: .02em; color: #0f172a; margin-bottom: 4px; }
.welcome p     { font-size: 13px; color: #64748b; margin-bottom: 14px; }
.example-grid  { display: grid; grid-template-columns: repeat(3,1fr); gap: 8px; max-width: 540px; margin: 0 auto; }
.ex-card       {
  background: linear-gradient(180deg, #fff, #f8fafc); border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 12px 14px; font-size: 13px; color: #334155; cursor: pointer;
  transition: all .18s; text-align: left; box-shadow: 0 8px 22px rgba(15, 23, 42, .04);
}
.ex-card:hover { border-color: #60a5fa; color: #2563eb; transform: translateY(-2px); box-shadow: 0 12px 24px rgba(37, 99, 235, .12); }

/* 消息行 */
.msg-row       { display: flex; align-items: flex-start; gap: 10px; }
.msg-row.user  { flex-direction: row-reverse; }
.avatar        {
  width: 34px; height: 34px; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-weight: 800; font-size: 12px; letter-spacing: .04em;
  box-shadow: 0 10px 18px rgba(15, 23, 42, .10);
}
.avatar.user      { background: linear-gradient(135deg, #2563eb, #38bdf8); color: #fff; }
.avatar.assistant { background: linear-gradient(135deg, #111827, #f59e0b); color: #fff; }

.bubble-wrap { max-width: 65%; display: flex; flex-direction: column; gap: 4px; }
.decision-pill-row {
  display: flex; align-items: center; gap: 8px; margin: 2px 2px 0;
}
.decision-pill {
  font-size: 11px; font-weight: 700; letter-spacing: .02em;
  padding: 2px 10px; border-radius: 999px;
}
.decision-pill.pro {
  color: #1d4ed8; background: rgba(37, 99, 235, .14); border: 1px solid rgba(37, 99, 235, .22);
}
.decision-pill.general {
  color: #047857; background: rgba(16, 185, 129, .14); border: 1px solid rgba(16, 185, 129, .24);
}
.decision-strategy {
  font-size: 11px; color: #64748b; padding: 2px 8px; border-radius: 999px;
  background: rgba(148, 163, 184, .15); border: 1px solid rgba(148, 163, 184, .2);
}
.bubble {
  background: #fff; border: 1px solid #e2e8f0;
  border-radius: 16px; padding: 12px 16px;
  font-size: 14px; line-height: 1.75;
  box-shadow: 0 10px 30px rgba(15, 23, 42, .05); word-break: break-word;
  animation: bubbleIn .24s ease-out;
}
.bubble.assistant { background: linear-gradient(180deg, #fff, #fbfdff); }
.bubble.user { background: linear-gradient(135deg, #2563eb, #60a5fa); border-color: #2563eb; color: #fff; }

/* Markdown 内容 */
.bubble :deep(p)      { margin: 0 0 8px; }
.bubble :deep(p:last-child) { margin-bottom: 0; }
.bubble :deep(strong) { font-weight: 600; }
.bubble :deep(ol),.bubble :deep(ul) { padding-left: 20px; margin: 6px 0; }
.bubble :deep(li)     { margin: 3px 0; }
.bubble.user :deep(*) { color: #fff; }

/* 消息元数据 */
.msg-meta { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.meta-time { font-size: 11px; color: #909399; }
.bubble-ts { font-size: 11px; color: #c0c4cc; margin-left: auto; }
.feedback-actions { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
.feedback-actions :deep(.el-button) { padding-left: 0; padding-right: 0; }

/* 打字动画 */
.typing { padding: 14px 16px; }
.dot    {
  display: inline-block; width: 7px; height: 7px; background: #c0c4cc;
  border-radius: 50%; margin: 0 2px; animation: bounce .9s infinite;
}
.dot:nth-child(2) { animation-delay: .15s; }
.dot:nth-child(3) { animation-delay: .3s; }
@keyframes bounce { 0%,60%,100% { transform: translateY(0); } 30% { transform: translateY(-8px); } }

/* 输入区 */
.input-zone { padding: 14px 20px; background: #fff; border-top: 1px solid #e4e7ed; }
.question-image-bar {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
  margin-bottom: 10px; padding: 10px 12px;
  border: 1px solid rgba(64, 158, 255, .18); border-radius: 14px;
  background: linear-gradient(135deg, rgba(64, 158, 255, .08), rgba(103, 194, 58, .08));
}
.question-image-preview {
  display: flex; align-items: center; gap: 10px; min-width: 0;
}
.question-image-preview img {
  width: 44px; height: 44px; object-fit: cover; border-radius: 10px;
  border: 1px solid rgba(148, 163, 184, .28); background: #fff;
}
.question-image-meta { display: flex; flex-direction: column; min-width: 0; }
.question-image-meta span {
  font-size: 13px; font-weight: 600; color: #303133;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.question-image-meta small { font-size: 12px; color: #909399; }
.input-foot { display: flex; justify-content: flex-end; align-items: center; margin-top: 8px; gap: 12px; }
.input-options { display: inline-flex; align-items: center; gap: 8px; margin-right: auto; }
.option-label { font-size: 12px; color: #606266; }
.question-image-uploader { display: inline-flex; }
.char-count { font-size: 12px; color: #c0c4cc; }

/* ── 右侧分析面板 ─────────────────────────────────────────────────────────── */
.analysis-panel {
  width: 330px; min-width: 330px; background: #fff;
  border-left: 1px solid #e4e7ed; overflow-y: auto;
}
.panel-head {
  display: flex; align-items: center; gap: 6px;
  padding: 14px 16px 10px;
  font-size: 14px; font-weight: 600; color: #303133;
  border-bottom: 1px solid #f0f2f5;
  position: sticky; top: 0; background: #fff; z-index: 1;
}
.p-section { padding: 12px 16px 0; }
.p-label   { font-size: 12px; color: #909399; margin-bottom: 6px; }
.tag-row   { display: flex; gap: 6px; flex-wrap: wrap; }
.error-hint { margin-top: 6px; font-size: 12px; color: #e6a23c; line-height: 1.4; }

.count-row { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.cnt       { text-align: center; }
.cnt-n     { font-size: 20px; font-weight: 700; color: #606266; }
.cnt-n.blue { color: #409eff; }
.cnt-l     { font-size: 11px; color: #909399; }
.cost-time { font-size: 11px; color: #909399; margin-left: auto; }

.src-card  {
  background: #f8f9fb; border-radius: 8px; padding: 10px; margin-top: 8px;
  cursor: pointer; transition: box-shadow .15s, transform .15s;
}
.src-card:hover { box-shadow: 0 8px 20px rgba(15, 23, 42, .10); transform: translateY(-1px); }
.src-top   { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.src-idx   { font-size: 11px; color: #909399; background: #e4e7ed; padding: 1px 5px; border-radius: 3px; }
.src-name  { flex: 1; font-size: 12px; color: #606266; font-weight: 500; }
.src-score { font-size: 12px; font-weight: 700; color: #409eff; }
.score-bar { height: 4px; background: #e4e7ed; border-radius: 2px; margin-bottom: 8px; }
.score-fill { height: 100%; background: linear-gradient(90deg,#409eff,#79bbff); border-radius: 2px; transition: width .4s; }
.src-file  { font-size: 11px; color: #64748b; margin-bottom: 6px; }
.src-text  { font-size: 12px; color: #909399; line-height: 1.6; }
.src-tip   { font-size: 11px; color: #409eff; margin-top: 6px; }

.detail-head { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.detail-section { margin-top: 10px; }
.detail-title { font-size: 13px; color: #303133; font-weight: 700; margin-bottom: 6px; }
.detail-block {
  margin: 0;
  padding: 10px;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  line-height: 1.6;
  color: #4b5563;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
}
.child-block { margin-bottom: 10px; }
.child-head { font-size: 12px; color: #64748b; margin-bottom: 4px; }

/* LLM 对比 */
.llm-section  { border-top: 1px dashed #e4e7ed; margin-top: 12px; padding-top: 12px; }
.llm-label    { display: flex; align-items: center; gap: 6px; }
.llm-loading  { font-size: 13px; color: #909399; display: flex; align-items: center; gap: 6px; padding: 8px 0; }
.llm-content  { font-size: 13px; color: #606266; line-height: 1.75; }
.llm-content :deep(p)     { margin: 0 0 8px; }
.llm-content :deep(strong){ font-weight: 600; }
.llm-content :deep(ol),.llm-content :deep(ul) { padding-left: 18px; margin: 4px 0; }
.llm-placeholder { font-size: 12px; color: #c0c4cc; padding: 8px 0; }

.no-retrieval { text-align: center; padding: 32px 16px; color: #c0c4cc; font-size: 13px; }
.no-retrieval p { margin-top: 8px; }
.no-retrieval .hint { font-size: 12px; }

/* 旋转动画 */
.spin { animation: rotate 1s linear infinite; }
@keyframes rotate { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

/* 面板入场 */
.panel-slide-enter-active,.panel-slide-leave-active { transition: width .3s, min-width .3s, opacity .3s; overflow: hidden; }
.panel-slide-enter-from,.panel-slide-leave-to       { width: 0; min-width: 0; opacity: 0; }

@keyframes bubbleIn {
  from { opacity: .2; transform: translateY(6px); }
  to { opacity: 1; transform: translateY(0); }
}

@keyframes bgFlow {
  from { background-position: 0% 0%, 100% 100%, 0% 0%; }
  to { background-position: 6% 10%, 90% 80%, 0% 0%; }
}
</style>
