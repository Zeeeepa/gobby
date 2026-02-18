import { useEffect, useRef } from 'react'
import type { ChatMessage } from '../../types/chat'
import { ScrollArea } from './ui/ScrollArea'
import { MessageItem } from './MessageItem'

interface MessageListProps {
  messages: ChatMessage[]
  isStreaming: boolean
  isThinking: boolean
  onRespondToQuestion?: (toolCallId: string, answers: Record<string, string>) => void
}

export function MessageList({ messages, isStreaming, isThinking, onRespondToQuestion }: MessageListProps) {
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const el = scrollRef.current
    if (el) {
      const distanceFromBottom = el.scrollHeight - el.scrollTop - el.clientHeight
      if (distanceFromBottom < 100) {
        el.scrollTop = el.scrollHeight
      }
    }
  }, [messages, isThinking])

  return (
    <ScrollArea ref={scrollRef} className="flex-1 min-h-0">
      {messages.length === 0 && !isThinking ? (
        <div className="flex items-center justify-center h-full">
          <div className="text-center text-muted-foreground">
            <div className="text-lg mb-1">Chat</div>
            <p className="text-sm">Start a conversation with Gobby</p>
          </div>
        </div>
      ) : (
        <>
          {messages.map((message, i) => (
            <MessageItem
              key={message.id}
              message={message}
              isStreaming={isStreaming && i === messages.length - 1}
              isThinking={isThinking && i === messages.length - 1}
              onRespondToQuestion={onRespondToQuestion}
            />
          ))}
          {isThinking && (messages.length === 0 || messages[messages.length - 1].role === 'user') && (
            <div className="px-4 py-3">
              <div className="max-w-3xl mx-auto">
                <div className="flex items-center gap-2 mb-1.5">
                  <img src="/logo.png" alt="" className="w-5 h-5 rounded" />
                  <span className="text-xs font-medium text-muted-foreground">Gobby</span>
                </div>
                <div className="flex items-center gap-2 py-2">
                  <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
                  <span className="text-sm text-muted-foreground">Thinking...</span>
                </div>
              </div>
            </div>
          )}
        </>
      )}
    </ScrollArea>
  )
}
