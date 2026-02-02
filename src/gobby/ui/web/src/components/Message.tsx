import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: Date
}

interface MessageProps {
  message: ChatMessage
  isStreaming?: boolean
}

export function Message({ message, isStreaming = false }: MessageProps) {
  return (
    <div className={`message message-${message.role}`}>
      <div className="message-header">
        <span className="message-role">
          {message.role === 'user' ? 'You' : message.role === 'assistant' ? 'Gobby' : 'System'}
        </span>
        <span className="message-time">
          {message.timestamp.toLocaleTimeString()}
        </span>
      </div>
      <div className="message-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {message.content}
        </ReactMarkdown>
        {isStreaming && <span className="cursor" />}
      </div>
    </div>
  )
}
