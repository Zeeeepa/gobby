import type { GobbySession } from '../hooks/useSessions'
import type { SessionMessage } from '../hooks/useSessionDetail'
import { SourceIcon } from './SourceIcon'
import { MemoizedMarkdown } from './MemoizedMarkdown'
import { SessionTranscript } from './SessionTranscript'
import { SessionLineage } from './SessionLineage'
import { formatDuration, formatTokens, formatCost } from '../utils/formatTime'

interface SessionDetailProps {
  session: GobbySession
  messages: SessionMessage[]
  totalMessages: number
  hasMore: boolean
  isLoading: boolean
  onLoadMore: () => void
  onAskGobby: (context: string) => void
  onGenerateSummary: () => void
  isGeneratingSummary: boolean
  allSessions: GobbySession[]
  onSelectSession: (sessionId: string) => void
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
  onGenerateSummary,
  isGeneratingSummary,
  allSessions,
  onSelectSession,
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
      <div className="session-detail-summary">
        <div className="session-detail-summary-header">
          <h3>Summary</h3>
          {!session.summary_markdown && !isGeneratingSummary && (
            <button
              className="session-detail-generate-btn"
              onClick={onGenerateSummary}
            >
              <SummaryIcon /> Generate Summary
            </button>
          )}
          {session.summary_markdown && !isGeneratingSummary && (
            <button
              className="session-detail-regenerate-btn"
              onClick={onGenerateSummary}
              title="Regenerate summary"
            >
              <SummaryIcon />
            </button>
          )}
        </div>
        {isGeneratingSummary && (
          <div className="session-detail-generating">
            <span className="thinking-spinner" /> Generating summary...
          </div>
        )}
        {session.summary_markdown && (
          <div className="message-content">
            <MemoizedMarkdown content={session.summary_markdown} id={`summary-${session.id}`} />
          </div>
        )}
        {!session.summary_markdown && !isGeneratingSummary && (
          <div className="session-detail-no-summary">No summary available yet.</div>
        )}
      </div>

      {/* Lineage */}
      <SessionLineage
        session={session}
        allSessions={allSessions}
        onSelectSession={onSelectSession}
      />

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
      <SessionTranscript
        messages={messages}
        totalMessages={totalMessages}
        hasMore={hasMore}
        isLoading={isLoading}
        onLoadMore={onLoadMore}
      />
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

function SummaryIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
      <polyline points="10 9 9 9 8 9" />
    </svg>
  )
}
