import { useState, useMemo } from 'react'
import type { SessionMessage } from '../hooks/useSessionDetail'
import { MemoizedMarkdown } from './MemoizedMarkdown'
import { formatRelativeTime } from '../utils/formatTime'

interface SessionTranscriptProps {
  messages: SessionMessage[]
  totalMessages: number
  hasMore: boolean
  isLoading: boolean
  onLoadMore: () => void
}

/** A parsed message ready for display. */
interface TranscriptEntry {
  id: string
  role: 'user' | 'assistant' | 'tool'
  content: string
  timestamp: string
  /** Tool call info when role is 'tool' or assistant used a tool. */
  toolCall?: {
    name: string
    input?: string
    result?: string
  }
}

/** Map an API SessionMessage to a TranscriptEntry, or null to skip. */
function mapMessage(msg: SessionMessage): TranscriptEntry | null {
  const content = msg.content?.trim() ?? ''

  // Tool-use messages (role from DB can be "tool" or messages with tool_name)
  if (msg.tool_name) {
    return {
      id: String(msg.id),
      role: 'tool',
      content: content,
      timestamp: msg.timestamp,
      toolCall: {
        name: msg.tool_name,
        input: msg.tool_input || undefined,
        result: msg.tool_result || undefined,
      },
    }
  }

  // Skip tool_result JSON blobs sent as "user" role (Claude API convention).
  // These are internal protocol messages — actual results are shown in tool call dropdowns.
  if (msg.role === 'user' && content.startsWith('[{') && content.includes('tool_result')) {
    return null
  }

  // Detect tool_use blocks in assistant messages
  if (msg.role === 'assistant' && content.startsWith('[{') && content.includes('tool_use')) {
    try {
      const calls = JSON.parse(content) as Array<{ type?: string; name?: string; input?: unknown }>
      const tools = calls.filter((c) => c.type === 'tool_use')
      if (tools.length > 0) {
        // Show each tool as its own entry in the transcript
        return {
          id: String(msg.id),
          role: 'tool',
          content: '',
          timestamp: msg.timestamp,
          toolCall: {
            name: tools.map((t) => t.name).join(', '),
            input: tools.length === 1 ? safeStringify(tools[0].input) : undefined,
          },
        }
      }
    } catch (e) {
      console.warn('Failed to parse tool_use JSON in assistant message:', e)
    }
  }

  // Skip empty assistant messages (tool-use-only turns)
  if (!content && msg.role === 'assistant') return null
  if (!content) return null

  let role: TranscriptEntry['role']
  if (msg.role === 'user') role = 'user'
  else if (msg.role === 'assistant') role = 'assistant'
  else if (msg.role === 'system') role = 'tool'
  else {
    console.warn(`Unexpected message role: ${msg.role}`)
    role = 'tool'
  }

  return {
    id: String(msg.id),
    role,
    content,
    timestamp: msg.timestamp,
  }
}

function safeStringify(value: unknown): string | undefined {
  if (value === undefined || value === null) return undefined
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

function ToolCallBlock({ toolCall }: { toolCall: NonNullable<TranscriptEntry['toolCall']> }) {
  const [expanded, setExpanded] = useState(false)
  const hasDetails = toolCall.input || toolCall.result

  return (
    <div className="transcript-tool-call">
      <div
        className="transcript-tool-call-header"
        onClick={() => hasDetails && setExpanded(!expanded)}
        style={{ cursor: hasDetails ? 'pointer' : 'default' }}
      >
        <span className="transcript-tool-call-icon">{'\u2699'}</span>
        <span className="transcript-tool-call-name">{toolCall.name}</span>
        {hasDetails && (
          <span className="transcript-tool-call-expand">{expanded ? '\u25bc' : '\u25b6'}</span>
        )}
      </div>
      {expanded && hasDetails && (
        <div className="transcript-tool-call-details">
          {toolCall.input && (
            <div className="transcript-tool-call-section">
              <div className="transcript-tool-call-section-label">Input</div>
              <pre className="transcript-tool-call-json">{toolCall.input}</pre>
            </div>
          )}
          {toolCall.result && (
            <div className="transcript-tool-call-section">
              <div className="transcript-tool-call-section-label">Result</div>
              <pre className="transcript-tool-call-json">{toolCall.result}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function TranscriptMessage({ entry }: { entry: TranscriptEntry }) {
  const roleLabel = entry.role === 'user' ? 'User' : entry.role === 'assistant' ? 'Assistant' : 'Tool'

  return (
    <div className={`transcript-message transcript-message-${entry.role}`}>
      <div className="transcript-message-header">
        <span className={`transcript-message-role transcript-message-role-${entry.role}`}>
          {roleLabel}
        </span>
        <span className="transcript-message-time">
          {formatRelativeTime(entry.timestamp)}
        </span>
      </div>
      {entry.toolCall && <ToolCallBlock toolCall={entry.toolCall} />}
      {entry.content && (
        <div className="transcript-message-content message-content">
          <MemoizedMarkdown content={entry.content} id={`transcript-${entry.id}`} />
        </div>
      )}
    </div>
  )
}

export function SessionTranscript({
  messages,
  totalMessages,
  hasMore,
  isLoading,
  onLoadMore,
}: SessionTranscriptProps) {
  const entries = useMemo(
    () => messages.map(mapMessage).filter((e): e is TranscriptEntry => e !== null),
    [messages],
  )

  return (
    <div className="session-transcript">
      <h3>Transcript ({totalMessages} messages)</h3>

      {/* Load more at the top for reverse-chronological pagination */}
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
        {entries.map((entry) => (
          <TranscriptMessage key={entry.id} entry={entry} />
        ))}
      </div>
    </div>
  )
}
