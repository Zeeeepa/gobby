import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { ToolCallDisplay } from './ToolCallDisplay'
import { markdownComponents } from './CodeBlock'

export interface ToolCall {
  id: string
  tool_name: string
  server_name: string
  status: 'calling' | 'completed' | 'error'
  arguments?: Record<string, unknown>
  result?: unknown
  error?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: Date
  toolCalls?: ToolCall[]
}

interface MessageProps {
  message: ChatMessage
  isStreaming?: boolean
  isThinking?: boolean
}

export function Message({ message, isStreaming = false, isThinking = false }: MessageProps) {
  const isCommandResult = message.role === 'system' && message.toolCalls?.length && !message.content
  const isModelSwitch = message.role === 'system' && message.id.startsWith('model-switch-')

  return (
    <div className={`message message-${message.role}${isCommandResult ? ' message-command' : ''}${isModelSwitch ? ' message-model-switch' : ''}`}>
      <div className="message-header">
        <span className="message-role">
          {message.role === 'user' ? 'You' : message.role === 'assistant' ? 'Gobby' : 'System'}
        </span>
        <span className="message-time">
          {message.timestamp.toLocaleTimeString()}
        </span>
      </div>
      {isThinking && !message.content && (
        <div className="thinking-indicator">
          <span className="thinking-spinner" />
          <span className="thinking-text">Gobby is thinking...</span>
        </div>
      )}
      {message.toolCalls && message.toolCalls.length > 0 && (
        <ToolCallDisplay toolCalls={message.toolCalls} />
      )}
      <div className="message-content">
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>
          {message.content}
        </ReactMarkdown>
        {isStreaming && <span className="cursor" />}
      </div>
    </div>
  )
}
