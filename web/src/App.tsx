import { useState } from 'react'
import { useChat } from './hooks/useChat'
import { useSettings } from './hooks/useSettings'
import { useTerminal } from './hooks/useTerminal'
import { ChatMessages } from './components/ChatMessages'
import { ChatInput } from './components/ChatInput'
import { Settings, SettingsIcon } from './components/Settings'
import { TerminalPanel } from './components/Terminal'

export default function App() {
  const { messages, isConnected, isStreaming, sendMessage, stopStreaming, clearHistory } = useChat()
  const { settings, modelInfo, modelsLoading, updateFontSize, updateModel, resetSettings } = useSettings()
  const { agents, selectedAgent, setSelectedAgent, sendInput, onOutput } = useTerminal()
  const [settingsOpen, setSettingsOpen] = useState(false)
  const [terminalOpen, setTerminalOpen] = useState(false)

  // Wrap sendMessage to include the selected model
  const handleSendMessage = (content: string) => {
    sendMessage(content, settings.model)
  }

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
          {messages.length > 0 && (
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

      <main className="chat-container">
        <ChatMessages messages={messages} isStreaming={isStreaming} />
        <ChatInput onSend={handleSendMessage} onStop={stopStreaming} isStreaming={isStreaming} disabled={!isConnected} />
      </main>

      <TerminalPanel
        isOpen={terminalOpen}
        onToggle={() => setTerminalOpen(!terminalOpen)}
        runId={selectedAgent}
        agents={agents}
        selectedAgent={selectedAgent}
        onSelectAgent={setSelectedAgent}
        onInput={sendInput}
        onOutput={onOutput}
      />

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
