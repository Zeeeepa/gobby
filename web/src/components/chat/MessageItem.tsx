import type { ChatMessage } from '../../types/chat'
import { cn } from '../../lib/utils'
import { Markdown } from './Markdown'
import { ThinkingBlock } from './ThinkingBlock'
import { ToolCallCards } from './ToolCallCard'

interface MessageItemProps {
  message: ChatMessage
  isStreaming?: boolean
  isThinking?: boolean
  onRespondToQuestion?: (toolCallId: string, answers: Record<string, string>) => void
}

export function MessageItem({ message, isStreaming = false, isThinking = false, onRespondToQuestion }: MessageItemProps) {
  const isCommandResult = message.role === 'system' && message.toolCalls?.length && !message.content
  const isModelSwitch = message.role === 'system' && message.id.startsWith('model-switch-')

  if (isModelSwitch) {
    return (
      <div className="flex justify-center py-2">
        <span className="text-xs text-muted-foreground bg-muted rounded-full px-3 py-1">
          {message.content}
        </span>
      </div>
    )
  }

  return (
    <div className={cn(
      'px-4 py-3',
      message.role === 'user' && 'bg-[#1e3a5f]/30',
      message.role === 'system' && !isCommandResult && 'bg-muted/30',
    )}>
      <div className="max-w-3xl mx-auto">
        <div className="flex items-center gap-2 mb-1.5">
          {message.role === 'assistant' && (
            <img src="/logo.png" alt="App logo" className="w-5 h-5 rounded" onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = 'none' }} />
          )}
          <span className="text-xs font-medium text-muted-foreground">
            {message.role === 'user' ? 'You' : message.role === 'assistant' ? 'Gobby' : 'System'}
          </span>
          <span className="text-xs text-muted-foreground/60">
            {(() => {
              const date = message.timestamp instanceof Date ? message.timestamp : new Date(message.timestamp)
              return !isNaN(date.getTime()) ? date.toLocaleTimeString() : ''
            })()}
          </span>
        </div>

        {isThinking && !message.content && !message.thinkingContent && (
          <div className="flex items-center gap-2 py-2">
            <div className="w-4 h-4 border-2 border-accent border-t-transparent rounded-full animate-spin" />
            <span className="text-sm text-muted-foreground">Thinking...</span>
          </div>
        )}

        {message.thinkingContent && (
          <ThinkingBlock content={message.thinkingContent} messageId={message.id} />
        )}

        {message.toolCalls && message.toolCalls.length > 0 && (
          <ToolCallCards toolCalls={message.toolCalls} onRespond={onRespondToQuestion} />
        )}

        {message.content && (
          <div className="message-content text-sm leading-relaxed text-foreground">
            <Markdown content={message.content} id={message.id} />
            {isStreaming && <span className="cursor inline-block w-2 h-4 bg-foreground animate-pulse ml-1.5" />}
          </div>
        )}
      </div>
    </div>
  )
}
