import type { GobbySession } from '../hooks/useSessions'
import type { SessionMessage } from '../hooks/useSessionDetail'
import { SourceIcon } from './SourceIcon'
import { MemoizedMarkdown } from './MemoizedMarkdown'
import { formatRelativeTime, formatDuration } from '../utils/formatTime'

interface SessionDetailProps {
  session: GobbySession
  messages: SessionMessage[]
  totalMessages: number
  hasMore: boolean
  isLoading: boolean
  onLoadMore: () => void
  onAskGobby: (context: string) => void
}

interface TranscriptDisplay {
  role: string
  content: string
  isToolResult?: boolean
}

/** Clean up transcript messages for display: skip empties, label tool results. */
function formatTranscriptContent(msg: SessionMessage): TranscriptDisplay | null {
  const content = msg.content?.trim() ?? ''

  // Skip empty assistant messages (tool-use-only turns)
  if (!content && msg.role === 'assistant') return null

  // Detect tool_result JSON blobs (sent as "user" role in Claude API)
  if (msg.role === 'user' && content.startsWith('[{') && content.includes('tool_result')) {
    // Count tool results and extract tool_use_ids
    try {
      const results = JSON.parse(content) as Array<{ type?: string; tool_use_id?: string }>
      const count = results.filter((r) => r.type === 'tool_result').length
      return {
        role: 'tool',
        content: `(${count} tool result${count !== 1 ? 's' : ''})`,
        isToolResult: true,
      }
    } catch {
      return { role: 'tool', content: '(tool results)', isToolResult: true }
    }
  }

  // Detect tool_use blocks in assistant messages
  if (msg.role === 'assistant' && content.startsWith('[{') && content.includes('tool_use')) {
    try {
      const calls = JSON.parse(content) as Array<{ type?: string; name?: string }>
      const tools = calls.filter((c) => c.type === 'tool_use').map((c) => c.name).filter(Boolean)
      if (tools.length > 0) {
        return {
          role: 'assistant',
          content: `Used tools: ${tools.join(', ')}`,
          isToolResult: true,
        }
      }
    } catch {
      // Fall through to normal rendering
    }
  }

  if (!content) return null

  // Truncate very long messages
  const truncated = content.length > 2000 ? content.slice(0, 2000) + '\n\n...' : content
  return { role: msg.role, content: truncated }
}

function formatTokens(n: number): string {
  if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}K`
  return String(n)
}

function formatCost(usd: number): string {
  if (usd === 0) return '$0'
  if (usd < 0.01) return '<$0.01'
  return `$${usd.toFixed(2)}`
}

function statusLabel(status: string): string {
  switch (status) {
    case 'active': return 'Active'
    case 'archived': return 'Archived'
    case 'handoff_ready': return 'Handoff'
    case 'expired': return 'Expired'
    default: return status
  }
}

export function SessionDetail({
  session,
  messages,
  totalMessages,
  hasMore,
  isLoading,
  onLoadMore,
  onAskGobby,
}: SessionDetailProps) {
  const title = session.title || `Session #${session.ref}`

  return (
    <div className="session-detail">
      {/* Header */}
      <div className="session-detail-header">
        <div className="session-detail-header-left">
          <SourceIcon source={session.source} size={18} />
          <h2 className="session-detail-title">{title}</h2>
        </div>
        <div className="session-detail-header-right">
          <span className={`session-detail-status session-detail-status-${session.status}`}>
            {statusLabel(session.status)}
          </span>
          {session.model && (
            <span className="session-detail-model">{session.model}</span>
          )}
          {session.git_branch && (
            <span className="session-detail-branch">
              <BranchIcon /> {session.git_branch}
            </span>
          )}
        </div>
      </div>

      {/* Stats bar */}
      <div className="session-detail-stats">
        <div className="session-detail-stat">
          <span className="session-detail-stat-label">Messages</span>
          <span className="session-detail-stat-value">{session.message_count}</span>
        </div>
        <div className="session-detail-stat">
          <span className="session-detail-stat-label">Input</span>
          <span className="session-detail-stat-value">{formatTokens(session.usage_input_tokens)}</span>
        </div>
        <div className="session-detail-stat">
          <span className="session-detail-stat-label">Output</span>
          <span className="session-detail-stat-value">{formatTokens(session.usage_output_tokens)}</span>
        </div>
        <div className="session-detail-stat">
          <span className="session-detail-stat-label">Cost</span>
          <span className="session-detail-stat-value">{formatCost(session.usage_total_cost_usd)}</span>
        </div>
        <div className="session-detail-stat">
          <span className="session-detail-stat-label">Duration</span>
          <span className="session-detail-stat-value">{formatDuration(session.created_at, session.updated_at)}</span>
        </div>
        {session.had_edits && (
          <div className="session-detail-stat">
            <span className="session-detail-stat-value session-detail-edited">Edited files</span>
          </div>
        )}
      </div>

      {/* Summary */}
      {session.summary_markdown && (
        <div className="session-detail-summary">
          <h3>Summary</h3>
          <div className="message-content">
            <MemoizedMarkdown content={session.summary_markdown} id={`summary-${session.id}`} />
          </div>
        </div>
      )}

      {/* Ask Gobby button */}
      <div className="session-detail-actions">
        <button
          className="session-detail-ask-btn"
          onClick={() => onAskGobby(`Tell me about session ${session.ref} (${title}). Here's the summary:\n\n${session.summary_markdown || 'No summary available.'}`)}
        >
          <ChatIcon /> Ask Gobby about this session
        </button>
      </div>

      {/* Transcript */}
      <div className="session-detail-transcript">
        <h3>Transcript ({totalMessages} messages)</h3>
        {isLoading && messages.length === 0 && (
          <div className="session-detail-loading">Loading messages...</div>
        )}
        <div className="session-detail-messages">
          {messages.map((msg) => {
            const display = formatTranscriptContent(msg)
            if (!display) return null
            return (
              <div key={msg.id} className={`session-detail-message session-detail-message-${display.role}`}>
                <div className="session-detail-message-header">
                  <span className="session-detail-message-role">{display.role}</span>
                  <span className="session-detail-message-time">
                    {formatRelativeTime(msg.timestamp)}
                  </span>
                </div>
                <div className="session-detail-message-content message-content">
                  {display.isToolResult ? (
                    <span className="text-muted">{display.content}</span>
                  ) : (
                    <MemoizedMarkdown content={display.content} id={`transcript-${msg.id}`} />
                  )}
                </div>
              </div>
            )
          })}
        </div>
        {hasMore && (
          <button
            className="session-detail-load-more"
            onClick={onLoadMore}
            disabled={isLoading}
          >
            {isLoading ? 'Loading...' : `Load more (${totalMessages - messages.length} remaining)`}
          </button>
        )}
      </div>
    </div>
  )
}

function BranchIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="6" y1="3" x2="6" y2="15" />
      <circle cx="18" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M18 9a9 9 0 0 1-9 9" />
    </svg>
  )
}

function ChatIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )
}
