import { useState } from 'react'
import { useChat } from './hooks/useChat'
import { useSettings } from './hooks/useSettings'
import { ChatMessages } from './components/ChatMessages'
import { ChatInput } from './components/ChatInput'
import { Settings, SettingsIcon } from './components/Settings'

export default function App() {
  const { messages, isConnected, isStreaming, sendMessage } = useChat()
  const { settings, updateFontSize, resetSettings } = useSettings()
  const [settingsOpen, setSettingsOpen] = useState(false)

  return (
    <div className="app">
      <header className="header">
        <h1>Gobby</h1>
        <div className="header-actions">
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
        <ChatInput onSend={sendMessage} disabled={!isConnected || isStreaming} />
      </main>

      <Settings
        isOpen={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        settings={settings}
        onFontSizeChange={updateFontSize}
        onReset={resetSettings}
      />
    </div>
  )
}
