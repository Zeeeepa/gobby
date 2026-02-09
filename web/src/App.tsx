import { useState, useCallback } from 'react'
import { useChat } from './hooks/useChat'
import { useSettings } from './hooks/useSettings'
import { useTerminal } from './hooks/useTerminal'
import { useTmuxSessions } from './hooks/useTmuxSessions'
import { useSlashCommands } from './hooks/useSlashCommands'
import { ChatMessages } from './components/ChatMessages'
import { ChatInput } from './components/ChatInput'
import type { QueuedFile } from './components/ChatInput'
import { Settings } from './components/Settings'
import { TerminalPanel } from './components/Terminal'
import { Sidebar } from './components/Sidebar'
import { TerminalsPage } from './components/TerminalsPage'

export default function App() {
  const { messages, isConnected, isStreaming, isThinking, sendMessage, stopStreaming, clearHistory, executeCommand, respondToQuestion } = useChat()
  const { settings, modelInfo, modelsLoading, updateFontSize, updateModel, resetSettings } = useSettings()
  const { agents, selectedAgent, setSelectedAgent, sendInput, onOutput } = useTerminal()
  const tmux = useTmuxSessions()
  const { filteredCommands, parseCommand, filterCommands } = useSlashCommands()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [terminalOpen, setTerminalOpen] = useState(false)
  const [activeTab, setActiveTab] = useState<string>('chat')
  const [sidebarOpen, setSidebarOpen] = useState(false)

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
    sendMessage(content, settings.model, files)
  }, [parseCommand, executeCommand, sendMessage, settings.model])

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
    { id: 'terminals', label: 'Terminals', icon: <TerminalIcon /> },
    { id: 'files', label: 'Files', icon: <FilesIcon /> },
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
        <>
          <main className="chat-container">
            <ChatMessages messages={messages} isStreaming={isStreaming} isThinking={isThinking} onRespondToQuestion={respondToQuestion} />
            <ChatInput
              onSend={handleSendMessage}
              onStop={stopStreaming}
              isStreaming={isStreaming}
              disabled={!isConnected}
              onInputChange={handleInputChange}
              filteredCommands={filteredCommands}
              onCommandSelect={handleCommandSelect}
            />
          </main>

          <TerminalPanel
            isOpen={terminalOpen}
            onToggle={() => setTerminalOpen(!terminalOpen)}
            agents={agents}
            selectedAgent={selectedAgent}
            onSelectAgent={setSelectedAgent}
            onInput={sendInput}
            onOutput={onOutput}
          />
        </>
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
        <div className="files-placeholder">
          <h3>Files</h3>
          <p>Coming soon</p>
        </div>
      ) : null}

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
