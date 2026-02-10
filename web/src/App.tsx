import { useState, useCallback, useMemo } from 'react'
import { useChat } from './hooks/useChat'
import { useSettings } from './hooks/useSettings'
import { useTerminal } from './hooks/useTerminal'
import { useTmuxSessions } from './hooks/useTmuxSessions'
import { useSlashCommands } from './hooks/useSlashCommands'
import { useFiles } from './hooks/useFiles'
import { useSessions } from './hooks/useSessions'
import type { QueuedFile } from './components/ChatInput'
import { Settings } from './components/Settings'
import { Sidebar } from './components/Sidebar'
import { ChatPage } from './components/ChatPage'
import { SessionsPage } from './components/SessionsPage'
import { TerminalsPage } from './components/TerminalsPage'
import { FilesPage } from './components/FilesPage'
import type { GobbySession } from './hooks/useSessions'

export default function App() {
  const { messages, conversationId, isConnected, isStreaming, isThinking, sendMessage, stopStreaming, clearHistory, executeCommand, respondToQuestion, switchConversation, startNewChat } = useChat()
  const { settings, modelInfo, modelsLoading, updateFontSize, updateModel, resetSettings } = useSettings()
  const { agents, selectedAgent, setSelectedAgent, sendInput, onOutput } = useTerminal()
  const tmux = useTmuxSessions()
  const files = useFiles()
  const { filteredCommands, parseCommand, filterCommands } = useSlashCommands()
  const sessionsHook = useSessions()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [terminalOpen, setTerminalOpen] = useState(true)
  const [activeTab, setActiveTab] = useState<string>('chat')
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null)

  // Build project options for the selector (exclude internal system projects)
  const HIDDEN_PROJECTS = new Set(['_orphaned', '_migrated'])
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

  // Web-chat sessions only (for ConversationPicker in ChatPage)
  const webChatSessions = useMemo(
    () => sessionsHook.filteredSessions.filter((s) => s.source === 'web-chat'),
    [sessionsHook.filteredSessions]
  )

  // Wrap sendMessage to include the selected model and handle slash commands
  const handleSendMessage = useCallback((content: string, files?: QueuedFile[]) => {
    // Check for slash command first
    const cmd = parseCommand(content)
    if (cmd) {
      // Intercept local commands
      if (cmd.server === '_local') {
        if (cmd.tool === 'open_settings') {
          setSettingsOpen(true)
        }
        return
      }
      executeCommand(cmd.server, cmd.tool, cmd.args)
      return
    }
    sendMessage(content, settings.model, files, effectiveProjectId)
  }, [parseCommand, executeCommand, sendMessage, settings.model, effectiveProjectId])

  // Chat page: only web-chat sessions are selectable
  const handleSelectConversation = useCallback((session: GobbySession) => {
    switchConversation(session.external_id)
  }, [switchConversation])

  // "Ask Gobby about this session" from Sessions page
  const handleAskGobby = useCallback((context: string) => {
    setActiveTab('chat')
    // Send the context as a new message after switching to chat
    setTimeout(() => {
      sendMessage(context, settings.model)
    }, 100)
  }, [sendMessage, settings.model])

  const handleInputChange = useCallback((value: string) => {
    filterCommands(value)
  }, [filterCommands])

  const handleCommandSelect = useCallback((cmd: { server: string; tool: string; isLocal?: boolean; action?: string }) => {
    if (cmd.server === '_local') {
      if (cmd.action === 'open_settings' || cmd.tool === 'open_settings') {
        setSettingsOpen(true)
      }
      return
    }
    executeCommand(cmd.server, cmd.tool)
  }, [executeCommand])

  const navItems = [
    { id: 'chat', label: 'Chat', icon: <ChatIcon /> },
    { id: 'sessions', label: 'Sessions', icon: <SessionsIcon /> },
    { id: 'terminals', label: 'Terminals', icon: <TerminalIcon /> },
    { id: 'files', label: 'Files', icon: <FilesIcon /> },
    { id: 'tasks', label: 'Tasks', icon: <TasksIcon />, separator: true },
    { id: 'projects', label: 'Projects', icon: <ProjectsIcon /> },
    { id: 'agents', label: 'Agents', icon: <AgentsIcon /> },
    { id: 'workflows', label: 'Workflows', icon: <WorkflowsIcon /> },
    { id: 'memory', label: 'Memory', icon: <MemoryIcon /> },
    { id: 'skills', label: 'Skills', icon: <SkillsIcon /> },
    { id: 'artifacts', label: 'Artifacts', icon: <ArtifactsIcon /> },
    { id: 'worktrees', label: 'Worktrees/Clones', icon: <WorktreesIcon /> },
    { id: 'configuration', label: 'Configuration', icon: <ConfigurationIcon /> },
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
          <h1>Gobby</h1>
        </div>
        <div className="header-actions">
          <span className={`status ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
          {messages.length > 0 && activeTab === 'chat' && (
            <button
              className="settings-button"
              onClick={clearHistory}
              title="Clear chat history"
            >
              <TrashIcon />
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

      {activeTab === 'chat' ? (
        <ChatPage
          messages={messages}
          conversationId={conversationId}
          isStreaming={isStreaming}
          isThinking={isThinking}
          isConnected={isConnected}
          onSend={handleSendMessage}
          onStop={stopStreaming}
          onRespondToQuestion={respondToQuestion}
          onInputChange={handleInputChange}
          filteredCommands={filteredCommands}
          onCommandSelect={handleCommandSelect}
          webChatSessions={webChatSessions}
          activeSessionId={conversationId}
          onNewChat={startNewChat}
          onSelectSession={handleSelectConversation}
          terminalOpen={terminalOpen}
          onTerminalToggle={() => setTerminalOpen(!terminalOpen)}
          agents={agents}
          selectedAgent={selectedAgent}
          onSelectAgent={setSelectedAgent}
          onTerminalInput={sendInput}
          onTerminalOutput={onOutput}
          projects={projectOptions}
          selectedProjectId={effectiveProjectId}
          onProjectChange={setSelectedProjectId}
        />
      ) : activeTab === 'sessions' ? (
        <SessionsPage
          sessions={sessionsHook.filteredSessions}
          projects={sessionsHook.projects}
          filters={sessionsHook.filters}
          onFiltersChange={sessionsHook.setFilters}
          isLoading={sessionsHook.isLoading}
          onRefresh={sessionsHook.refresh}
          onAskGobby={handleAskGobby}
        />
      ) : activeTab === 'terminals' ? (
        <TerminalsPage
          sessions={tmux.sessions}
          attachedSession={tmux.attachedSession}
          streamingId={tmux.streamingId}
          isLoading={tmux.isLoading}
          attachSession={tmux.attachSession}
          createSession={tmux.createSession}
          killSession={tmux.killSession}
          refreshSessions={tmux.refreshSessions}
          sendInput={tmux.sendInput}
          resizeTerminal={tmux.resizeTerminal}
          onOutput={tmux.onOutput}
        />
      ) : activeTab === 'files' ? (
        <FilesPage
          projects={files.projects}
          expandedDirs={files.expandedDirs}
          expandedProjects={files.expandedProjects}
          openFiles={files.openFiles}
          activeFileIndex={files.activeFileIndex}
          loadingDirs={files.loadingDirs}
          gitStatuses={files.gitStatuses}
          onExpandProject={files.expandProject}
          onExpandDir={files.expandDir}
          onOpenFile={files.openFile}
          onCloseFile={files.closeFile}
          onSetActiveFile={files.setActiveFileIndex}
          getImageUrl={files.getImageUrl}
          onToggleEditing={files.toggleEditing}
          onUpdateEditContent={files.updateEditContent}
          onSaveFile={files.saveFile}
          onFetchDiff={files.fetchDiff}
        />
      ) : (
        <ComingSoonPage title={navItems.find(i => i.id === activeTab)?.label ?? activeTab} />
      )}

      <Settings
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        modelInfo={modelInfo}
        modelsLoading={modelsLoading}
        onFontSizeChange={updateFontSize}
        onModelChange={updateModel}
        onReset={resetSettings}
      />
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

function ChatIcon() {
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
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
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

function FilesIcon() {
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
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
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

function AgentsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="10" rx="2" />
      <circle cx="12" cy="5" r="4" />
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

function ArtifactsIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
      <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
      <line x1="12" y1="22.08" x2="12" y2="12" />
    </svg>
  )
}

function WorktreesIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="18" r="3" />
      <circle cx="6" cy="6" r="3" />
      <circle cx="18" cy="6" r="3" />
      <path d="M12 15V9" />
      <path d="M9 7.5L12 9l3-1.5" />
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

function TrashIcon() {
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
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  )
}
