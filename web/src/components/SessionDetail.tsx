import type { GobbySession } from '../hooks/useSessions'
import type { SessionMessage } from '../hooks/useSessionDetail'
import { SourceIcon } from './SourceIcon'
import { BranchIcon, ChatIcon, SummaryIcon } from './Icons'
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
          <span className="session-detail-stat-value">{session.message_count != null ? session.message_count : '\u2014'}</span>
        </div>
        <div className="session-detail-stat">
          <span className="session-detail-stat-label">Input</span>
          <span className="session-detail-stat-value">{session.usage_input_tokens > 0 ? formatTokens(session.usage_input_tokens) : '\u2014'}</span>
        </div>
        <div className="session-detail-stat">
          <span className="session-detail-stat-label">Output</span>
          <span className="session-detail-stat-value">{session.usage_output_tokens > 0 ? formatTokens(session.usage_output_tokens) : '\u2014'}</span>
        </div>
        <div className="session-detail-stat">
          <span className="session-detail-stat-label">Cost</span>
          <span className="session-detail-stat-value">{session.usage_total_cost_usd > 0 ? formatCost(session.usage_total_cost_usd) : '\u2014'}</span>
        </div>
        <div className="session-detail-stat">
          <span className="session-detail-stat-label">Duration</span>
          <span className="session-detail-stat-value">{formatDuration(session.created_at, session.updated_at)}</span>
        </div>
        {(session.commit_count ?? 0) > 0 && (
          <div className="session-detail-stat">
            <span className="session-detail-stat-label">Commits</span>
            <span className="session-detail-stat-value">{session.commit_count}</span>
          </div>
        )}
        {(session.tasks_closed ?? 0) > 0 && (
          <div className="session-detail-stat">
            <span className="session-detail-stat-label">Tasks Closed</span>
            <span className="session-detail-stat-value">{session.tasks_closed}</span>
          </div>
        )}
        {(session.memories_created ?? 0) > 0 && (
          <div className="session-detail-stat">
            <span className="session-detail-stat-label">Memories</span>
            <span className="session-detail-stat-value">{session.memories_created}</span>
          </div>
        )}
        {(session.artifacts_count ?? 0) > 0 && (
          <div className="session-detail-stat">
            <span className="session-detail-stat-label">Artifacts</span>
            <span className="session-detail-stat-value">{session.artifacts_count}</span>
          </div>
        )}
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
              aria-label="Regenerate summary"
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
          onClick={() => onAskGobby(`Tell me about session ${session.ref || 'unknown'} (${title}). Here's the summary:\n\n${session.summary_markdown || 'No summary available.'}`)}
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

