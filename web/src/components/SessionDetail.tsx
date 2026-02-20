import { useState, useEffect, useRef } from 'react'
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
  onAskGobby?: (context: string) => void
  onContinueInChat?: (session: GobbySession) => void
  onRenameSession?: (id: string, title: string) => void
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
  onContinueInChat,
  onRenameSession,
  onGenerateSummary,
  isGeneratingSummary,
  allSessions,
  onSelectSession,
}: SessionDetailProps) {
  const title = session.title || `Session #${session.ref}`
  const [isEditingTitle, setIsEditingTitle] = useState(false)
  const [editValue, setEditValue] = useState('')
  const saveOnBlurRef = useRef(true)

  useEffect(() => {
    setIsEditingTitle(false)
  }, [session.id])

  return (
    <div className="session-detail">
      {/* Header */}
      <div className="session-detail-header">
        <div className="session-detail-header-left">
          <SourceIcon source={session.source} size={18} />
          {isEditingTitle ? (
            <input
              className="session-detail-title-input"
              value={editValue}
              onChange={e => setEditValue(e.target.value)}
              onBlur={() => {
                if (saveOnBlurRef.current && onRenameSession) {
                  onRenameSession(session.id, editValue)
                }
                saveOnBlurRef.current = true
                setIsEditingTitle(false)
              }}
              onKeyDown={e => {
                if (e.key === 'Enter') {
                  saveOnBlurRef.current = false
                  if (onRenameSession) onRenameSession(session.id, editValue)
                  setIsEditingTitle(false)
                } else if (e.key === 'Escape') {
                  saveOnBlurRef.current = false
                  setIsEditingTitle(false)
                }
              }}
              aria-label="Rename session"
              autoFocus
            />
          ) : (
            <h2
              className="session-detail-title"
              onDoubleClick={() => {
                if (!onRenameSession) return
                setIsEditingTitle(true)
                setEditValue(title)
              }}
            >
              {title}
            </h2>
          )}
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

      {/* Ask Gobby dropdown */}
      {(onAskGobby || onContinueInChat) && (
        <SessionActions
          session={session}
          title={title}
          onAskGobby={onAskGobby}
          onContinueInChat={onContinueInChat}
        />
      )}

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

function SessionActions({
  session,
  title,
  onAskGobby,
  onContinueInChat,
}: {
  session: GobbySession
  title: string
  onAskGobby?: (context: string) => void
  onContinueInChat?: (session: GobbySession) => void
}) {
  const [dropdownOpen, setDropdownOpen] = useState(false)
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!dropdownOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setDropdownOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [dropdownOpen])

  const hasMessages = (session.message_count ?? 0) > 0

  return (
    <div className="session-detail-actions" ref={dropdownRef}>
      <button
        className="session-detail-ask-btn"
        onClick={() => setDropdownOpen(!dropdownOpen)}
      >
        <ChatIcon /> Ask Gobby
        <ChevronDownIcon />
      </button>
      {dropdownOpen && (
        <div className="session-detail-dropdown">
          {onContinueInChat && (
            <button
              className="session-detail-dropdown-item"
              disabled={!hasMessages}
              title={!hasMessages ? 'No messages recorded' : 'Continue this session in chat with full history'}
              onClick={() => {
                setDropdownOpen(false)
                onContinueInChat(session)
              }}
            >
              <ResumeIcon /> Resume Session
            </button>
          )}
          {onAskGobby && (
            <button
              className="session-detail-dropdown-item"
              onClick={() => {
                setDropdownOpen(false)
                onAskGobby(`Tell me about session ${session.ref || 'unknown'} (${title}). Here's the summary:\n\n${session.summary_markdown || 'No summary available.'}`)
              }}
            >
              <ChatIcon /> New Chat with Summary
            </button>
          )}
        </div>
      )}
    </div>
  )
}

function ChevronDownIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

function ResumeIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polygon points="5 3 19 12 5 21 5 3" />
    </svg>
  )
}

