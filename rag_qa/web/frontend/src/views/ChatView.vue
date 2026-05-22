<template>
  <div class="chat-layout motion-ready">

    <!-- ═══════════════════════════════════════════════════════
         左侧：3-tab 功能侧边栏
    ════════════════════════════════════════════════════════════ -->
    <div class="sidebar" :class="{ collapsed: !sidebarOpen }">
      <div class="sidebar-pin" @click="sidebarOpen = !sidebarOpen" title="折叠/展开">
        <el-icon><ArrowLeft v-if="sidebarOpen" /><ArrowRight v-else /></el-icon>
      </div>

      <template v-if="sidebarOpen">
        <div class="sidebar-overview">
          <div class="sidebar-kicker">Workbench</div>
          <div class="sidebar-title">检索与会话工作台</div>
          <div class="sidebar-meta">
            <span>{{ sessions.length }} 个会话</span>
            <span>{{ currentSessionId ? '已连接当前对话' : '等待创建对话' }}</span>
          </div>
        </div>

        <div v-if="workspaceActionFeedback" class="workspace-feedback" :class="workspaceActionFeedback.tone">
          <div class="workspace-feedback-main">
            <el-icon class="workspace-feedback-icon" size="18"><component :is="workspaceActionFeedback.icon" /></el-icon>
            <div class="workspace-feedback-copy">
              <div class="workspace-feedback-title">{{ workspaceActionFeedback.title }}</div>
              <div class="workspace-feedback-desc">{{ workspaceActionFeedback.desc }}</div>
            </div>
          </div>
          <el-button text size="small" @click="clearWorkspaceActionFeedback">关闭</el-button>
        </div>

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

            <div class="upload-compact-head">
              <div class="tab-title">批量添加文档</div>
              <div class="upload-source-badge">默认分类：采矿知识库</div>
            </div>
            <div class="upload-hint">支持一次拖入多篇文档。上传进行中继续拖入的新文档会自动加入队列。</div>

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

            <div v-if="uploadFiles.length" class="selected-file-list compact">
              <div class="selected-file-summary">当前队列 {{ uploadFiles.length }} 篇</div>
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
            >{{ isUploading ? '队列处理中…' : '开始向量化入库' }}</el-button>

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
      <div class="chat-stage">
        <div v-if="!messages.length" class="chat-hero-bar">
          <div class="chat-hero-copy">
            <div class="chat-kicker">Mine safety copilot</div>
            <h1>把问答、来源证据和人工反馈放进同一个交互界面</h1>
            <p>当前界面优先展示检索过程、证据命中与反馈闭环，让系统更像一款产品，而不是单纯的聊天框。</p>
          </div>
          <div class="chat-hero-pills">
            <div class="chat-hero-pill">
              <span>当前会话</span>
              <strong>{{ currentSessionId ? '已激活' : '未创建' }}</strong>
            </div>
            <div class="chat-hero-pill">
              <span>消息数量</span>
              <strong>{{ messages.length }}</strong>
            </div>
            <div class="chat-hero-pill">
              <span>来源详情</span>
              <strong>{{ includeSourceDetails ? '已开启' : '已关闭' }}</strong>
            </div>
          </div>
        </div>

        <div class="messages-wrap" ref="messagesWrap" @scroll.passive="_onMessagesScroll">

          <!-- 欢迎屏 -->
          <div v-if="!messages.length" class="welcome">
            <div class="welcome-shell">
              <div class="welcome-badge">
                <span>RAG</span>
                <small>mine safety copilot</small>
              </div>
              <div class="welcome-icon">⛏</div>
              <h2>采矿安全智能问答助手</h2>
              <p>基于《采矿安全手册》的专业知识问答，可按需查看通用 LLM 对比回答</p>
              <div class="welcome-metrics">
                <div class="welcome-metric">
                  <strong>检索优先</strong>
                  <span>先给证据，再给答案</span>
                </div>
                <div class="welcome-metric">
                  <strong>来源可追溯</strong>
                  <span>支持父块与子块核查</span>
                </div>
                <div class="welcome-metric">
                  <strong>反馈闭环</strong>
                  <span>方便后续优化和复盘</span>
                </div>
              </div>
              <div class="example-grid">
                <div
                  v-for="item in examples"
                  :key="item.question"
                  class="ex-card"
                  :class="item.source"
                  @click="fillAndSend(item.question)"
                >
                  <div class="ex-card-title">{{ item.question }}</div>
                  <div class="ex-card-meta">{{ item.label }}</div>
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
                 <div class="bubble" :class="msg.role" v-html="renderMd(msg.content)"></div>
                 <!-- 元数据条（仅助手消息） -->
                 <div v-if="msg.role === 'assistant' && msg.meta" class="msg-meta">
                   <el-tag v-if="msg.meta.stream_status === 'interrupted'" type="danger" size="small" effect="light">
                     回答中断
                   </el-tag>
                   <span class="meta-time">⏱ {{ formatDuration(msg.meta.time) }}</span>
                   <span class="bubble-ts">{{ msg.time }}</span>
                 </div>
                 <div v-if="msg.role === 'assistant' && msg.meta?.stream_status === 'interrupted'" class="stream-interrupt-note">
                   <div class="stream-interrupt-copy">
                     <strong>这条回答在生成中断。</strong>
                     <span>{{ msg.meta.stream_error || '上游流式输出未完整返回，当前内容可能只是一部分。' }}</span>
                   </div>
                   <el-button
                     v-if="!msg.meta.had_image && msg.meta.user_query"
                     text
                     size="small"
                     type="primary"
                     @click="retryInterruptedMessage(msg)"
                   >重试该问题</el-button>
                 </div>
                 <!-- 反馈按钮（仅助手消息） -->
                 <div v-if="msg.role === 'assistant'" class="feedback-actions">
                   <el-button
                     v-if="msg.meta?.panel_info && (msg.meta.panel_info.sources?.length || msg.meta.panel_info.query_type)"
                     text
                     size="small"
                     type="primary"
                     @click="reopenPanel(msg)"
                   >
                     <el-icon><Search /></el-icon>
                     查看上下文
                   </el-button>
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
                 <div v-if="msg.role === 'assistant' && msg.feedback?.content" class="feedback-note">
                   <span class="feedback-note-label">已提交反馈：</span>
                   <span>{{ msg.feedback.content }}</span>
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
        <div v-if="!useUtilityRail" class="input-zone" :class="{ collapsed: composerCollapsed }">
          <div class="composer-head">
            <div>
              <div class="composer-title">提问输入区</div>
            </div>
            <div class="composer-head-actions">
              <el-button text size="small" class="composer-toggle" @click="toggleComposerCollapsed">
                <el-icon><ArrowDown v-if="composerCollapsed" /><ArrowUp v-else /></el-icon>
                {{ composerCollapsed ? '展开输入区' : '收起输入区' }}
              </el-button>
            </div>
          </div>

          <div v-if="composerCollapsed" class="composer-collapsed-bar">
            <span>{{ questionImageFile ? `已附带图片：${questionImageFile.name}` : '输入区已收起' }}</span>
            <el-button text size="small" type="primary" @click="toggleComposerCollapsed">点击展开</el-button>
          </div>

          <template v-else>

          <div class="hot-rank-board">
            <div class="hot-rank-head">
              <div>
                <div class="hot-rank-title">高频问题热搜</div>
                <div class="hot-rank-desc">按最近单天、三天、一周统计前五问题，点击即可直接提问。</div>
              </div>
              <div class="hot-rank-tabs">
                <el-button
                  v-for="window in hotQuestionWindows"
                  :key="window.key"
                  size="small"
                  :type="activeHotWindowKey === window.key ? 'primary' : 'default'"
                  @click="activeHotWindowKey = window.key"
                >{{ window.label }}</el-button>
              </div>
            </div>
            <div v-if="activeHotWindow?.items?.length" class="hot-rank-list">
              <button
                v-for="(item, index) in activeHotWindow.items"
                :key="`${activeHotWindow.key}-${item.question}`"
                type="button"
                class="hot-rank-item"
                @click="fillAndSend(item.question)"
              >
                <span class="hot-rank-index">{{ index + 1 }}</span>
                <span class="hot-rank-copy">
                  <strong>{{ item.question }}</strong>
                  <small>{{ item.label || hotQuestionLabel(activeHotWindow.days, item.count) }}</small>
                </span>
              </button>
            </div>
            <div v-else class="hot-rank-empty">当前时间窗下还没有足够的高频问题，已回退到普通引导问题。</div>
          </div>

          <div v-if="composerNotice" class="composer-status" :class="composerNotice.tone">
            <div class="composer-status-main">
              <el-icon class="composer-status-icon"><component :is="composerNotice.icon" /></el-icon>
              <div class="composer-status-copy">
                <div class="composer-status-title">{{ composerNotice.title }}</div>
                <div class="composer-status-desc">{{ composerNotice.desc }}</div>
              </div>
            </div>
            <el-button
              v-if="composerNotice.action"
              text
              size="small"
              :disabled="isLoading"
              @click="composerNotice.action()"
            >{{ composerNotice.actionLabel }}</el-button>
          </div>

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
            <el-button type="primary" :loading="isLoading" :icon="Promotion"
              :disabled="!inputText.trim() && !questionImageFile" @click="doSend">发送</el-button>
          </div>
          </template>
        </div>
      </div>
    </div>

    <template v-if="useUtilityRail">
      <div class="hot-rank-rail" :class="{ 'analysis-open': showPanel }">
        <transition name="rail-card-slide">
          <div v-if="hotRailOpen" class="chat-utility-card hot-rank-rail-card">
            <div class="rail-card-head">
              <div>
                <div class="rail-card-title">高频问题热搜</div>
                <div class="rail-card-desc">按最近单天、三天、一周统计前五问题，点击即可直接提问。</div>
              </div>
              <el-button text size="small" @click="hotRailOpen = false">收起</el-button>
            </div>
            <div class="hot-rank-tabs rail-card-tabs">
              <el-button
                v-for="window in hotQuestionWindows"
                :key="window.key"
                size="small"
                :type="activeHotWindowKey === window.key ? 'primary' : 'default'"
                @click="activeHotWindowKey = window.key"
              >{{ window.label }}</el-button>
            </div>
            <div v-if="activeHotWindow?.items?.length" class="hot-rank-list">
              <button
                v-for="(item, index) in activeHotWindow.items"
                :key="`${activeHotWindow.key}-${item.question}`"
                type="button"
                class="hot-rank-item"
                @click="handleHotQuestionSelect(item.question)"
              >
                <span class="hot-rank-index">{{ index + 1 }}</span>
                <span class="hot-rank-copy">
                  <strong>{{ item.question }}</strong>
                  <small>{{ item.label || hotQuestionLabel(activeHotWindow.days, item.count) }}</small>
                </span>
              </button>
            </div>
            <div v-else class="hot-rank-empty">当前时间窗下还没有足够的高频问题，已回退到普通引导问题。</div>
          </div>
        </transition>

        <div v-if="!hotRailOpen" class="chat-utility-fab-wrap">
          <el-tooltip content="展开高频热搜" placement="left">
            <button type="button" class="chat-utility-fab" @click="toggleHotRail">
              <el-icon><QuestionFilled /></el-icon>
            </button>
          </el-tooltip>
        </div>
      </div>

      <div class="composer-rail" :class="{ 'analysis-open': showPanel }">
        <transition name="rail-card-slide">
          <div v-if="composerRailOpen" class="chat-utility-card composer-rail-card">
            <div class="input-zone rail-zone" :class="{ collapsed: composerCollapsed }">
              <div class="composer-head">
                <div>
                  <div class="composer-title">提问输入区</div>
                </div>
                <div class="composer-head-actions">
                  <el-button text size="small" class="composer-toggle" @click="toggleComposerCollapsed">
                    <el-icon><ArrowDown v-if="composerCollapsed" /><ArrowUp v-else /></el-icon>
                    {{ composerCollapsed ? '展开输入区' : '收起输入区' }}
                  </el-button>
                  <el-button text size="small" class="composer-toggle" @click="composerRailOpen = false">挂起</el-button>
                </div>
              </div>

              <div v-if="composerCollapsed" class="composer-collapsed-bar">
                <span>{{ questionImageFile ? `已附带图片：${questionImageFile.name}` : '输入区已收起' }}</span>
                <el-button text size="small" type="primary" @click="toggleComposerCollapsed">点击展开</el-button>
              </div>

              <template v-else>
                <div v-if="composerNotice" class="composer-status" :class="composerNotice.tone">
                  <div class="composer-status-main">
                    <el-icon class="composer-status-icon"><component :is="composerNotice.icon" /></el-icon>
                    <div class="composer-status-copy">
                      <div class="composer-status-title">{{ composerNotice.title }}</div>
                      <div class="composer-status-desc">{{ composerNotice.desc }}</div>
                    </div>
                  </div>
                  <el-button
                    v-if="composerNotice.action"
                    text
                    size="small"
                    :disabled="isLoading"
                    @click="composerNotice.action()"
                  >{{ composerNotice.actionLabel }}</el-button>
                </div>

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
                  <el-button type="primary" :loading="isLoading" :icon="Promotion"
                    :disabled="!inputText.trim() && !questionImageFile" @click="doSend">发送</el-button>
                </div>
              </template>
            </div>
          </div>
        </transition>

        <div v-if="!composerRailOpen" class="chat-utility-fab-wrap">
          <el-tooltip content="展开提问输入区" placement="left">
            <button type="button" class="chat-utility-fab" @click="toggleComposerRail">
              <el-icon><Edit /></el-icon>
            </button>
          </el-tooltip>
        </div>
      </div>
    </template>

    <div v-if="panelAvailable && !showPanel" class="analysis-panel-fab-wrap">
      <el-tooltip content="展开检索分析" placement="left">
        <button type="button" class="analysis-panel-fab" @click="openPanelManually">
          <el-icon><Loading v-if="isLoading && currentQuery" class="spin" /><Search v-else /></el-icon>
        </button>
      </el-tooltip>
    </div>

    <!-- ═══════════════════════════════════════════════════════
         右侧：分析面板（专业咨询时显示）
    ════════════════════════════════════════════════════════════ -->
    <transition name="panel-slide">
      <div class="analysis-panel" v-if="showPanel">

        <div class="panel-head">
          <div class="panel-head-main"><el-icon><Search /></el-icon>检索分析</div>
          <el-button text size="small" @click="closePanel">收起</el-button>
        </div>

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
            <div class="cnt"><div class="cnt-n">{{ panelStrategyK(panelInfo) }}</div><div class="cnt-l">策略档位 k</div></div>
            <el-icon color="#dcdfe6"><ArrowRight /></el-icon>
            <div class="cnt"><div class="cnt-n">{{ panelContextLimit(panelInfo) }}</div><div class="cnt-l">父块上限 m</div></div>
            <el-icon color="#dcdfe6"><ArrowRight /></el-icon>
            <div class="cnt"><div class="cnt-n blue">{{ panelInfo.final_count }}</div><div class="cnt-l">最终父块</div></div>
            <span class="cost-time">{{ formatDuration(panelInfo.time) }}</span>
          </div>
          <div v-if="panelInfo.query_type === '专业咨询'" class="count-subrow">
            <span>直接命中子块 {{ panelDirectChildHits(panelInfo) }}</span>
            <span v-if="panelParentOnlyHits(panelInfo)">仅父块重排入选 {{ panelParentOnlyHits(panelInfo) }}</span>
          </div>
        </div>

        <!-- 来源文档 -->
        <div v-if="panelInfo?.sources?.length" class="p-section">
          <div class="p-label">命中证据（{{ panelInfo.sources.length }} 篇）</div>
          <div class="evidence-note">
            上方 k/m 只是当前策略的检索档位，不等于本次真实命中的子块数。右侧主分数表示原始问题直接命中的子块证据强弱；若显示“无直接子块证据”，表示该父块是靠重排入选。
          </div>
          <div v-if="panelInfo.evidence_note" class="evidence-summary">
            {{ panelInfo.evidence_note }}
          </div>
          <div v-for="(doc, i) in panelInfo.sources" :key="i" class="src-card" @click="openSourceDetail(doc, i)">
            <div class="src-top">
              <span class="src-idx">[{{ i+1 }}]</span>
              <span class="src-name">{{ doc.source }}</span>
              <span class="src-score">{{ docScoreLabel(doc) }}</span>
            </div>
            <div class="score-bar"><div class="score-fill" :style="{width: doc.score*100+'%'}"/></div>
            <div class="src-file" v-if="doc.file_name">📄 {{ doc.file_name }}</div>
            <div v-if="doc.evidence_note" class="src-evidence-flag" :class="evidenceClass(doc)">
              {{ doc.evidence_note }}
            </div>
            <div class="src-metrics">
              <span>检索分 {{ formatPercent(doc.search_score) }}</span>
              <span v-if="doc.rerank_score !== null && doc.rerank_score !== undefined">重排分 {{ formatSigned(doc.rerank_score) }}</span>
            </div>
            <div class="src-text">{{ truncate(doc.content, 120) }}</div>
            <div class="src-tip">点击查看完整父块与命中子块</div>
          </div>
        </div>

        <div v-else-if="panelEmptyState" class="no-retrieval panel-empty-state" :class="panelEmptyState.tone">
          <el-icon size="36"><component :is="panelEmptyState.icon" /></el-icon>
          <p>{{ panelEmptyState.title }}</p>
          <p class="hint">{{ panelEmptyState.desc }}</p>
          <el-button
            v-if="panelEmptyState.action"
            plain
            size="small"
            :type="panelEmptyState.actionType || 'primary'"
            @click="panelEmptyState.action()"
          >{{ panelEmptyState.actionLabel }}</el-button>
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
          <div v-if="compareLoading" class="llm-loading">
            <el-icon class="spin"><Loading /></el-icon> 生成中…
          </div>
          <div v-else-if="llmAnswer" class="llm-content" v-html="renderMd(llmAnswer)"></div>
          <div v-else class="llm-placeholder">
            <div>默认不生成对比回答，避免每次提问都额外触发一次通用模型。</div>
            <el-button type="primary" plain size="small" style="margin-top:10px" @click="requestCompareAnswer">
              查看该问题的通用 LLM 回答
            </el-button>
          </div>
          <div v-if="compareError" class="error-hint" style="margin-top:10px">{{ compareError }}</div>
          <div v-if="llmAnswer" class="llm-actions">
            <el-button text size="small" type="primary" @click="requestCompareAnswer">重新生成对比回答</el-button>
          </div>
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
      title="命中证据详情"
      destroy-on-close
    >
      <template v-if="sourceDetail">
        <div class="detail-head">
          <el-tag type="primary" effect="light">来源：{{ sourceDetail.source }}</el-tag>
          <el-tag v-if="sourceDetail.file_name" type="info" effect="light">文件：{{ sourceDetail.file_name }}</el-tag>
          <el-tag :type="sourceDetail.evidence_status === 'parent_rerank_only' ? 'warning' : 'success'" effect="light">{{ sourceDetailTagLabel(sourceDetail) }}</el-tag>
          <el-tag type="info" effect="light">检索分：{{ formatPercent(sourceDetail.search_score) }}</el-tag>
          <el-tag v-if="sourceDetail.rerank_score !== null && sourceDetail.rerank_score !== undefined" type="warning" effect="light">
            重排分：{{ formatSigned(sourceDetail.rerank_score) }}
          </el-tag>
        </div>

        <div class="detail-note">
          子块证据分只说明原始问题与这段文档中命中的子块相关，不等于系统已经具备足够依据给出安全、完整、可执行的结论。
        </div>
        <div v-if="sourceDetail.evidence_note" class="detail-note soft">
          {{ sourceDetail.evidence_note }}
        </div>

        <div class="detail-section">
          <div class="detail-title">父块（完整）</div>
          <pre class="detail-block">{{ sourceDetail.parent_content || sourceDetail.content }}</pre>
        </div>

        <div class="detail-section" v-if="sourceDetail.matched_children?.length">
          <div class="detail-title">命中子块（{{ sourceDetail.matched_children.length }}）</div>
          <div v-for="(child, idx) in sourceDetail.matched_children" :key="idx" class="child-block">
            <div class="child-head">子块 {{ idx + 1 }} · 检索分 {{ formatPercent(child.score) }} · 原始值 {{ Number(child.score || 0).toFixed(4) }}</div>
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
import { ref, reactive, computed, nextTick, onMounted, onUnmounted, watch } from 'vue'
import { marked } from 'marked'
import {
  Plus, Delete, Promotion, Search, ArrowLeft, ArrowRight, ArrowDown, ArrowUp,
  Loading, InfoFilled, ChatDotRound, FolderAdd, DataAnalysis,
  Upload, Document, SuccessFilled, Download, MagicStick,
  ChatRound, QuestionFilled, CircleCheck, CircleClose, Warning, Edit,
} from '@element-plus/icons-vue'
import { sessionAPI, streamChat, streamChatWithImage, streamCompareChat, uploadDocument, generateTestset, feedbackAPI, knowledgeAPI, testgenAPI, chatAPI } from '@/api'
import { useStore } from '@/store'
import {
  sessionStates,
  currentSessionId,
  ensureSessionState,
  dropSessionState,
  persistTransientChatSnapshot,
  restoreTransientChatSnapshot,
} from '@/store/chatSessions'

marked.setOptions({ breaks: true })

// ── 布局状态 ──────────────────────────────────────────────────────────────────
const sidebarOpen = ref(true)
const activeTab   = ref('sessions')
const useUtilityRail = ref(typeof window === 'undefined' ? true : window.innerWidth > 1180)
const hotRailOpen = ref(
  (() => {
    try {
      return localStorage.getItem('chat:hotRailOpen') === 'true'
    } catch (_) {
      return false
    }
  })()
)
const composerRailOpen = ref(
  (() => {
    try {
      return localStorage.getItem('chat:composerRailOpen') === 'true'
    } catch (_) {
      return false
    }
  })()
)
const composerCollapsed = ref(
  (() => {
    try {
      return localStorage.getItem('chat:composerCollapsed') === 'true'
    } catch (_) {
      return false
    }
  })()
)
// ── 聊天状态：per-session 缓存（来自 @/store/chatSessions，跨路由切换持久） ──
const sessions         = ref([])
const inputText        = ref('')
const questionImageFile = ref(null)
const questionImagePreview = ref('')
const includeSourceDetails = ref(
  (() => {
    try {
      const v = localStorage.getItem('chat:includeSourceDetails')
      // 未设置过时默认开启；仅当显式存为 'false' 才关闭
      return v === null ? true : v !== 'false'
    } catch (_) {
      return true
    }
  })()
)
watch(includeSourceDetails, (v) => {
  try { localStorage.setItem('chat:includeSourceDetails', v ? 'true' : 'false') } catch (_) {}
})
watch(hotRailOpen, (v) => {
  try { localStorage.setItem('chat:hotRailOpen', v ? 'true' : 'false') } catch (_) {}
})
watch(composerRailOpen, (v) => {
  try { localStorage.setItem('chat:composerRailOpen', v ? 'true' : 'false') } catch (_) {}
})
watch(composerCollapsed, (v) => {
  try { localStorage.setItem('chat:composerCollapsed', v ? 'true' : 'false') } catch (_) {}
})

function syncUtilityRailMode() {
  if (typeof window === 'undefined') return
  const enabled = window.innerWidth > 1180
  useUtilityRail.value = enabled
  if (!enabled) {
    hotRailOpen.value = false
    composerRailOpen.value = false
  }
}

function toggleHotRail() {
  hotRailOpen.value = !hotRailOpen.value
  if (hotRailOpen.value) {
    composerRailOpen.value = false
  }
}

function toggleComposerRail() {
  composerRailOpen.value = !composerRailOpen.value
  if (composerRailOpen.value) {
    composerCollapsed.value = false
    hotRailOpen.value = false
  }
}

function toggleComposerCollapsed() {
  composerCollapsed.value = !composerCollapsed.value
}

function handleHotQuestionSelect(question) {
  hotRailOpen.value = false
  fillAndSend(question)
}

const compareLoading = ref(false)
const compareError = ref('')
const currentPanelMessageId = ref(null)

const currentState = computed(() => {
  const sid = currentSessionId.value
  return (sid && sessionStates[sid]) || {
    messages: [], panelInfo: null, panelVisible: false, llmAnswer: '',
    isLoading: false, isTyping: false, currentQuery: '', activeMsg: null,
    requestError: '', lastFailedQuery: '', lastFailedHadImage: false,
  }
})
const messages     = computed(() => currentState.value.messages)
const isLoading    = computed(() => currentState.value.isLoading)
const isTyping     = computed(() => currentState.value.isTyping)
const currentQuery = computed(() => currentState.value.currentQuery)
const panelInfo    = computed(() => currentState.value.panelInfo)
const panelVisible = computed(() => !!currentState.value.panelVisible)
const llmAnswer    = computed(() => currentState.value.llmAnswer)
const bootstrapError = ref('')

const composerNotice = computed(() => {
  if (bootstrapError.value) {
    return {
      tone: 'error',
      icon: Warning,
      title: '当前无法创建新对话',
      desc: bootstrapError.value,
      action: retryBootstrapSend,
      actionLabel: '重新发送',
    }
  }

  if (currentState.value.requestError) {
    const desc = currentState.value.lastFailedHadImage
      ? `${currentState.value.requestError} 如需重试图片提问，请重新选择图片后再发送。`
      : currentState.value.requestError

    return {
      tone: 'error',
      icon: Warning,
      title: '上一条提问发送失败',
      desc,
      action: currentState.value.lastFailedHadImage ? null : retryLastSend,
      actionLabel: currentState.value.lastFailedHadImage ? '' : '重试上次问题',
    }
  }

  if (!currentSessionId.value && !sessions.value.length) {
    return {
      tone: 'info',
      icon: InfoFilled,
      title: '首次发送会自动创建对话',
      desc: '可以直接输入问题；如果后端暂时不可用，这里会显示明确的失败原因。',
      action: null,
      actionLabel: '',
    }
  }

  return null
})

const panelEmptyState = computed(() => {
  if (!panelInfo.value || panelInfo.value.query_type !== '专业咨询' || panelInfo.value?.sources?.length) {
    return null
  }

  if (!includeSourceDetails.value) {
    return {
      tone: 'info',
      icon: InfoFilled,
      title: '本次未展示来源详情',
      desc: '你当前关闭了“来源详情”。如需查看命中证据，请开启后重新提问。',
      action: enableSourceDetails,
      actionLabel: '开启来源详情',
      actionType: 'primary',
    }
  }

  if (panelInfo.value.error_message || panelInfo.value.error_type) {
    return {
      tone: 'warning',
      icon: Warning,
      title: '本次未返回可展示证据',
      desc: panelInfo.value.error_message || '检索阶段出现异常，当前只能展示策略和计数信息。',
      action: null,
      actionLabel: '',
      actionType: 'warning',
    }
  }

  return {
    tone: 'info',
    icon: Search,
    title: '暂未命中可展示证据',
    desc: '可以尝试缩短问题、补充专业术语，或把复合问题拆成更具体的子问题后再提问。',
    action: null,
    actionLabel: '',
    actionType: 'primary',
  }
})

const panelAvailable = computed(() => !!panelInfo.value || !!(isLoading.value && currentQuery.value))
const showPanel = computed(() => panelAvailable.value && panelVisible.value)
const sourceDetailVisible = ref(false)
const sourceDetail = ref(null)

const defaultExamples = [
  { question: '矿井通风安全有哪些规定？', count: null, source: 'guide', label: '引导问题' },
  { question: '瓦斯超标应该如何处理？', count: null, source: 'guide', label: '引导问题' },
  { question: '顶板管理的主要安全措施？', count: null, source: 'guide', label: '引导问题' },
  { question: '爆破作业安全规程是什么？', count: null, source: 'guide', label: '引导问题' },
  { question: '矿山水害预防措施？', count: null, source: 'guide', label: '引导问题' },
  { question: '采矿特种作业人员资质要求？', count: null, source: 'guide', label: '引导问题' },
]
const examples = ref([...defaultExamples])
const hotQuestionWindows = ref([])
const activeHotWindowKey = ref('1d')
const activeHotWindow = computed(() => hotQuestionWindows.value.find((item) => item.key === activeHotWindowKey.value) || hotQuestionWindows.value[0] || null)

const feedbackOptions = [
  { type: 'like', label: '点赞', icon: CircleCheck, buttonType: 'success' },
  { type: 'dislike', label: '点踩', icon: CircleClose, buttonType: 'danger' },
  { type: 'partial_correct', label: '部分正确', icon: Warning, buttonType: 'warning' },
  { type: 'correction', label: '纠错', icon: Edit, buttonType: 'primary' },
]

function buildSessionMetadata() {
  return {
    user_id: state.user?.employee_id || '',
    employee_id: state.user?.employee_id || '',
    nickname: state.user?.nickname || '',
    user: {
      employee_id: state.user?.employee_id || '',
      nickname: state.user?.nickname || '',
    },
  }
}

// ── 数据集管理状态 ────────────────────────────────────────────────────────────
const uploadFiles  = ref([])
const uploadSource = ref('mining')
const isUploading  = ref(false)
const uploadSteps  = ref([])
const uploadPct    = ref(0)
const uploadError  = ref('')
const uploadProcessedCount = ref(0)
const uploadScheduledCount = ref(0)

function uploadFileKey(file) {
  return `${file?.name || ''}-${file?.size || 0}-${file?.lastModified || 0}`
}

function appendUploadFiles(rawFiles = []) {
  const queue = [...uploadFiles.value]
  const existing = new Set(queue.map(uploadFileKey))
  let addedCount = 0

  for (const file of rawFiles) {
    if (!file) continue
    const key = uploadFileKey(file)
    if (existing.has(key)) continue
    existing.add(key)
    queue.push(file)
    addedCount += 1
  }

  uploadFiles.value = queue
  return addedCount
}

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
const workspaceActionFeedback = ref(null)

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
const formatPercent = (value) => `${Math.round((Number(value) || 0) * 100)}%`
const formatSigned = (value) => {
  const num = Number(value)
  if (!Number.isFinite(num)) return '0.0000'
  return num >= 0 ? `+${num.toFixed(4)}` : num.toFixed(4)
}
const panelStrategyK = (info) => Number(info?.strategy_k ?? info?.candidate_count ?? 0)
const panelContextLimit = (info) => Number(info?.context_limit ?? info?.final_count ?? 0)
const panelDirectChildHits = (info) => {
  const explicit = Number(info?.direct_child_hits)
  if (Number.isFinite(explicit)) return explicit
  return (info?.sources || []).reduce((sum, item) => sum + ((item?.matched_children || []).length), 0)
}
const panelParentOnlyHits = (info) => {
  const explicit = Number(info?.parent_only_hits)
  if (Number.isFinite(explicit)) return explicit
  return (info?.sources || []).filter((item) => item?.evidence_status === 'parent_rerank_only').length
}
const docScoreLabel = (doc) => {
  if (doc?.evidence_status === 'parent_rerank_only') return '无直接子块证据'
  return `子块证据分 ${formatPercent(doc?.score)}`
}
const sourceDetailTagLabel = (doc) => {
  if (doc?.evidence_status === 'parent_rerank_only') return '父块重排入选'
  return `子块证据分：${formatPercent(doc?.score)}`
}
const evidenceClass = (doc) => {
  if (doc?.evidence_status === 'parent_rerank_only') return 'parent-only'
  if (doc?.evidence_status === 'weak_child_evidence') return 'weak-child'
  return 'strong-child'
}

function setWorkspaceActionFeedback(tone, title, desc) {
  workspaceActionFeedback.value = {
    tone,
    title,
    desc,
    icon: tone === 'success' ? CircleCheck : Warning,
  }
}

function clearWorkspaceActionFeedback() {
  workspaceActionFeedback.value = null
}
const nowTime  = () => new Date().toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
const fmtDate  = (iso) => {
  if (!iso) return ''
  const d = new Date(iso)
  return `${(d.getMonth()+1).toString().padStart(2,'0')}-${d.getDate().toString().padStart(2,'0')} ` +
         `${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`
}
const messagesWrap = ref(null)
// 用户是否已经手动向上滚动；只要离底部超过 NEAR_BOTTOM_PX 就视为"用户在阅读"，
// streaming 期间不再强制把视图按到底，从而让用户可以自由翻看历史。
const NEAR_BOTTOM_PX = 80
let userScrolledUp = false
function _isNearBottom() {
  const el = messagesWrap.value
  if (!el) return true
  return (el.scrollHeight - el.scrollTop - el.clientHeight) <= NEAR_BOTTOM_PX
}
function _onMessagesScroll() {
  userScrolledUp = !_isNearBottom()
}
const scrollBottom = (force = false) => nextTick(() => {
  const el = messagesWrap.value
  if (!el) return
  if (force) {
    el.scrollTop = el.scrollHeight
    userScrolledUp = false
    return
  }
  // 仅在用户没有手动向上滚时才自动跟随
  if (!userScrolledUp || _isNearBottom()) {
    el.scrollTop = el.scrollHeight
  }
})

function openSourceDetail(doc, index) {
  sourceDetail.value = {
    ...doc,
    index,
  }
  sourceDetailVisible.value = true
}

function openPanelManually() {
  const sid = currentSessionId.value
  if (!sid) return
  const st = ensureSessionState(sid)
  st.panelVisible = true
}

function closePanel() {
  const sid = currentSessionId.value
  if (!sid) return
  const st = ensureSessionState(sid)
  st.panelVisible = false
}

// 历史消息或当前消息恢复右侧"检索分析"面板
function reopenPanel(msg) {
  const sid = currentSessionId.value
  if (!sid) return
  const st = ensureSessionState(sid)
  st.panelInfo = msg.meta?.panel_info || null
  st.panelVisible = true
  st.llmAnswer = msg.meta?.compare_answer || ''
  currentPanelMessageId.value = msg.id
  compareLoading.value = false
  compareError.value = ''
}

function resolvePanelQuery(msg) {
  if (msg?.meta?.user_query) return msg.meta.user_query
  const index = messages.value.findIndex(item => item.id === msg?.id)
  if (index > 0) {
    const prev = messages.value[index - 1]
    if (prev?.role === 'user' && prev.content) return prev.content
  }
  return currentQuery.value || ''
}

async function requestCompareAnswer() {
  if (compareLoading.value || panelInfo.value?.query_type !== '专业咨询') return

  const sid = currentSessionId.value
  if (!sid) return
  const st = ensureSessionState(sid)
  const targetMsg = messages.value.find(item => item.id === currentPanelMessageId.value)
  const query = resolvePanelQuery(targetMsg)
  if (!query) {
    ElMessage.warning('未找到该问题的原始内容')
    return
  }

  compareLoading.value = true
  compareError.value = ''
  st.llmAnswer = ''
  if (targetMsg?.meta) {
    targetMsg.meta.compare_answer = ''
  }

  try {
    await streamCompareChat(query, {
      onToken(char) {
        st.llmAnswer += char
      },
      onDone() {
        if (targetMsg?.meta) {
          targetMsg.meta.compare_answer = st.llmAnswer
        }
      },
      onError(msg) {
        compareError.value = msg || '通用 LLM 对比生成失败'
      },
    })
  } finally {
    compareLoading.value = false
  }
}

function dispatchActivityUpdate(detail = {}) {
  window.dispatchEvent(new CustomEvent('rag-activity-updated', { detail }))
}

function dispatchFeedbackUpdate(detail = {}) {
  window.dispatchEvent(new CustomEvent('rag-feedback-updated', { detail }))
}

function handleChatPageHide() {
  persistTransientChatSnapshot()
}

function handleChatVisibilityChange() {
  if (document.visibilityState === 'hidden') {
    persistTransientChatSnapshot()
  }
}

// ── 反馈提交 / 撤销 ───────────────────────────────────────────────────────────
async function submitFeedback(msgId, type, content = null) {
  try {
    const msg = messages.value.find(m => m.id === msgId)
    if (!msg) return

    const messageIndex = messages.value.findIndex(m => m.id === msgId)
    if (messageIndex < 0) return

    const questionMessage = messageIndex > 0 ? messages.value[messageIndex - 1] : null
    const originalQuestion = questionMessage?.role === 'user' ? questionMessage.content : (msg.meta?.user_query || '')

    await feedbackAPI.submit({
      session_id: currentSessionId.value,
      message_index: messageIndex,
      user_id: state.user.employee_id,
      feedback_type: type,
      content,
      question: originalQuestion,
      answer: msg.content || '',
      query_type: msg.meta?.query_type || '',
      strategy: msg.meta?.strategy || '',
      panel_info: msg.meta?.panel_info || null,
    })

    msg.feedback = { type, content }
    dispatchFeedbackUpdate({ sessionId: currentSessionId.value, messageIndex, type })
    setWorkspaceActionFeedback(
      'success',
      type === 'correction' ? '纠错已提交' : '反馈已提交',
      content ? '你的补充说明已保存，后续可在消息下方继续查看。' : '当前回答的反馈状态已经更新。'
    )
  } catch (err) {
    setWorkspaceActionFeedback('error', '反馈提交失败', err.response?.data?.detail || '请稍后重试。')
  }
}

async function cancelFeedback(msg) {
  try {
    const messageIndex = messages.value.findIndex(m => m.id === msg.id)
    if (messageIndex < 0) return
    await feedbackAPI.cancel(
      currentSessionId.value,
      messageIndex,
      state.user.employee_id,
    )
    msg.feedback = null
    dispatchFeedbackUpdate({ sessionId: currentSessionId.value, messageIndex, type: null })
    setWorkspaceActionFeedback('success', '已撤销反馈', '当前回答已恢复到未反馈状态。')
  } catch (err) {
    setWorkspaceActionFeedback('error', '撤销反馈失败', err.response?.data?.detail || '请稍后重试。')
  }
}

async function handleFeedback(msg, type) {
  // 同一类型再次点击 → 撤销
  if (msg.feedback?.type === type) {
    await cancelFeedback(msg)
    return
  }
  if (type === 'partial_correct') {
    try {
      const { value } = await ElMessageBox.prompt('请说明哪些内容正确、哪些内容需要补充或修正', '提交“部分正确”反馈', {
        confirmButtonText: '提交',
        cancelButtonText: '取消',
        inputPlaceholder: '例如：支护部分基本正确，但通风整改措施不够具体',
        inputType: 'textarea',
        inputValidator: (value) => !!value?.trim() || '请填写补充说明',
      })
      await submitFeedback(msg.id, type, value.trim())
    } catch (err) {
      if (err !== 'cancel' && err !== 'close') {
        setWorkspaceActionFeedback('error', '部分正确反馈提交失败', '请稍后重试，或缩短补充说明后再次提交。')
      }
    }
    return
  }

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
        setWorkspaceActionFeedback('error', '纠错提交失败', '请稍后重试，或缩短纠错说明后再次提交。')
      }
    }
    return
  }

  // 其他类型互斥替换
  await submitFeedback(msg.id, type)
}

// ── 会话管理 ──────────────────────────────────────────────────────────────────
async function loadSessions() {
  try { sessions.value = (await sessionAPI.list()).data.sessions || [] } catch {}
}
async function createSession() {
  try {
    bootstrapError.value = ''
    const sid = (await sessionAPI.create(buildSessionMetadata())).data.session_id
    const st = ensureSessionState(sid)
    st.messages = [buildGreetingMessage()]
    st.panelInfo = null
    st.llmAnswer = ''
    st.requestError = ''
    st.lastFailedQuery = ''
    st.lastFailedHadImage = false
    currentSessionId.value = sid
    await loadSessions()
    setWorkspaceActionFeedback('success', '已创建新对话', '你现在可以直接开始提问，当前会话已切换到最新对话。')
  } catch {
    setWorkspaceActionFeedback('error', '创建对话失败', '请确认后端服务可用后再试。')
  }
}
async function switchSession(id) {
  if (!id || id === currentSessionId.value) return
  // 不再 abort 在飞请求：让它在后台继续跑、写入对应 session 的 state，
  // 这样用户切回来仍能看到完整问答；同时切到别的 session 也能立刻输入新问题。
  ensureSessionState(id)
  currentSessionId.value = id

  const st = sessionStates[id]
  // 已经在飞或本地已有缓存消息（包含正在流式生成的回答）→ 不重新拉取，避免覆盖
  if (st.isLoading || st.messages.length > 0) {
    nextTick(scrollBottom)
    return
  }
  try {
    const res = await sessionAPI.messages(id)
    const raw = res.data.messages || []
    if (raw.length > 0) {
      st.messages = raw.map((m, i) => ({
        id:      i,
        role:    m.role,
        content: m.content,
        time:    m.time,
        meta:    m.meta || null,
        feedback: m.feedback || null,
      }))
    } else {
      st.messages = [buildGreetingMessage()]
    }
    nextTick(scrollBottom)
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
    dropSessionState(id)
    persistTransientChatSnapshot()
    await loadSessions()
    setWorkspaceActionFeedback('success', '对话已删除', '侧边栏会话列表已经同步更新。')
  } catch (e) {
    if (e !== 'cancel') {
      setWorkspaceActionFeedback('error', '删除对话失败', '请稍后重试。')
    }
  }
}

// ── 发送消息 ──────────────────────────────────────────────────────────────────
async function doSend() {
  const query = inputText.value.trim()
  if (!query && !questionImageFile.value) return
  if (isLoading.value) return

  // 没有 currentSession 时先建一个，确保 user message 有归属 session
  if (!currentSessionId.value) {
    try {
      bootstrapError.value = ''
      const sid = (await sessionAPI.create(buildSessionMetadata())).data.session_id
      ensureSessionState(sid)
      currentSessionId.value = sid
      await loadSessions()
    } catch (err) {
      bootstrapError.value = err?.response?.data?.detail || '新对话创建失败，请确认后端服务可用后再试。'
      setWorkspaceActionFeedback('error', '无法创建会话', bootstrapError.value)
      return
    }
  }
  const bindSid = currentSessionId.value
  const st = ensureSessionState(bindSid)
  bootstrapError.value = ''

  const requestStartedAt = performance.now()
  inputText.value = ''
  st.isLoading = true
  st.isTyping  = true
  st.panelInfo = null
  st.panelVisible = false
  st.llmAnswer = ''
  st.currentQuery = query || (questionImageFile.value ? `图片提问：${questionImageFile.value.name}` : '')
  compareLoading.value = false
  compareError.value = ''
  currentPanelMessageId.value = null
  st.requestError = ''
  st.lastFailedQuery = query
  st.lastFailedHadImage = !!questionImageFile.value

  // 如果只剩问候语，发送时清掉，避免 server 端历史里有奇怪的"问候"
  if (st.messages.length === 1 && st.messages[0].role === 'assistant' && st.messages[0].content === SESSION_GREETING) {
    st.messages = []
  }
  st.messages.push({
    id: Date.now(),
    role: 'user',
    content: query || (questionImageFile.value ? `图片提问：${questionImageFile.value.name}` : ''),
    time: nowTime(),
  })
  if (currentSessionId.value === bindSid) scrollBottom(true)

  // 占位助手消息（绑定到 bindSid，闭包内引用即可，不依赖外部）
  const activeMsg = reactive({ id: Date.now() + 1, role: 'assistant', content: '', meta: null, time: nowTime(), feedback: null })
  st.activeMsg = activeMsg
  let msgPushed = false

  const imageFile = questionImageFile.value
  const callbacks = {
    onRetrievalInfo(info) {
      st.panelInfo = info
      st.isTyping  = false
      if (!msgPushed) { st.messages.push(activeMsg); msgPushed = true }
      activeMsg.meta = {
        query_type: info.query_type,
        strategy: info.strategy,
        user_query: st.currentQuery,
        time: info.time,
        compare_answer: '',
        stream_status: 'streaming',
        stream_error: '',
        had_image: !!imageFile,
      }
      currentPanelMessageId.value = activeMsg.id
      if (currentSessionId.value === bindSid) scrollBottom()
    },
    onToken(char) {
      if (!msgPushed) { st.isTyping = false; st.messages.push(activeMsg); msgPushed = true }
      if (!activeMsg.meta) {
        activeMsg.meta = {
          query_type: '专业咨询',
          strategy: '',
          user_query: st.currentQuery,
          time: 0,
          compare_answer: '',
          stream_status: 'streaming',
          stream_error: '',
          had_image: !!imageFile,
        }
      }
      activeMsg.content += char
      if (currentSessionId.value === bindSid) scrollBottom()
    },
    onLlmToken(char) {
      st.llmAnswer += char
    },
    onDone(data) {
      const elapsedSeconds = Math.max(0, (performance.now() - requestStartedAt) / 1000)
      if (st.panelInfo) {
        st.panelInfo = { ...st.panelInfo, time: elapsedSeconds }
        activeMsg.meta = {
          query_type: st.panelInfo.query_type,
          strategy:   st.panelInfo.strategy,
          time:       elapsedSeconds,
          panel_info: st.panelInfo,
          user_query: st.currentQuery,
          compare_answer: activeMsg.meta?.compare_answer || '',
          stream_status: 'done',
          stream_error: '',
          had_image: !!imageFile,
        }
      } else if (activeMsg.meta) {
        activeMsg.meta = {
          ...activeMsg.meta,
          time: elapsedSeconds,
          stream_status: 'done',
          stream_error: '',
          had_image: !!imageFile,
        }
      }
      st.isLoading = false
      st.isTyping  = false
      st.activeMsg = null
      st.requestError = ''
      st.lastFailedQuery = ''
      st.lastFailedHadImage = false
      persistTransientChatSnapshot()
      dispatchActivityUpdate({ sessionId: bindSid, query: st.currentQuery })
      loadSessions()
    },
    onError(msg) {
      st.requestError = msg || '请求未成功完成，请稍后重试。'
      if (msgPushed) {
        activeMsg.meta = {
          ...(activeMsg.meta || {}),
          user_query: st.currentQuery,
          time: activeMsg.meta?.time || 0,
          stream_status: 'interrupted',
          stream_error: msg || '流式回答中断',
          had_image: !!imageFile,
        }
      }
      st.isLoading = false; st.isTyping = false; st.activeMsg = null
      persistTransientChatSnapshot()
    },
  }

  try {
    if (imageFile) {
      await streamChatWithImage(
        query,
        imageFile,
        bindSid,
        null,
        includeSourceDetails.value,
        callbacks,
        { enableCompare: false },
      )
    } else {
      await streamChat(
        query,
        bindSid,
        null,
        includeSourceDetails.value,
        callbacks,
        { enableCompare: false },
      )
    }
  } finally {
    clearQuestionImage()
  }
}
function fillAndSend(q) { inputText.value = q; doSend() }

function normalizeHotQuestionWindows(windows = []) {
  return (windows || [])
    .map((window) => {
      const days = Number(window?.days)
      const items = normalizeExampleItems(window?.items || []).slice(0, 5)
      if (!items.length) return null
      return {
        key: String(window?.key || `${days || 0}d`),
        label: String(window?.label || `近 ${days || 0} 天`),
        days: Number.isFinite(days) && days > 0 ? days : 7,
        items,
      }
    })
    .filter(Boolean)
}

function hotQuestionLabel(days, count) {
  return `近 ${days} 天 ${count || 0} 次`
}

function normalizeExampleItems(items = []) {
  return (items || [])
    .map((item) => {
      if (typeof item === 'string') {
        const question = item.trim()
        if (!question) return null
        return { question, count: null, source: 'guide', label: '引导问题' }
      }
      const question = String(item?.question || item?.text || '').trim()
      if (!question) return null
      const rawCount = Number(item?.count)
      const count = Number.isFinite(rawCount) && rawCount > 0 ? rawCount : null
      const source = item?.source || (count ? 'recent_hot' : 'guide')
      const label = item?.label || (count ? `近 7 天 ${count} 次` : '引导问题')
      return { question, count, source, label }
    })
    .filter(Boolean)
}

function retryBootstrapSend() {
  doSend()
}

function retryLastSend() {
  if (!currentState.value.lastFailedQuery || currentState.value.lastFailedHadImage) return
  inputText.value = currentState.value.lastFailedQuery
  doSend()
}

function enableSourceDetails() {
  includeSourceDetails.value = true
}

function retryInterruptedMessage(msg) {
  const query = msg?.meta?.user_query
  if (!query) return
  inputText.value = query
  doSend()
}

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
  const addedCount = appendUploadFiles((fileList || [])
    .map(item => item.raw)
    .filter(Boolean))

  if (!isUploading.value) {
    uploadSteps.value = []
    uploadPct.value = 0
    uploadError.value = ''
    uploadProcessedCount.value = 0
    uploadScheduledCount.value = uploadFiles.value.length
    clearWorkspaceActionFeedback()
    return
  }

  if (addedCount > 0) {
    uploadScheduledCount.value += addedCount
    uploadSteps.value.push(`已加入队列：${addedCount} 个文件，等待当前任务完成后继续处理`)
  }
}
async function doUpload() {
  if (!isSupervisor.value) {
    setWorkspaceActionFeedback('error', '无法上传知识文件', '仅主管角色可执行知识库文件上传。')
    return
  }
  if (!uploadFiles.value.length) return
  isUploading.value  = true
  uploadSteps.value  = []
  uploadPct.value    = 0
  uploadError.value = ''
  uploadProcessedCount.value = 0
  uploadScheduledCount.value = uploadFiles.value.length
  clearWorkspaceActionFeedback()

  try {
    let totalChunks = 0
    const completedFiles = []

    while (uploadFiles.value.length) {
      const file = uploadFiles.value[0]
      uploadSteps.value.push(`开始处理：${file.name}`)

      await uploadDocument(file, uploadSource.value, {
        onProgress(step, pct) {
          uploadSteps.value.push(step)
          const total = Math.max(uploadScheduledCount.value, 1)
          uploadPct.value = Math.min(100, Math.round(((uploadProcessedCount.value + pct / 100) / total) * 100))
        },
        onDone(chunks, filename) {
          totalChunks += chunks
          completedFiles.push(filename)
          uploadSteps.value.push(`✅ 完成！${filename} 新增 ${chunks} 个向量块`)
          uploadProcessedCount.value += 1
          const total = Math.max(uploadScheduledCount.value, 1)
          uploadPct.value = Math.round((uploadProcessedCount.value / total) * 100)
        },
        onError(msg) {
          uploadSteps.value.push(`❌ ${file.name}：${msg}`)
          uploadProcessedCount.value += 1
          const total = Math.max(uploadScheduledCount.value, 1)
          uploadPct.value = Math.round((uploadProcessedCount.value / total) * 100)
        },
      })

      uploadFiles.value = uploadFiles.value.slice(1)
    }

    setWorkspaceActionFeedback(
      'success',
      '知识文件入库完成',
      `已完成 ${uploadProcessedCount.value} 个文件处理，共新增 ${totalChunks.toLocaleString()} 个向量块。`,
    )
    uploadFiles.value = []
    window.dispatchEvent(new CustomEvent('rag-knowledge-updated', {
      detail: { source: uploadSource.value, files: completedFiles, chunks: totalChunks },
    }))
  } catch (err) {
    const message = err?.message || '上传失败'
    uploadError.value = message
    setWorkspaceActionFeedback('error', '知识文件入库失败', message)
  } finally {
    isUploading.value = false
    uploadProcessedCount.value = 0
    uploadScheduledCount.value = uploadFiles.value.length
  }
}

// ── 测试集生成 ────────────────────────────────────────────────────────────────
async function doGenerate() {
  if (!isSupervisor.value) {
    setWorkspaceActionFeedback('error', '无法生成测试问答对', '仅主管角色可执行测试集生成。')
    return
  }
  clearWorkspaceActionFeedback()
  isGenerating.value = true
  tgCurrent.value    = 0
  tgTotal.value      = tgCount.value
  tgItems.value      = []
  tgDataset.value    = []

  try {
    await generateTestset(tgCount.value, tgSource.value, {
      onLoading(msg)  { ElMessage.info(msg) },
      onProgress(cur, total, item) {
        tgCurrent.value = cur
        tgTotal.value   = total
        tgItems.value.push(item)
      },
      onDone(dataset, savedPath) {
        tgDataset.value = dataset
        setWorkspaceActionFeedback(
          'success',
          '测试集生成完成',
          `已生成 ${dataset.length.toLocaleString()} 条问答样本，并保存到 ${savedPath}。`,
        )
      },
      onError(msg) {
        setWorkspaceActionFeedback('error', '测试集生成失败', msg || '生成流程未成功完成。')
      },
    })
  } catch (err) {
    const message = err?.response?.data?.detail || err?.message || '生成流程未成功完成。'
    setWorkspaceActionFeedback('error', '测试集生成失败', message)
  } finally {
    isGenerating.value = false
  }
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
    const items = normalizeExampleItems(res?.data?.items || [])
    const hotWindows = normalizeHotQuestionWindows(res?.data?.hot_windows || [])
    hotQuestionWindows.value = hotWindows
    if (hotWindows.length) {
      activeHotWindowKey.value = hotWindows.some((item) => item.key === activeHotWindowKey.value) ? activeHotWindowKey.value : hotWindows[0].key
    }
    if (items.length) {
      examples.value = items.slice(0, 10)
      return
    }
  } catch {
    // Fall through to defaults.
  }
  hotQuestionWindows.value = []
  examples.value = [...defaultExamples]
}

async function openAppendDialog() {
  if (!tgDataset.value.length) {
    setWorkspaceActionFeedback('error', '无法追加到已有文件', '请先生成问答对，再执行追加。')
    return
  }
  try {
    const res = await testgenAPI.listDatasetFiles()
    appendFiles.value = res?.data?.files || []
    appendTargetFile.value = appendFiles.value[0]?.name || ''
    appendDialogVisible.value = true
  } catch (err) {
    setWorkspaceActionFeedback('error', '获取文件列表失败', err?.response?.data?.detail || '请稍后重试。')
  }
}

async function confirmAppendToFile() {
  if (!appendTargetFile.value) {
    setWorkspaceActionFeedback('error', '无法执行追加', '请选择目标文件。')
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
    setWorkspaceActionFeedback('success', '追加成功', `新增 ${data.appended || 0} 条，总计 ${data.total || 0} 条。`)
    appendDialogVisible.value = false
  } catch (err) {
    if (err !== 'cancel' && err !== 'close') {
      setWorkspaceActionFeedback('error', '追加失败', err?.response?.data?.detail || '请稍后重试。')
    }
  } finally {
    appendLoading.value = false
  }
}

onMounted(async () => {
  syncUtilityRailMode()
  window.addEventListener('resize', syncUtilityRailMode)
  window.addEventListener('pagehide', handleChatPageHide)
  document.addEventListener('visibilitychange', handleChatVisibilityChange)
  const restoredTransientState = restoreTransientChatSnapshot()
  await loadSessions()
  if (!currentSessionId.value && sessions.value.length) {
    await switchSession(sessions.value[0].session_id)
  }
  if (restoredTransientState) {
    setWorkspaceActionFeedback('warning', '已恢复刷新前的临时对话', '上一轮回答在页面刷新时被中断；当前内容来自本窗口临时缓存，可直接重试。')
  }
  if (!isSupervisor.value && activeTab.value !== 'sessions') {
    activeTab.value = 'sessions'
  }
  await initTestgenSources()
  await loadExamples()
})

onUnmounted(() => {
  window.removeEventListener('resize', syncUtilityRailMode)
  window.removeEventListener('pagehide', handleChatPageHide)
  document.removeEventListener('visibilitychange', handleChatVisibilityChange)
})
</script>

<style scoped>
/* ── 整体布局 ─────────────────────────────────────────────────────────────── */
.chat-layout {
  display: flex;
  height: calc(100vh - 60px);
  height: calc(100dvh - 60px);
  min-height: 0;
  overflow: auto;
  position: relative;
  gap: 18px;
  padding: 18px 18px 20px;
}

.motion-ready .sidebar,
.motion-ready .chat-main,
.motion-ready .analysis-panel {
  opacity: 0;
  transform: translateY(18px);
  animation: sceneReveal .78s cubic-bezier(.22,1,.36,1) forwards;
}

.motion-ready .chat-main { animation-delay: .08s; }
.motion-ready .analysis-panel { animation-delay: .16s; }

/* ── 左侧侧边栏 ───────────────────────────────────────────────────────────── */
.sidebar {
  width: 260px; min-width: 260px;
  background: rgba(255, 255, 255, .72);
  border: 1px solid rgba(148, 163, 184, .18);
  border-radius: 28px;
  backdrop-filter: blur(18px);
  box-shadow: 0 18px 38px rgba(15, 23, 42, .08);
  display: flex; flex-direction: column;
  transition: width .2s, min-width .2s;
  overflow: hidden; position: relative;
}
.sidebar.collapsed { width: 54px; min-width: 54px; }
.sidebar-pin {
  position: absolute; top: 14px; right: 12px; z-index: 10;
  cursor: pointer; color: #64748b; padding: 8px;
  border-radius: 999px; transition: color .15s, background .15s;
}
.sidebar-pin:hover { color: #0f5bd8; background: rgba(15, 91, 216, .08); }

.sidebar-overview {
  padding: 18px 18px 10px;
  border-bottom: 1px solid rgba(148, 163, 184, .14);
  opacity: 0;
  transform: translateY(12px);
  animation: sceneReveal .68s cubic-bezier(.22,1,.36,1) .18s forwards;
}

.sidebar-kicker {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .16em;
  text-transform: uppercase;
  color: #0f5bd8;
}

.sidebar-title {
  margin-top: 6px;
  font-size: 20px;
  line-height: 1.15;
  font-weight: 900;
  color: #0f172a;
}

.sidebar-meta {
  margin-top: 10px;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
  color: #64748b;
}

.workspace-feedback {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin: 0 12px 10px;
  padding: 12px 12px;
  border-radius: 16px;
  border: 1px solid rgba(148, 163, 184, .18);
  box-shadow: 0 10px 20px rgba(15, 23, 42, .05);
}

.workspace-feedback.success {
  background: linear-gradient(180deg, rgba(240, 253, 244, .96), rgba(255,255,255,.96));
  border-color: rgba(34, 197, 94, .18);
}

.workspace-feedback.error {
  background: linear-gradient(180deg, rgba(254, 242, 242, .96), rgba(255,255,255,.96));
  border-color: rgba(239, 68, 68, .18);
}

.workspace-feedback-main {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
}

.workspace-feedback-icon {
  flex-shrink: 0;
  margin-top: 2px;
}

.workspace-feedback.success .workspace-feedback-icon {
  color: #16a34a;
}

.workspace-feedback.error .workspace-feedback-icon {
  color: #dc2626;
}

.workspace-feedback-copy {
  min-width: 0;
}

.workspace-feedback-title {
  font-size: 12px;
  font-weight: 800;
  color: #0f172a;
}

.workspace-feedback-desc {
  margin-top: 3px;
  font-size: 11px;
  line-height: 1.6;
  color: #64748b;
}

:deep(.sidebar-tabs)              { flex: 1; overflow: hidden; }
:deep(.sidebar-tabs .el-tabs__header) { padding: 12px 12px 0; margin: 0; }
:deep(.sidebar-tabs .el-tabs__content) { padding: 10px 12px 14px; overflow-y: auto; height: calc(100% - 48px); }
:deep(.sidebar-tabs .el-tabs__item)   { padding: 0 12px; }

.new-session-btn { width: 100%; margin-bottom: 10px; border-radius: 14px; height: 42px; font-weight: 800; }
.session-list    { display: flex; flex-direction: column; gap: 4px; }
.session-item    {
  display: flex; align-items: center; gap: 6px;
  padding: 10px 12px; border-radius: 16px; cursor: pointer;
  transition: background .15s, transform .15s, box-shadow .15s;
}
.session-item:hover  { background: rgba(255, 255, 255, .86); transform: translateY(-1px); box-shadow: 0 10px 20px rgba(15, 23, 42, .05); }
.session-item.active { background: linear-gradient(135deg, rgba(15, 91, 216, .12), rgba(20, 184, 166, .1)); border: 1px solid rgba(15, 91, 216, .12); }
.s-meta   { flex: 1; min-width: 0; }
.s-date   { font-size: 12px; color: #0f172a; font-weight: 700; }
.s-count  { font-size: 11px; color: #909399; }
.s-del    { opacity: 0; transition: opacity .15s; }
.session-item:hover .s-del { opacity: 1; }
.empty-hint { font-size: 12px; color: #c0c4cc; text-align: center; padding: 16px 0; }

/* 数据/测试 tab 通用 */
.tab-title   { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 10px; }
.upload-compact-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 6px;
}
.upload-source-badge {
  padding: 4px 8px;
  border-radius: 999px;
  background: rgba(15, 91, 216, .08);
  color: #0f5bd8;
  font-size: 11px;
  font-weight: 700;
}
.upload-hint {
  margin-bottom: 8px;
  font-size: 11px;
  color: #64748b;
  line-height: 1.5;
}
:deep(.uploader .el-upload-dragger) {
  padding: 12px; border-radius: 8px; text-align: center;
}
.upload-text { font-size: 12px; color: #909399; margin-top: 6px; line-height: 1.5; }
.selected-file-list.compact {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin: 8px 0;
}
.selected-file-summary {
  font-size: 11px;
  color: #64748b;
  font-weight: 700;
}
.selected-file {
  display: flex; align-items: center; gap: 6px;
  font-size: 12px; color: #606266;
  background: #f5f7fa; padding: 6px 10px; border-radius: 6px;
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
  flex: 1; display: flex; flex-direction: column; min-width: 0; min-height: 0;
  background:
    radial-gradient(circle at 12% 18%, rgba(34, 197, 94, .12), transparent 38%),
    radial-gradient(circle at 88% 78%, rgba(59, 130, 246, .12), transparent 42%),
    linear-gradient(145deg, rgba(248,250,252,.42) 0%, rgba(238,242,255,.58) 42%, rgba(239,246,255,.52) 100%);
  border: 1px solid rgba(148, 163, 184, .16);
  border-radius: 30px;
  backdrop-filter: blur(14px);
  box-shadow: 0 22px 48px rgba(15, 23, 42, .08);
  overflow: hidden;
  animation: bgFlow 12s ease-in-out infinite alternate;
}
.chat-stage {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
  padding: 18px;
  gap: 16px;
}
.chat-hero-bar {
  display: grid;
  grid-template-columns: minmax(0, 1.5fr) minmax(280px, 420px);
  gap: 16px;
  padding: 22px 24px;
  border-radius: 26px;
  background: linear-gradient(135deg, #0f172a 0%, #0f5bd8 58%, #0f766e 100%);
  color: #fff;
  box-shadow: 0 18px 42px rgba(15, 23, 42, .2);
  opacity: 0;
  transform: translateY(18px);
  animation: sceneReveal .8s cubic-bezier(.22,1,.36,1) .18s forwards;
}
.chat-kicker {
  font-size: 11px;
  font-weight: 800;
  letter-spacing: .18em;
  text-transform: uppercase;
  color: rgba(255,255,255,.72);
}
.chat-hero-copy h1 {
  margin-top: 8px;
  font-size: clamp(22px, 2vw, 32px);
  line-height: 1.1;
  font-weight: 900;
  max-width: 14ch;
}
.chat-hero-copy p {
  margin-top: 10px;
  max-width: 60ch;
  font-size: 13px;
  line-height: 1.8;
  color: rgba(255,255,255,.76);
}
.chat-hero-pills {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
  align-self: stretch;
}
.chat-hero-pill {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 8px;
  min-height: 96px;
  padding: 14px 16px;
  border-radius: 20px;
  background: rgba(255,255,255,.12);
  border: 1px solid rgba(255,255,255,.16);
  backdrop-filter: blur(10px);
  animation: pillFloat 6.8s ease-in-out infinite;
}
.chat-hero-pill:nth-child(2) { animation-delay: .8s; }
.chat-hero-pill:nth-child(3) { animation-delay: 1.6s; }
.chat-hero-pill span {
  font-size: 12px;
  color: rgba(255,255,255,.7);
}
.chat-hero-pill strong {
  font-size: 20px;
  font-weight: 900;
}
.messages-wrap {
  flex: 1; overflow-y: auto; padding: 28px 28px 14px;
  display: flex; flex-direction: column; gap: 18px;
  min-height: 0;
  border-radius: 28px;
  background: rgba(255,255,255,.46);
  border: 1px solid rgba(255,255,255,.48);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.5);
  opacity: 0;
  transform: translateY(20px);
  animation: sceneReveal .82s cubic-bezier(.22,1,.36,1) .26s forwards;
}

/* 欢迎 */
.welcome       { text-align: center; margin: auto; padding: 32px 0; }
.welcome-shell {
  display: inline-flex; flex-direction: column; align-items: center; gap: 10px;
  padding: 34px 34px; border-radius: 30px;
  background: linear-gradient(180deg, rgba(255,255,255,.92), rgba(248,250,252,.95));
  box-shadow: 0 22px 48px rgba(15, 23, 42, .08);
  border: 1px solid rgba(148, 163, 184, .18);
  animation: panelFloat 7.4s ease-in-out infinite;
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
.welcome-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  width: 100%;
  margin: 2px 0 12px;
}
.welcome-metric {
  padding: 12px 14px;
  border-radius: 16px;
  text-align: left;
  background: linear-gradient(180deg, #ffffff, #f8fafc);
  border: 1px solid rgba(148, 163, 184, .18);
}
.welcome-metric strong {
  display: block;
  font-size: 13px;
  color: #0f172a;
  font-weight: 800;
}
.welcome-metric span {
  display: block;
  margin-top: 4px;
  font-size: 11px;
  color: #64748b;
  line-height: 1.6;
}
.example-grid  { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 10px; max-width: 720px; margin: 0 auto; width: 100%; }
.ex-card       {
  background: linear-gradient(180deg, #fff, #f8fafc); border: 1px solid #e2e8f0; border-radius: 12px;
  padding: 12px 14px; font-size: 13px; color: #334155; cursor: pointer;
  transition: all .18s; text-align: left; box-shadow: 0 8px 22px rgba(15, 23, 42, .04);
}
.ex-card:hover { border-color: #60a5fa; color: #2563eb; transform: translateY(-2px); box-shadow: 0 12px 24px rgba(37, 99, 235, .12); }
.ex-card.recent_hot {
  border-color: rgba(37, 99, 235, .22);
  background: linear-gradient(180deg, #ffffff, #eff6ff);
}
.ex-card-title {
  font-size: 13px;
  font-weight: 700;
  line-height: 1.5;
  color: #1e293b;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.ex-card-meta {
  margin-top: 8px;
  font-size: 11px;
  color: #64748b;
}

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
  border-radius: 20px; padding: 14px 18px;
  font-size: 14px; line-height: 1.75;
  box-shadow: 0 14px 30px rgba(15, 23, 42, .05); word-break: break-word;
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
.feedback-note {
  margin-top: 6px;
  font-size: 12px;
  color: #6b7280;
  line-height: 1.6;
}
.feedback-note-label { color: #374151; font-weight: 600; }

.stream-interrupt-note {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-top: 6px;
  padding: 10px 12px;
  border-radius: 14px;
  border: 1px solid rgba(248, 113, 113, .22);
  background: linear-gradient(180deg, rgba(254,242,242,.96), rgba(255,255,255,.96));
}

.stream-interrupt-copy {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.stream-interrupt-copy strong {
  font-size: 12px;
  color: #b91c1c;
}

.stream-interrupt-copy span {
  font-size: 12px;
  line-height: 1.6;
  color: #7f1d1d;
}

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
.input-zone {
  flex-shrink: 0;
  padding: 18px 20px 20px;
  background: rgba(255,255,255,.76);
  border: 1px solid rgba(148, 163, 184, .18);
  border-radius: 26px;
  box-shadow: 0 16px 32px rgba(15, 23, 42, .06);
  opacity: 0;
  transform: translateY(18px);
  animation: sceneReveal .82s cubic-bezier(.22,1,.36,1) .34s forwards;
}
.composer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 12px;
}
.composer-head-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.composer-title {
  font-size: 15px;
  font-weight: 800;
  color: #0f172a;
}
.composer-toggle {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-weight: 700;
}
.composer-collapsed-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 10px;
  border-radius: 14px;
  border: 1px dashed rgba(59, 130, 246, .22);
  background: rgba(248, 250, 252, .92);
  color: #475569;
  font-size: 12px;
}
.input-zone.collapsed {
  padding: 12px 14px;
}
.composer-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-bottom: 12px;
  padding: 12px 14px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, .18);
}
.composer-status.info {
  background: linear-gradient(135deg, rgba(15, 91, 216, .08), rgba(56, 189, 248, .08));
}
.composer-status.error {
  background: linear-gradient(135deg, rgba(239, 68, 68, .08), rgba(251, 191, 36, .08));
}
.composer-status-main {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-width: 0;
}
.composer-status-icon {
  margin-top: 2px;
  flex-shrink: 0;
  color: #0f5bd8;
}
.composer-status.error .composer-status-icon {
  color: #dc2626;
}
.composer-status-copy {
  min-width: 0;
}
.composer-status-title {
  font-size: 13px;
  font-weight: 800;
  color: #0f172a;
}
.composer-status-desc {
  margin-top: 3px;
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}
.hot-rank-board {
  margin-bottom: 12px;
  padding: 14px 16px;
  border-radius: 18px;
  border: 1px solid rgba(148, 163, 184, .18);
  background: linear-gradient(180deg, rgba(248,250,252,.96), rgba(255,255,255,.96));
}
.hot-rank-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.hot-rank-title {
  font-size: 13px;
  font-weight: 800;
  color: #0f172a;
}
.hot-rank-desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}
.hot-rank-tabs {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.hot-rank-list {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}
.hot-rank-item {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  width: 100%;
  padding: 12px;
  border: 1px solid rgba(148, 163, 184, .18);
  border-radius: 14px;
  background: linear-gradient(180deg, #fff, #f8fafc);
  text-align: left;
  cursor: pointer;
  transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease;
}
.hot-rank-item:hover {
  transform: translateY(-2px);
  border-color: rgba(37, 99, 235, .28);
  box-shadow: 0 12px 24px rgba(15, 23, 42, .08);
}
.hot-rank-index {
  width: 24px;
  height: 24px;
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 800;
  color: #2563eb;
  background: rgba(219, 234, 254, .92);
}
.hot-rank-copy {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.hot-rank-copy strong {
  font-size: 12px;
  line-height: 1.55;
  color: #1e293b;
}
.hot-rank-copy small {
  font-size: 11px;
  color: #64748b;
}
.hot-rank-empty {
  margin-top: 12px;
  font-size: 12px;
  color: #94a3b8;
}
.hot-rank-rail,
.composer-rail {
  position: fixed;
  right: 18px;
  z-index: 21;
}
.hot-rank-rail {
  bottom: 188px;
}
.composer-rail {
  bottom: 18px;
}
.hot-rank-rail.analysis-open,
.composer-rail.analysis-open {
  right: 378px;
}
.chat-utility-fab-wrap {
  display: flex;
  justify-content: flex-end;
}
.chat-utility-fab {
  width: 48px;
  height: 48px;
  border: 1px solid rgba(191, 219, 254, .9);
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #2563eb;
  background: rgba(239, 246, 255, .92);
  box-shadow: 0 12px 24px rgba(37, 99, 235, .16);
  cursor: pointer;
  transition: transform .18s ease, box-shadow .18s ease, background .18s ease;
}
.chat-utility-fab:hover {
  transform: translateY(-2px);
  background: rgba(219, 234, 254, .98);
  box-shadow: 0 16px 28px rgba(37, 99, 235, .22);
}
.chat-utility-card {
  border-radius: 28px;
  border: 1px solid rgba(148, 163, 184, .18);
  background: rgba(255,255,255,.88);
  backdrop-filter: blur(18px);
  box-shadow: 0 18px 38px rgba(15, 23, 42, .1);
  overflow: hidden;
}
.hot-rank-rail-card {
  width: 360px;
  max-width: calc(100vw - 110px);
}
.composer-rail-card {
  width: 420px;
  max-width: calc(100vw - 110px);
}
.rail-card-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px 12px;
  border-bottom: 1px solid rgba(148, 163, 184, .14);
}
.rail-card-title {
  font-size: 14px;
  font-weight: 800;
  color: #0f172a;
}
.rail-card-desc {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: #64748b;
}
.rail-card-tabs {
  padding: 0 18px 12px;
}
.hot-rank-rail-card .hot-rank-list {
  grid-template-columns: 1fr;
  margin: 0;
  padding: 0 18px 18px;
}
.hot-rank-rail-card .hot-rank-empty {
  margin: 0;
  padding: 0 18px 18px;
}
.rail-zone {
  padding: 16px 18px 18px;
  background: transparent;
  border: 0;
  border-radius: 0;
  box-shadow: none;
  opacity: 1;
  transform: none;
  animation: none;
}
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
.input-foot { display: flex; justify-content: flex-end; align-items: center; margin-top: 8px; gap: 12px; flex-wrap: wrap; }
.input-options { display: inline-flex; align-items: center; gap: 8px; margin-right: auto; }
.option-label { font-size: 12px; color: #606266; }
.question-image-uploader { display: inline-flex; }
.char-count { font-size: 12px; color: #c0c4cc; }
:deep(.msg-input .el-textarea__inner) {
  min-height: 112px !important;
  padding: 16px 18px;
  border-radius: 18px;
  background: rgba(248,250,252,.9);
  border: 1px solid rgba(148, 163, 184, .22);
  box-shadow: inset 0 1px 0 rgba(255,255,255,.6);
}
:deep(.msg-input .el-textarea__inner:focus) {
  box-shadow: 0 0 0 4px rgba(15, 91, 216, .10);
}

/* ── 右侧分析面板 ─────────────────────────────────────────────────────────── */
.analysis-panel {
  width: 344px; min-width: 344px; background: rgba(255,255,255,.76);
  border: 1px solid rgba(148, 163, 184, .18); overflow-y: auto;
  border-radius: 30px;
  backdrop-filter: blur(18px);
  box-shadow: 0 18px 38px rgba(15, 23, 42, .08);
}
.analysis-panel-fab-wrap {
  position: fixed;
  right: 18px;
  bottom: 132px;
  z-index: 20;
}
.analysis-panel-fab {
  width: 48px;
  height: 48px;
  border: 1px solid rgba(191, 219, 254, .9);
  border-radius: 50%;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  color: #2563eb;
  background: rgba(239, 246, 255, .92);
  box-shadow: 0 12px 24px rgba(37, 99, 235, .16);
  cursor: pointer;
  transition: transform .18s ease, box-shadow .18s ease, background .18s ease;
}
.analysis-panel-fab:hover {
  transform: translateY(-2px);
  background: rgba(219, 234, 254, .98);
  box-shadow: 0 16px 28px rgba(37, 99, 235, .22);
}
.panel-head {
  display: flex; align-items: center; justify-content: space-between; gap: 10px;
  padding: 18px 18px 14px;
  font-size: 14px; font-weight: 800; color: #0f172a;
  border-bottom: 1px solid rgba(148, 163, 184, .14);
  position: sticky; top: 0; background: rgba(255,255,255,.9); z-index: 1;
}
.panel-head-main {
  display: flex;
  align-items: center;
  gap: 6px;
}
.p-section { padding: 12px 16px 0; }
.p-label   { font-size: 12px; color: #909399; margin-bottom: 6px; }
.tag-row   { display: flex; gap: 6px; flex-wrap: wrap; }
.error-hint { margin-top: 6px; font-size: 12px; color: #e6a23c; line-height: 1.4; }
.evidence-note {
  margin-top: 6px; padding: 8px 10px; border-radius: 8px;
  font-size: 12px; line-height: 1.5; color: #8a6d3b;
  background: #fff7e6; border: 1px solid #f7d9a8;
}
.evidence-summary {
  margin-top: 8px; padding: 9px 10px; border-radius: 8px;
  font-size: 12px; line-height: 1.6; color: #475569;
  background: #f8fafc; border: 1px solid #e2e8f0;
}

.count-row { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.count-subrow {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 6px;
  font-size: 11px;
  color: #64748b;
}
.cnt       { text-align: center; }
.cnt-n     { font-size: 20px; font-weight: 700; color: #606266; }
.cnt-n.blue { color: #409eff; }
.cnt-l     { font-size: 11px; color: #909399; }
.cost-time { font-size: 11px; color: #909399; margin-left: auto; }

.src-card  {
  background: linear-gradient(180deg, #fff, #f8f9fb); border-radius: 16px; padding: 12px; margin-top: 8px;
  cursor: pointer; transition: box-shadow .15s, transform .15s;
  border: 1px solid rgba(148, 163, 184, .16);
}
.src-card:hover { box-shadow: 0 8px 20px rgba(15, 23, 42, .10); transform: translateY(-1px); }
.src-top   { display: flex; align-items: center; gap: 6px; margin-bottom: 6px; }
.src-idx   { font-size: 11px; color: #909399; background: #e4e7ed; padding: 1px 5px; border-radius: 3px; }
.src-name  { flex: 1; font-size: 12px; color: #606266; font-weight: 500; }
.src-score { font-size: 12px; font-weight: 700; color: #409eff; }
.score-bar { height: 4px; background: #e4e7ed; border-radius: 2px; margin-bottom: 8px; }
.score-fill { height: 100%; background: linear-gradient(90deg,#409eff,#79bbff); border-radius: 2px; transition: width .4s; }
.src-file  { font-size: 11px; color: #64748b; margin-bottom: 6px; }
.src-evidence-flag {
  margin-bottom: 6px; padding: 6px 8px; border-radius: 8px;
  font-size: 11px; line-height: 1.5;
}
.src-evidence-flag.parent-only {
  color: #8a6d3b; background: #fff7e6; border: 1px solid #f7d9a8;
}
.src-evidence-flag.weak-child {
  color: #92400e; background: #fff4e5; border: 1px solid #fed7aa;
}
.src-evidence-flag.strong-child {
  color: #166534; background: #effdf5; border: 1px solid #bbf7d0;
}
.src-metrics {
  display: flex; gap: 10px; flex-wrap: wrap;
  margin-bottom: 6px; font-size: 11px; color: #64748b;
}
.src-text  { font-size: 12px; color: #909399; line-height: 1.6; }
.src-tip   { font-size: 11px; color: #409eff; margin-top: 6px; }

.detail-head { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.detail-note {
  margin-bottom: 10px; padding: 8px 10px; border-radius: 8px;
  font-size: 12px; line-height: 1.5; color: #8a6d3b;
  background: #fff7e6; border: 1px solid #f7d9a8;
}
.detail-note.soft {
  color: #475569; background: #f8fafc; border-color: #e2e8f0;
}
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
.panel-empty-state {
  margin: 12px 16px 0;
  padding: 24px 18px;
  border-radius: 18px;
  border: 1px dashed rgba(148, 163, 184, .28);
  background: linear-gradient(180deg, rgba(248,250,252,.95), rgba(255,255,255,.96));
  color: #64748b;
}
.panel-empty-state.info {
  border-color: rgba(59, 130, 246, .18);
  background: linear-gradient(180deg, rgba(239,246,255,.95), rgba(255,255,255,.96));
}
.panel-empty-state.warning {
  border-color: rgba(245, 158, 11, .24);
  background: linear-gradient(180deg, rgba(255,251,235,.96), rgba(255,255,255,.96));
}
.panel-empty-state :deep(.el-button) {
  margin-top: 12px;
}
.panel-empty-state p {
  color: #334155;
  font-weight: 700;
}
.panel-empty-state .hint {
  color: #64748b;
  line-height: 1.7;
  font-weight: 400;
}

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

@keyframes sceneReveal {
  from {
    opacity: 0;
    transform: translateY(18px) scale(.99);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes panelFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-4px); }
}

@keyframes pillFloat {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}

.rail-card-slide-enter-active,
.rail-card-slide-leave-active {
  transition: opacity .22s ease, transform .22s ease;
}

.rail-card-slide-enter-from,
.rail-card-slide-leave-to {
  opacity: 0;
  transform: translateX(10px) scale(.98);
}

@media (prefers-reduced-motion: reduce) {
  .motion-ready .sidebar,
  .motion-ready .chat-main,
  .motion-ready .analysis-panel,
  .motion-ready .sidebar-overview,
  .chat-hero-bar,
  .messages-wrap,
  .input-zone,
  .chat-utility-card,
  .welcome-shell,
  .chat-hero-pill {
    animation: none !important;
    opacity: 1 !important;
    transform: none !important;
  }
}

@media (max-width: 1360px) {
  .chat-layout {
    gap: 14px;
    padding: 14px;
  }

  .chat-hero-bar {
    grid-template-columns: 1fr;
  }

  .chat-hero-copy h1 {
    max-width: none;
  }
}

@media (max-width: 1180px) {
  .hot-rank-rail,
  .composer-rail,
  .analysis-panel-fab-wrap {
    display: none;
  }
  .analysis-panel {
    display: none;
  }
}

@media (max-width: 960px) {
  .chat-layout {
    padding: 10px;
    gap: 10px;
  }

  .sidebar {
    display: none;
  }

  .chat-stage {
    padding: 14px;
  }

  .chat-hero-pills,
  .welcome-metrics,
  .example-grid {
    grid-template-columns: 1fr;
  }

  .workspace-feedback {
    margin: 0 0 10px;
  }

  .messages-wrap {
    padding: 18px 16px 8px;
  }

  .bubble-wrap {
    max-width: 84%;
  }

  .input-foot,
  .composer-head,
  .composer-status,
  .hot-rank-head {
    flex-direction: column;
    align-items: stretch;
  }

  .composer-chip {
    align-self: flex-start;
  }

  .hot-rank-list {
    grid-template-columns: 1fr;
  }
}
</style>
