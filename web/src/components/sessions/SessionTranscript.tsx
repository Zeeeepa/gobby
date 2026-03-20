import { useMemo } from 'react'
import type { SessionMessage } from '../../hooks/useSessionDetail'
import type { ChatMessage } from '../../types/chat'
import { MessageItem } from '../chat/MessageItem'

/** Map SessionMessages (RenderedMessage shape) to ChatMessages for rendering. */
function mapToChatMessages(messages: SessionMessage[]): ChatMessage[] {
  return messages.map((m) => {
    const chatMsg: ChatMessage = {
      id: m.id,
      role: (m.role as 'user' | 'assistant' | 'system') || 'assistant',
      content: m.content || '',
      timestamp: new Date(m.timestamp),
      contentBlocks: m.content_blocks,
    }
    // Extract toolCalls and thinkingContent for legacy component compat
    if (m.content_blocks) {
      for (const block of m.content_blocks) {
        if (block.type === 'tool_chain' && block.tool_calls) {
          chatMsg.toolCalls = [...(chatMsg.toolCalls || []), ...block.tool_calls]
        } else if (block.type === 'thinking') {
          chatMsg.thinkingContent = (chatMsg.thinkingContent || '') + block.content
        }
      }
    }
    return chatMsg
  })
}

interface SessionTranscriptProps {
  messages: SessionMessage[]
  totalMessages: number
  isLoading: boolean
}

export function SessionTranscript({
  messages,
  totalMessages,
  isLoading,
}: SessionTranscriptProps) {
  const chatMessages = useMemo(
    () => mapToChatMessages(messages),
    [messages],
  )

  return (
    <div className="session-transcript">
      <h3>Transcript ({totalMessages} messages)</h3>

      {isLoading && messages.length === 0 && (
        <div className="session-transcript-loading">Loading messages...</div>
      )}

      <div className="session-transcript-messages">
        {chatMessages.map((msg) => (
          <MessageItem key={msg.id} message={msg} />
        ))}
      </div>
    </div>
  )
}
