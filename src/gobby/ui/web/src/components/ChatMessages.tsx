import { useEffect, useRef } from 'react'
import { Message, ChatMessage } from './Message'

interface ChatMessagesProps {
  messages: ChatMessage[]
  isStreaming?: boolean
}

export function ChatMessages({ messages, isStreaming = false }: ChatMessagesProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    const container = containerRef.current
    if (container) {
      container.scrollTop = container.scrollHeight
    }
  }, [messages])

  return (
    <div className="chat-messages" ref={containerRef}>
      {messages.length === 0 ? (
        <div className="empty-state">
          <p>Start a conversation with Gobby</p>
        </div>
      ) : (
        messages.map((message) => (
          <Message
            key={message.id}
            message={message}
            isStreaming={isStreaming && message === messages[messages.length - 1]}
          />
        ))
      )}
    </div>
  )
}
