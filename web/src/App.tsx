import { useState, useCallback } from 'react'
import { useChat } from './hooks/useChat'
import { useSettings } from './hooks/useSettings'
import { useTerminal } from './hooks/useTerminal'
import { useTmuxSessions } from './hooks/useTmuxSessions'
import { useSlashCommands } from './hooks/useSlashCommands'
import { ChatMessages } from './components/ChatMessages'
import { ChatInput } from './components/ChatInput'
import { Settings, SettingsIcon } from './components/Settings'
import { TerminalPanel } from './components/Terminal'
import { TabBar } from './components/TabBar'
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

  // Wrap sendMessage to include the selected model and handle slash commands
  const handleSendMessage = useCallback((content: string) => {
    // Check for slash command first
    const cmd = parseCommand(content)
    if (cmd) {
      executeCommand(cmd.server, cmd.tool, cmd.args)
      return
    }
    sendMessage(content, settings.model)
  }, [parseCommand, executeCommand, sendMessage, settings.model])

  const handleInputChange = useCallback((value: string) => {
    filterCommands(value)
  }, [filterCommands])

  const handleCommandSelect = useCallback((cmd: { server: string; tool: string }) => {
    executeCommand(cmd.server, cmd.tool)
  }, [executeCommand])

  const tabs = [
    { id: 'chat', label: 'Chat' },
    { id: 'terminals', label: 'Terminals', badge: tmux.sessions.length },
  ]

  return (
    <div className="app">
      <header className="header">
        <div className="header-brand">
          <img src="/logo.png" alt="Gobby logo" className="header-logo" />
          <h1>Gobby</h1>
        </div>
        <div className="header-actions">
          {settings.model && (
            <span className="model-indicator" title={`Using ${settings.model}`}>
              {settings.model}
            </span>
          )}
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
          <button
            className="settings-button"
            onClick={() => setSettingsOpen(true)}
            title="Settings"
          >
            <SettingsIcon />
          </button>
        </div>
      </header>

      <TabBar tabs={tabs} activeTab={activeTab} onTabChange={setActiveTab} />

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
      ) : (
        <TerminalsPage
          sessions={tmux.sessions}
          attachedSession={tmux.attachedSession}
          streamingId={tmux.streamingId}
          isLoading={tmux.isLoading}
          attachSession={tmux.attachSession}
          detachSession={tmux.detachSession}
          createSession={tmux.createSession}
          killSession={tmux.killSession}
          refreshSessions={tmux.refreshSessions}
          sendInput={tmux.sendInput}
          resizeTerminal={tmux.resizeTerminal}
          onOutput={tmux.onOutput}
        />
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
