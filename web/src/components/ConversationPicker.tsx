import type { GobbySession } from '../hooks/useSessions'
import { formatRelativeTime } from '../utils/formatTime'
import { useState, useEffect, useRef } from 'react'

interface ConversationPickerProps {
  sessions: GobbySession[]
  activeSessionId: string | null
  onNewChat: () => void
  onSelectSession: (session: GobbySession) => void
}

export function ConversationPicker({
  sessions,
  activeSessionId,
  onNewChat,
  onSelectSession,
}: ConversationPickerProps) {
  const [search, setSearch] = useState('')
  const [isOpen, setIsOpen] = useState(true)
  const pickerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!isOpen) return
    const handleClickOutside = (e: MouseEvent) => {
      if (pickerRef.current && !pickerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [isOpen])

  const filtered = search
    ? sessions.filter(
        (s) =>
          (s.title && s.title.toLowerCase().includes(search.toLowerCase())) ||
          s.ref.toLowerCase().includes(search.toLowerCase())
      )
    : sessions

  return (
    <div ref={pickerRef} className={`conversation-picker ${isOpen ? '' : 'collapsed'}`}>
      <div className="conversation-picker-header">
        {isOpen && <span className="conversation-picker-title">Chats</span>}
        <div className="conversation-picker-actions">
          {isOpen && (
            <button
              className="terminals-action-btn"
              onClick={onNewChat}
              title="New Chat"
            >
              <PlusIcon />
            </button>
          )}
          <button
            className="terminals-sidebar-toggle"
            onClick={() => setIsOpen(!isOpen)}
            title={isOpen ? 'Collapse' : 'Expand'}
          >
            {isOpen ? '\u25C0' : '\u25B6'}
          </button>
        </div>
      </div>

      {isOpen && (
        <>
          <div className="conversation-picker-search">
            <input
              className="sessions-filter-input"
              type="text"
              placeholder="Search chats..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
          </div>

          <div className="sessions-list">
            {filtered.length === 0 && (
              <div className="terminals-empty-sidebar">No conversations</div>
            )}
            {filtered.map((session) => {
              const title = session.title || `Chat #${session.ref}`
              const isActive = session.external_id === activeSessionId
              return (
                <div
                  key={session.id}
                  className={`session-item ${isActive ? 'attached' : ''}`}
                  onClick={() => onSelectSession(session)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectSession(session) } }}
                >
                  <div className="session-item-main">
                    <span className="session-source-dot web-chat" />
                    <span className="session-name" title={title}>
                      {title}
                    </span>
                  </div>
                  <div className="session-item-actions">
                    <span className="session-pid">
                      {formatRelativeTime(session.updated_at)}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}
