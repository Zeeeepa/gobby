import { useState, useCallback, useMemo, useEffect, useRef, lazy, Suspense, Component, type ReactNode } from 'react'
import { useAuth } from './hooks/useAuth'
import { useChat } from './hooks/useChat'
import { useVoice } from './hooks/useVoice'
import { useSettings } from './hooks/useSettings'
import { useTerminal } from './hooks/useTerminal'
import { useTmuxSessions } from './hooks/useTmuxSessions'
import { useSlashCommands } from './hooks/useSlashCommands'
import { useSessions } from './hooks/useSessions'
import type { QueuedFile, ChatMode } from './types/chat'
import { Settings } from './components/Settings'
import { Sidebar } from './components/Sidebar'
import { ChatPage } from './components/chat/ChatPage'
import { LoginPage } from './components/auth/LoginPage'
import { ProjectSelector } from './components/ProjectSelector'
import { QuickCaptureTask } from './components/tasks/QuickCaptureTask'
import { SlashCommandModal } from './components/command-browser/SlashCommandModal'
import type { GobbySession } from './hooks/useSessions'

// Lazy-load non-default page components for code splitting
const SessionsPage = lazy(() => import('./components/SessionsPage').then(m => ({ default: m.SessionsPage })))
const TerminalsPage = lazy(() => import('./components/TerminalsPage').then(m => ({ default: m.TerminalsPage })))
const MemoryPage = lazy(() => import('./components/MemoryPage').then(m => ({ default: m.MemoryPage })))
const ProjectsPage = lazy(() => import('./components/ProjectsPage').then(m => ({ default: m.ProjectsPage })))
const TasksPage = lazy(() => import('./components/TasksPage').then(m => ({ default: m.TasksPage })))
const SkillsPage = lazy(() => import('./components/SkillsPage').then(m => ({ default: m.SkillsPage })))
const McpPage = lazy(() => import('./components/McpPage').then(m => ({ default: m.McpPage })))
const CronJobsPage = lazy(() => import('./components/CronJobsPage').then(m => ({ default: m.CronJobsPage })))
const ConfigurationPage = lazy(() => import('./components/ConfigurationPage').then(m => ({ default: m.ConfigurationPage })))
const WorkflowsPage = lazy(() => import('./components/WorkflowsPage').then(m => ({ default: m.WorkflowsPage })))
const GitHubPage = lazy(() => import('./components/GitHubPage').then(m => ({ default: m.GitHubPage })))
const DashboardPage = lazy(() => import('./components/DashboardPage').then(m => ({ default: m.DashboardPage })))

class AppErrorBoundary extends Component<
  { children: ReactNode; activeTab: string; onReturnToChat: () => void },
  { hasError: boolean; error: Error | null }
> {
  constructor(props: { children: ReactNode; activeTab: string; onReturnToChat: () => void }) {
    super(props)
    this.state = { hasError: false, error: null }
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[AppErrorBoundary] Caught error in tab:', this.props.activeTab, error, info)
  }
  componentDidUpdate(prevProps: { activeTab: string }) {
    if (prevProps.activeTab !== this.props.activeTab && this.state.hasError) {
      this.setState({ hasError: false, error: null })
    }
  }
  render() {
    if (this.state.hasError) {
      return (
        <main style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', flex: 1, gap: '1rem', padding: '2rem', color: 'var(--text-secondary)' }}>
          <div style={{ fontSize: '1.25rem', color: 'var(--text-primary)', fontWeight: 600 }}>Something went wrong</div>
          <div style={{ fontSize: '0.85rem', maxWidth: 480, textAlign: 'center', lineHeight: 1.5 }}>
            An error occurred in the <b>{this.props.activeTab}</b> tab. This is usually caused by a rendering failure in a third-party library.
          </div>
          {this.state.error && (
            <code style={{ fontSize: '0.75rem', color: 'var(--text-muted)', background: 'var(--bg-secondary)', padding: '0.5rem 1rem', borderRadius: 4, maxWidth: 600, overflow: 'auto', whiteSpace: 'pre-wrap' }}>
              {this.state.error.message}
            </code>
          )}
          <div style={{ display: 'flex', gap: '0.5rem', marginTop: '0.5rem' }}>
            <button
              onClick={() => this.setState({ hasError: false, error: null })}
              style={{ padding: '0.4rem 1rem', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', cursor: 'pointer', fontSize: '0.8rem' }}
            >
              Try Again
            </button>
            <button
              onClick={this.props.onReturnToChat}
              style={{ padding: '0.4rem 1rem', borderRadius: 4, border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer', fontSize: '0.8rem' }}
            >
              Return to Chat
            </button>
          </div>
        </main>
      )
    }
    return this.props.children
  }
}

const HIDDEN_PROJECTS = new Set(['_orphaned', '_migrated'])

export default function App() {
  const { authRequired, authenticated, loading: authLoading, login, logout } = useAuth()
  const { messages, conversationId, sessionRef, dbSessionId, currentBranch, worktreePath, isConnected, isStreaming, isThinking, contextUsage, sendMessage, sendMode, sendWorktreeChange, stopStreaming, clearHistory, deleteConversation, executeCommand, respondToQuestion, respondToApproval, planPendingApproval, approvePlan, requestPlanChanges, switchConversation, startNewChat, continueSessionInChat, setOnModeChanged, setOnPlanReady, addSystemMessage, wsRef, handleVoiceMessageRef, canvasSurfaces, canvasPanel, onCanvasInteraction } = useChat()
  const voice = useVoice(wsRef, conversationId)
  const { settings, updateFontSize, updateModel, updateChatMode, updateTheme, updateDefaultChatMode, resetSettings } = useSettings()
  const { agents, refreshAgents } = useTerminal()
  const tmux = useTmuxSessions()
  const { filteredCommands, filterCommands } = useSlashCommands()
  const [activeModal, setActiveModal] = useState<'skills' | 'gobby' | 'mcp' | null>(null)
  const sessionsHook = useSessions()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<string>('chat')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(() => {
    try {
      const saved = localStorage.getItem('gobby-project')
      if (saved) return saved
      const old = localStorage.getItem('gobby-chat-project')
      if (old) {
        localStorage.setItem('gobby-project', old)
        localStorage.removeItem('gobby-chat-project')
        return old
      }
      return null
    } catch { return null }
  })
  const showPlanRef = useRef<(() => void) | null>(null)
  const [quickCaptureOpen, setQuickCaptureOpen] = useState(false)
  const [toastMessage, setToastMessage] = useState<string | null>(null)
  const toastTimerRef = useRef<number | null>(null)

  // Auto-synthesize chat title when streaming completes
  const wasStreamingRef = useRef(false)
  const titleSynthesisCountRef = useRef(0) // messages since last synthesis
  const sessionsRef = useRef(sessionsHook.sessions)
  sessionsRef.current = sessionsHook.sessions
  const refreshSessionsRef = useRef(sessionsHook.refresh)
  refreshSessionsRef.current = sessionsHook.refresh

  useEffect(() => {
    // Detect streaming transition: true → false (response completed)
    if (wasStreamingRef.current && !isStreaming) {
      titleSynthesisCountRef.current += 1

      // Use dbSessionId directly (set by backend session_info message) to avoid
      // race condition where the sessions list hasn't polled since registration
      const sessionId = dbSessionId

      if (sessionId) {
        // Check sessions list for current title (may be stale for new chats — that's OK)
        const currentSession = sessionsRef.current.find((s) => s.id === sessionId)
        const needsTitle = !currentSession?.title
        const periodicUpdate = titleSynthesisCountRef.current >= 4

        if (needsTitle || periodicUpdate) {
          titleSynthesisCountRef.current = 0
          const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
          fetch(`${baseUrl}/sessions/${sessionId}/synthesize-title`, { method: 'POST' })
            .then((res) => {
              if (!res.ok) {
                console.warn(`Title synthesis returned ${res.status}`)
                return null
              }
              return res.json()
            })
            .then((data) => {
              if (data?.title) refreshSessionsRef.current()
            })
            .catch(() => { /* title synthesis is non-critical */ })
        }
      }
    }
    wasStreamingRef.current = isStreaming
  }, [isStreaming, conversationId, dbSessionId])

  // Reset title synthesis counter on conversation switch
  useEffect(() => {
    titleSynthesisCountRef.current = 0
  }, [conversationId])

  // Global keyboard chord: Cmd+K → t opens quick capture task creation
  const chordPendingRef = useRef(false)
  const chordTimeoutRef = useRef<number | null>(null)

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Don't trigger when typing in inputs/textareas (unless quick capture is closed)
      const tag = (e.target as HTMLElement).tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return

      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        chordPendingRef.current = true
        if (chordTimeoutRef.current) window.clearTimeout(chordTimeoutRef.current)
        chordTimeoutRef.current = window.setTimeout(() => {
          chordPendingRef.current = false
        }, 1000)
        return
      }

      if (chordPendingRef.current && e.key === 't') {
        e.preventDefault()
        chordPendingRef.current = false
        if (chordTimeoutRef.current) window.clearTimeout(chordTimeoutRef.current)
        setQuickCaptureOpen(true)
      } else if (chordPendingRef.current) {
        // Any other key cancels the chord
        chordPendingRef.current = false
        if (chordTimeoutRef.current) window.clearTimeout(chordTimeoutRef.current)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => {
      window.removeEventListener('keydown', handleKeyDown)
      if (chordTimeoutRef.current) window.clearTimeout(chordTimeoutRef.current)
    }
  }, [])

  // Build project options for the selector (exclude internal system projects)
  const projectOptions = useMemo(
    () => sessionsHook.projects
      .filter((p) => !HIDDEN_PROJECTS.has(p.name))
      .map((p) => ({ id: p.id, name: p.name === '_personal' ? 'Personal' : p.name })),
    [sessionsHook.projects]
  )

  // Default to "gobby" in dev mode (Vite port 5173), "Personal" otherwise
  const defaultProjectId = useMemo(() => {
    const isDev = window.location.port === '5173'
    const preferred = isDev ? 'gobby' : 'Personal'
    return projectOptions.find((p) => p.name === preferred)?.id
      ?? projectOptions[0]?.id ?? null
  }, [projectOptions])

  const effectiveProjectId = selectedProjectId ?? defaultProjectId

  // Persist project selection
  useEffect(() => {
    try {
      if (selectedProjectId) localStorage.setItem('gobby-project', selectedProjectId)
      else localStorage.removeItem('gobby-project')
    } catch { /* noop */ }
  }, [selectedProjectId])

  // When project changes, start fresh chat context for the new project.
  // The ConversationPicker will show the new project's conversations.
  const prevProjectRef = useRef<string | null>(null)
  useEffect(() => {
    if (effectiveProjectId && prevProjectRef.current !== null && effectiveProjectId !== prevProjectRef.current) {
      startNewChat()
      initialReconciliationDone.current = false
    }
    prevProjectRef.current = effectiveProjectId ?? null
  }, [effectiveProjectId, startNewChat])

  // Sync global project filter into sessions hook for cross-page filtering
  useEffect(() => {
    sessionsHook.setFilters(prev => ({ ...prev, projectId: effectiveProjectId ?? null }))
  }, [effectiveProjectId])

  // Web-chat sessions for main conversation list
  const webChatSessions = useMemo(
    () => sessionsHook.filteredSessions.filter((s) => s.source === 'claude_sdk_web_chat'),
    [sessionsHook.filteredSessions]
  )

  // Auto-select most recent server session on initial load (cross-device sync)
  const initialReconciliationDone = useRef(false)

  useEffect(() => {
    if (initialReconciliationDone.current) return
    if (!effectiveProjectId || sessionsHook.isLoading) return

    initialReconciliationDone.current = true

    // Does the current localStorage conversation_id match any server session?
    const match = webChatSessions.find(s => s.external_id === conversationId)

    if (match) {
      // Valid session — hydrate messages from server (replaces stale localStorage)
      switchConversation(match.external_id, match.id)
    } else if (webChatSessions.length > 0) {
      // Unknown conversation_id — switch to most recent session
      const mostRecent = webChatSessions[0] // sorted newest-first
      switchConversation(mostRecent.external_id, mostRecent.id)
    }
    // else: no sessions for this project — keep fresh UUID, user starts new chat
  }, [effectiveProjectId, sessionsHook.isLoading, webChatSessions, conversationId, switchConversation])

  // Wrap sendMessage to include the selected model
  const handleSendMessage = useCallback((content: string, files?: QueuedFile[]) => {
    sendMessage(content, settings.model, files, effectiveProjectId)
  }, [sendMessage, settings.model, effectiveProjectId])

  // Chat page: only web-chat sessions are selectable
  const handleSelectConversation = useCallback((session: GobbySession) => {
    switchConversation(session.external_id, session.id)
  }, [switchConversation])

  const handleDeleteConversation = useCallback((session: GobbySession) => {
    deleteConversation(session.external_id, session.id)
    sessionsHook.removeSession(session.id)
  }, [deleteConversation, sessionsHook.removeSession])

  const showToast = useCallback((msg: string, durationMs = 3000) => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current)
    setToastMessage(msg)
    toastTimerRef.current = window.setTimeout(() => setToastMessage(null), durationMs)
  }, [])

  // Refresh terminal list when switching to terminals tab
  useEffect(() => {
    if (activeTab === 'terminals') {
      tmux.refreshSessions()
    }
  }, [activeTab, tmux.refreshSessions])

  /* Navigate to Terminals tab and attach agent's tmux session */
  const handleNavigateToAgent = useCallback((agent: { run_id: string; tmux_session_name?: string }) => {
    if (!agent.tmux_session_name) return
    // Verify the tmux session still exists before navigating
    const sessionExists = tmux.sessions.some(s => s.name === agent.tmux_session_name)
    if (!sessionExists) {
      // Agent's session is gone — refresh agent list to clear stale entries and notify user
      refreshAgents()
      showToast('Agent session has ended')
      return
    }
    setActiveTab('terminals')
    tmux.attachSession(agent.tmux_session_name, 'gobby')
  }, [tmux, refreshAgents, showToast])

  /* "Ask Gobby about this session" from Sessions page */
  const handleAskGobby = useCallback((context: string) => {
    setActiveTab('chat')
    // Defer to next macrotask so the tab switch state update is flushed
    setTimeout(() => {
      try {
        if (!isConnected) {
          console.warn('Cannot ask Gobby: disconnected')
          return
        }
        const sent = sendMessage(context, settings.model)
        if (!sent) {
          console.error('Failed to send message to Gobby')
        }
      } catch (e) {
        console.error('Error in handleAskGobby:', e)
      }
    }, 0)
  }, [sendMessage, settings.model, isConnected])

  /* "Resume Session" from Sessions page — continue CLI session in web chat */
  const handleContinueInChat = useCallback(async (session: GobbySession) => {
    setActiveTab('chat')
    await continueSessionInChat(session.id, session.project_id)
  }, [continueSessionInChat])

  // Wire voice message handler into useChat's WebSocket routing
  useEffect(() => {
    handleVoiceMessageRef.current = voice.handleVoiceMessage
  }, [voice.handleVoiceMessage, handleVoiceMessageRef])

  // Wire backend-initiated mode changes (e.g. agent EnterPlanMode/ExitPlanMode)
  // to update the settings slider
  useEffect(() => {
    setOnModeChanged(updateChatMode)
  }, [updateChatMode, setOnModeChanged])

  // Restore persisted mode on conversation switch (DB value > user default > plan)
  useEffect(() => {
    if (sessionsHook.isLoading) return
    const session = webChatSessions.find(s => s.external_id === conversationId)
    const restoredMode = (session?.chat_mode as ChatMode | null) || settings.defaultChatMode
    updateChatMode(restoredMode)
    sendMode(restoredMode)
  }, [conversationId, sessionsHook.isLoading]) // eslint-disable-line react-hooks/exhaustive-deps

  const handleInputChange = useCallback((value: string) => {
    filterCommands(value)
  }, [filterCommands])

  const handleCommandSelect = useCallback((cmd: { name: string; action: string }) => {
    if (cmd.action === 'open_skills') { setActiveModal('skills'); return }
    if (cmd.action === 'open_gobby') { setActiveModal('gobby'); return }
    if (cmd.action === 'open_mcp') { setActiveModal('mcp'); return }
    if (cmd.action === 'open_settings') { setSettingsOpen(true); return }
    if (cmd.action === 'clear_history') { clearHistory(); return }
    if (cmd.action === 'compact_chat') {
      sendMessage('/compact', settings.model, undefined, effectiveProjectId)
      return
    }
    if (cmd.action === 'restart_daemon') {
      addSystemMessage('Restarting daemon...')
      const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
      fetch(`${baseUrl}/admin/restart`, { method: 'POST' })
        .catch(err => console.error('Restart request failed:', err))
      return
    }
    if (cmd.action === 'show_plan') {
      if (settings.chatMode !== 'plan') {
        updateChatMode('plan')
        sendMode('plan')
      }
      showPlanRef.current?.()
    }
  }, [clearHistory, sendMessage, settings.model, effectiveProjectId, updateChatMode, sendMode, addSystemMessage])

  // Auth guard — shown after all hooks (React rules)
  if (authLoading) {
    return (
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '100vh', background: 'var(--bg-primary)', color: 'var(--text-secondary)' }}>
        Loading...
      </div>
    )
  }
  if (authRequired && !authenticated) {
    return <LoginPage onLogin={login} />
  }

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: <DashboardIcon /> },
    { id: 'chat', label: 'Chat', icon: <ChatIcon /> },
    { id: 'sessions', label: 'Sessions', icon: <SessionsIcon /> },
    { id: 'terminals', label: 'Terminals', icon: <TerminalIcon /> },
    { id: 'projects', label: 'Projects', icon: <ProjectsIcon />, separator: true },
    { id: 'tasks', label: 'Tasks', icon: <TasksIcon /> },
    { id: 'workflows', label: 'Workflows', icon: <WorkflowsIcon /> },
    { id: 'source-control', label: 'GitHub', icon: <GitHubIcon /> },
    { id: 'cron', label: 'Cron Jobs', icon: <CronIcon /> },
    { id: 'memory', label: 'Memory', icon: <MemoryIcon /> },
    { id: 'skills', label: 'Skills', icon: <SkillsIcon /> },
    { id: 'mcp', label: 'MCP', icon: <McpIcon /> },
    { id: 'configuration', label: 'Configuration', icon: <ConfigurationIcon />, separator: true },
  ]

  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <button
            className="hamburger-button"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            title="Toggle menu"
            aria-label="Toggle navigation menu"
          >
            <HamburgerIcon />
          </button>
          <img src="/logo.png" alt="Gobby logo" className="header-logo" />
          <span className="header-title">Gobby</span>
        </div>
        <div className="header-actions">
          {projectOptions.length > 0 && (
            <ProjectSelector
              projects={projectOptions}
              selectedProjectId={effectiveProjectId}
              onProjectChange={setSelectedProjectId}
              dropDirection="down"
            />
          )}
          <span className={`status ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
          {authRequired && authenticated && (
            <button
              onClick={logout}
              title="Sign out"
              style={{ padding: '0.3rem 0.7rem', borderRadius: 4, border: '1px solid var(--border)', background: 'transparent', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '0.8rem' }}
            >
              Logout
            </button>
          )}
        </div>
      </header>

      <Sidebar
        items={navItems}
        activeItem={activeTab}
        isOpen={sidebarOpen}
        onItemSelect={setActiveTab}
        onClose={() => setSidebarOpen(false)}
      />

      <AppErrorBoundary activeTab={activeTab} onReturnToChat={() => setActiveTab('chat')}>
      <Suspense fallback={<main style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1, color: 'var(--text-secondary)' }}>Loading...</main>}>
      {activeTab === 'chat' ? (
        <ChatPage
          projectId={effectiveProjectId}
          showPlanRef={showPlanRef}
          chat={{
            messages,
            sessionRef,
            currentBranch,
            worktreePath,
            isStreaming,
            isThinking,
            isConnected,
            contextUsage,
            onSend: handleSendMessage,
            onStop: stopStreaming,
            onRespondToQuestion: respondToQuestion,
            onRespondToApproval: respondToApproval,
            onInputChange: handleInputChange,
            filteredCommands,
            onCommandSelect: handleCommandSelect,
            mode: settings.chatMode,
            onModeChange: (mode) => { updateChatMode(mode); sendMode(mode) },
            onWorktreeChange: sendWorktreeChange,
            planPendingApproval,
            onApprovePlan: approvePlan,
            onRequestPlanChanges: requestPlanChanges,
            setOnPlanReady,
            canvasSurfaces,
            canvasPanel,
            onCanvasInteraction,
          }}
          conversations={{
            sessions: webChatSessions,
            activeSessionId: conversationId,
            onNewChat: startNewChat,
            onSelectSession: handleSelectConversation,
            onDeleteSession: handleDeleteConversation,
            onRenameSession: sessionsHook.renameSession,
            onRefresh: sessionsHook.refresh,
            agents,
            onNavigateToAgent: handleNavigateToAgent,
          }}
          voice={{
            voiceMode: voice.voiceMode,
            voiceAvailable: voice.voiceAvailable,
            isListening: voice.isListening,
            isSpeechDetected: voice.isSpeechDetected,
            isTranscribing: voice.isTranscribing,
            isSpeaking: voice.isSpeaking,
            voiceError: voice.voiceError,
            onToggleVoice: voice.toggleVoiceMode,
            onStopSpeaking: voice.stopSpeaking,
          }}
        />
      ) : activeTab === 'sessions' ? (
        <SessionsPage
          sessions={sessionsHook.filteredSessions}
          filters={sessionsHook.filters}
          onFiltersChange={sessionsHook.setFilters}
          isLoading={sessionsHook.isLoading}
          onRefresh={sessionsHook.refresh}
          onAskGobby={handleAskGobby}
          onContinueInChat={handleContinueInChat}
          onRenameSession={sessionsHook.renameSession}
        />
      ) : activeTab === 'terminals' ? (
        <TerminalsPage
          sessions={tmux.sessions}
          attachedSession={tmux.attachedSession}
          streamingId={tmux.streamingId}
          isLoading={tmux.isLoading}
          sessionEnded={tmux.sessionEnded}
          attachSession={tmux.attachSession}
          createSession={tmux.createSession}
          killSession={tmux.killSession}
          refreshSessions={tmux.refreshSessions}
          refreshTerminal={tmux.refreshTerminal}
          dismissEndedSession={tmux.dismissEndedSession}
          sendInput={tmux.sendInput}
          resizeTerminal={tmux.resizeTerminal}
          onOutput={tmux.onOutput}
        />
      ) : activeTab === 'projects' ? (
        <ProjectsPage />
      ) : activeTab === 'tasks' ? (
        <TasksPage projectFilter={effectiveProjectId} />
      ) : activeTab === 'memory' ? (
        <MemoryPage projectId={effectiveProjectId} />
      ) : activeTab === 'cron' ? (
        <CronJobsPage />
      ) : activeTab === 'skills' ? (
        <SkillsPage />
      ) : activeTab === 'workflows' ? (
        <WorkflowsPage projectId={effectiveProjectId} />
      ) : activeTab === 'mcp' ? (
        <McpPage />
      ) : activeTab === 'source-control' ? (
        <GitHubPage projectId={effectiveProjectId} />
      ) : activeTab === 'configuration' ? (
        <ConfigurationPage />
      ) : activeTab === 'dashboard' ? (
        <DashboardPage />
      ) : (
        <ComingSoonPage title={navItems.find(i => i.id === activeTab)?.label ?? activeTab} />
      )}
      </Suspense>
      </AppErrorBoundary>

      <Settings
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        onFontSizeChange={updateFontSize}
        onModelChange={updateModel}
        onThemeChange={updateTheme}
        onDefaultChatModeChange={updateDefaultChatMode}
        onReset={resetSettings}
      />

      <QuickCaptureTask
        isOpen={quickCaptureOpen}
        onClose={() => setQuickCaptureOpen(false)}
      />

      <SlashCommandModal
        modal={activeModal}
        onClose={() => setActiveModal(null)}
        onExecuteTool={(server, tool, args) => {
          const strArgs: Record<string, string> = {}
          for (const [k, v] of Object.entries(args)) {
            if (v !== undefined && v !== null) strArgs[k] = typeof v === 'string' ? v : JSON.stringify(v)
          }
          executeCommand(server, tool, strArgs)
        }}
        onRunSkill={(skillName) => {
          sendMessage(`/skill:${skillName}`, settings.model, undefined, effectiveProjectId)
        }}
      />

      {toastMessage && (
        <div className="app-toast" onClick={() => setToastMessage(null)}>
          {toastMessage}
        </div>
      )}
    </div>
  )
}

function HamburgerIcon() {
  return (
    <svg
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="3" y1="6" x2="21" y2="6" />
      <line x1="3" y1="12" x2="21" y2="12" />
      <line x1="3" y1="18" x2="21" y2="18" />
    </svg>
  )
}

function DashboardIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="9" />
      <rect x="14" y="3" width="7" height="5" />
      <rect x="14" y="12" width="7" height="9" />
      <rect x="3" y="16" width="7" height="5" />
    </svg>
  )
}

function SessionsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
      <line x1="8" y1="21" x2="16" y2="21" />
      <line x1="12" y1="17" x2="12" y2="21" />
    </svg>
  )
}

function TerminalIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" y1="19" x2="20" y2="19" />
    </svg>
  )
}

function ComingSoonPage({ title }: { title: string }) {
  return (
    <main className="coming-soon-page">
      <div className="coming-soon-content">
        <h2>{title}</h2>
        <p>Coming Soon</p>
      </div>
    </main>
  )
}

function TasksIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 11l3 3L22 4" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    </svg>
  )
}

function ProjectsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="7" height="7" />
      <rect x="14" y="3" width="7" height="7" />
      <rect x="3" y="14" width="7" height="7" />
      <rect x="14" y="14" width="7" height="7" />
    </svg>
  )
}

function WorkflowsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="6" y1="3" x2="6" y2="15" />
      <circle cx="18" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M18 9a9 9 0 0 1-9 9" />
    </svg>
  )
}

function MemoryIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <ellipse cx="12" cy="5" rx="9" ry="3" />
      <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
      <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
    </svg>
  )
}

function SkillsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
    </svg>
  )
}

function CronIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}

function GitHubIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.38 13.38 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22" />
    </svg>
  )
}

function McpIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <circle cx="4" cy="6" r="2" />
      <circle cx="20" cy="6" r="2" />
      <circle cx="4" cy="18" r="2" />
      <circle cx="20" cy="18" r="2" />
      <line x1="6" y1="6" x2="9.5" y2="10" />
      <line x1="18" y1="6" x2="14.5" y2="10" />
      <line x1="6" y1="18" x2="9.5" y2="14" />
      <line x1="18" y1="18" x2="14.5" y2="14" />
    </svg>
  )
}

function ChatIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
      <path d="M8 10h8" />
      <path d="M8 14h4" />
    </svg>
  )
}

function ConfigurationIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  )
}
