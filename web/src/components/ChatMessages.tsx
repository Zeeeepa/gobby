import { useEffect, useRef } from 'react'
import { Message, ChatMessage } from './Message'

interface ChatMessagesProps {
  messages: ChatMessage[]
  isStreaming?: boolean
  isThinking?: boolean
  onRespondToQuestion?: (toolCallId: string, answers: Record<string, string>) => void
}

export function ChatMessages({ messages, isStreaming = false, isThinking = false, onRespondToQuestion }: ChatMessagesProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    const container = containerRef.current
    if (container) {
      container.scrollTop = container.scrollHeight
    }
  }, [messages, isThinking])

  return (
    <div className="chat-messages" ref={containerRef}>
      {messages.length === 0 && !isThinking ? (
        <div className="empty-state">
          <p>Start a conversation with Gobby</p>
        </div>
      ) : (
        <>
          {messages.map((message, i) => (
            <Message
              key={message.id}
              message={message}
              isStreaming={isStreaming && i === messages.length - 1}
              isThinking={isThinking && i === messages.length - 1}
              onRespondToQuestion={onRespondToQuestion}
            />
          ))}
          {isThinking && (messages.length === 0 || messages[messages.length - 1].role === 'user') && (
            <div className="message message-assistant">
              <div className="message-header">
                <span className="message-role">
                  <img src="/logo.png" alt="" className="message-role-logo" />
                  Gobby
                </span>
              </div>
              <div className="thinking-indicator">
                <span className="thinking-spinner" />
                <span className="thinking-text">Gobby is thinking...</span>
              </div>
            </div>
          )}
        </>
      )}
    </div>
  )
}
