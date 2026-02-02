import { useChat } from './hooks/useChat'
import { ChatMessages } from './components/ChatMessages'
import { ChatInput } from './components/ChatInput'

export default function App() {
  const { messages, isConnected, isStreaming, sendMessage } = useChat()

  return (
    <div className="app">
      <header className="header">
        <h1>Gobby</h1>
        <span className={`status ${isConnected ? 'connected' : 'disconnected'}`}>
          {isConnected ? 'Connected' : 'Disconnected'}
        </span>
      </header>

      <main className="chat-container">
        <ChatMessages messages={messages} isStreaming={isStreaming} />
        <ChatInput onSend={sendMessage} disabled={!isConnected || isStreaming} />
      </main>
    </div>
  )
}
