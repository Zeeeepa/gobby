import { useState } from 'react'
import { useChat } from './hooks/useChat'
import { useSettings } from './hooks/useSettings'
import { useTerminal } from './hooks/useTerminal'
import { ChatMessages } from './components/ChatMessages'
import { ChatInput } from './components/ChatInput'
import { Settings, SettingsIcon } from './components/Settings'
import { TerminalPanel } from './components/Terminal'

export default function App() {
  const { messages, isConnected, isStreaming, sendMessage } = useChat()
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
        <h1>Gobby</h1>
        <div className="header-actions">
          {settings.model && (
            <span className="model-indicator" title={`Using ${settings.model}`}>
              {settings.model}
            </span>
          )}
          <span className={`status ${isConnected ? 'connected' : 'disconnected'}`}>
            {isConnected ? 'Connected' : 'Disconnected'}
          </span>
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
        <ChatInput onSend={handleSendMessage} disabled={!isConnected || isStreaming} />
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
