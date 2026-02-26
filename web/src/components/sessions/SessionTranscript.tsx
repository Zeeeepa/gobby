import { useMemo } from 'react'
import type { SessionMessage } from '../../hooks/useSessionDetail'
import { MessageItem } from '../chat/MessageItem'
import { sessionMessagesToChatMessages } from './transcriptAdapter'

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
    () => sessionMessagesToChatMessages(messages),
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
