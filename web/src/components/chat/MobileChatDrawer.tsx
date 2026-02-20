import { useState } from 'react'
import type { GobbySession } from '../../hooks/useSessions'
import { formatRelativeTime } from '../../utils/formatTime'

interface MobileChatDrawerProps {
  sessions: GobbySession[]
  activeSessionId: string | null
  onNewChat: () => void
  onSelectSession: (session: GobbySession) => void
  onDeleteSession?: (session: GobbySession) => void
}

export function MobileChatDrawer({
  sessions,
  activeSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
}: MobileChatDrawerProps) {
  const [isOpen, setIsOpen] = useState(false)

  const activeSession = sessions.find(s => s.external_id === activeSessionId)
  const activeTitle = activeSession?.title || 'Chats'

  return (
    <div className={`mobile-chat-drawer ${isOpen ? '' : 'collapsed'}`}>
      <div
        className="mobile-chat-drawer-header"
        onClick={() => setIsOpen(!isOpen)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setIsOpen(!isOpen) } }}
      >
        <span className="mobile-chat-drawer-title">
          {isOpen ? 'Chats' : activeTitle}
        </span>
        <span>{isOpen ? '\u25B2' : '\u25BC'}</span>
      </div>

      {isOpen && (
        <div className="mobile-chat-drawer-content">
          <button
            type="button"
            className="mobile-chat-drawer-new"
            onClick={() => { onNewChat(); setIsOpen(false) }}
          >
            + New Chat
          </button>

          <div className="mobile-chat-drawer-list">
            {sessions.length === 0 && (
              <div className="mobile-chat-drawer-empty">
                No conversations
              </div>
            )}
            {sessions.map((session) => {
              const title = session.title || `Chat ${session.ref}`
              const isActive = session.external_id === activeSessionId
              return (
                <div
                  key={session.id}
                  className={`session-item ${isActive ? 'attached' : ''}`}
                  onClick={() => { onSelectSession(session); setIsOpen(false) }}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelectSession(session); setIsOpen(false) } }}
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
                    {onDeleteSession && (
                      <button
                        type="button"
                        className="session-delete-btn"
                        title="Delete chat"
                        onClick={(e) => { e.stopPropagation(); onDeleteSession(session) }}
                      >
                        <TrashIcon />
                      </button>
                    )}
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function TrashIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  )
}
