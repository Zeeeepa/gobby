import { useMemo } from 'react'
import type { SessionMessage } from '../hooks/useSessionDetail'
import { MessageItem } from './chat/MessageItem'
import { sessionMessagesToChatMessages } from './sessions/transcriptAdapter'

interface SessionTranscriptProps {
  messages: SessionMessage[]
  totalMessages: number
  hasMore: boolean
  isLoading: boolean
  onLoadMore: () => void
}

export function SessionTranscript({
  messages,
  totalMessages,
  hasMore,
  isLoading,
  onLoadMore,
}: SessionTranscriptProps) {
  const chatMessages = useMemo(
    () => sessionMessagesToChatMessages(messages),
    [messages],
  )

  return (
    <div className="session-transcript">
      <h3>Transcript ({totalMessages} messages)</h3>

      {hasMore && (
        <button
          className="session-transcript-load-more"
          onClick={onLoadMore}
          disabled={isLoading}
        >
          {isLoading ? 'Loading...' : `Load more (${totalMessages - messages.length} remaining)`}
        </button>
      )}

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
