import { useCallback, useEffect, useImperativeHandle, useRef, forwardRef } from 'react'
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso'
import type { ChatMessage } from '../../types/chat'
import { MessageItem } from './MessageItem'
import { MessageErrorBoundary } from './MessageErrorBoundary'
import type { A2UISurfaceState, UserAction } from '../canvas'

interface MessageListProps {
  messages: ChatMessage[]
  isStreaming: boolean
  isThinking: boolean
  isLoadingMessages?: boolean
  onRespondToQuestion?: (toolCallId: string, answers: Record<string, string>) => void
  onRespondToApproval?: (toolCallId: string, decision: 'approve' | 'reject' | 'approve_always') => void
  canvasSurfaces?: Map<string, A2UISurfaceState>
  onCanvasInteraction?: (canvasId: string, action: UserAction) => void
}

export interface MessageListHandle {
  scrollToBottom: () => void
}

export const MessageList = forwardRef<MessageListHandle, MessageListProps>(function MessageList({ messages, isStreaming, isThinking, isLoadingMessages, onRespondToQuestion, onRespondToApproval, canvasSurfaces, onCanvasInteraction }, ref) {
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const userScrolledUpRef = useRef(false)

  useImperativeHandle(ref, () => ({
    scrollToBottom() {
      userScrolledUpRef.current = false
      virtuosoRef.current?.scrollToIndex({ index: 'LAST', behavior: 'smooth' })
    },
  }))

  const handleAtBottomStateChange = useCallback((atBottom: boolean) => {
    userScrolledUpRef.current = !atBottom
  }, [])

  useEffect(() => {
    if (isStreaming && !userScrolledUpRef.current) {
      virtuosoRef.current?.scrollToIndex({ index: 'LAST', behavior: 'smooth' })
    }
  }, [isStreaming, messages])

  // Scroll to bottom on new messages (non-streaming appends)
  useEffect(() => {
    if (!userScrolledUpRef.current && messages.length > 0) {
      virtuosoRef.current?.scrollToIndex({ index: 'LAST', behavior: 'smooth' })
    }
  }, [messages.length])

  const Footer = useCallback(() => (
    <>
      {isThinking && (messages.length === 0 || messages[messages.length - 1].role === 'user') && (
        <ThinkingIndicator />
      )}
    </>
  ), [isThinking, messages])

  // Stable reference for itemContent to avoid Virtuoso re-renders
  const itemContent = useCallback((index: number, message: ChatMessage) => (
    <MessageErrorBoundary key={message.id} messageId={message.id}>
      <MessageItem
        message={message}
        isStreaming={isStreaming && index === messages.length - 1}
        isThinking={isThinking && index === messages.length - 1}
        onRespondToQuestion={onRespondToQuestion}
        onRespondToApproval={onRespondToApproval}
        canvasSurfaces={canvasSurfaces}
        onCanvasInteraction={onCanvasInteraction}
      />
    </MessageErrorBoundary>
  ), [isStreaming, isThinking, messages.length, onRespondToQuestion, onRespondToApproval, canvasSurfaces, onCanvasInteraction])

  if (messages.length === 0 && !isThinking) {
    return (
      <div className="chat-scaled flex-1 min-h-0 flex items-center justify-center">
        <div className="text-center text-muted-foreground">
          {isLoadingMessages ? (
            <p className="text-sm animate-pulse">Loading messages...</p>
          ) : (
            <>
              <ChatEmptyIcon />
              <div className="text-lg mb-1">Chat</div>
              <p className="text-sm">Start a conversation with Gobby</p>
            </>
          )}
        </div>
      </div>
    )
  }

  return (
    <Virtuoso
      ref={virtuosoRef}
      className="chat-scaled flex-1 min-h-0 overflow-x-hidden [&::-webkit-scrollbar]:w-2 [&::-webkit-scrollbar-track]:bg-transparent [&::-webkit-scrollbar-thumb]:rounded-full [&::-webkit-scrollbar-thumb]:bg-border [scrollbar-width:thin] [scrollbar-color:var(--border)_transparent]"
      data={messages}
      itemContent={itemContent}
      followOutput={() => {
        if (userScrolledUpRef.current) return false
        return 'smooth'
      }}
      atBottomThreshold={400}
      atBottomStateChange={handleAtBottomStateChange}
      overscan={400}
      increaseViewportBy={200}
      components={{ Footer }}
    />
  )
})

function ChatEmptyIcon() {
  return (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" className="mb-3 opacity-40">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )
}

function ThinkingIndicator() {
  return (
    <div className="px-4 py-3">
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-2 mb-1.5">
          <img src="/logo.png" alt="App logo" className="w-5 h-5 rounded" onError={(e) => { (e.target as HTMLImageElement).style.display = 'none' }} />
          <span className="text-xs font-medium text-muted-foreground">Gobby</span>
        </div>
        <div className="flex items-center gap-2 py-2">
          <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-muted-foreground">Thinking...</span>
        </div>
      </div>
    </div>
  )
}
