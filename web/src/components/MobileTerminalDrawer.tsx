import { useState } from 'react'
import type { TmuxSession } from '../hooks/useTmuxSessions'

interface MobileTerminalDrawerProps {
  sessions: TmuxSession[]
  attachedSession: string | null
  streamingId: string | null
  terminalNames: Record<string, string>
  onAttach: (name: string, socket: string) => void
  onCreate: () => void
  onRefresh: () => void
}

export function MobileTerminalDrawer({
  sessions,
  attachedSession,
  streamingId,
  terminalNames,
  onAttach,
  onCreate,
  onRefresh,
}: MobileTerminalDrawerProps) {
  const [isOpen, setIsOpen] = useState(false)

  const attachedEntry = attachedSession
    ? sessions.find(s => s.name === attachedSession && streamingId !== null)
    : null
  const activeTitle = attachedEntry
    ? (terminalNames[`${attachedEntry.socket}:${attachedEntry.name}`]
      || attachedEntry.session_title || attachedEntry.name)
    : 'Terminals'

  const defaultSessions = sessions.filter(s => s.socket === 'default')
  const gobbySessions = sessions.filter(s => s.socket === 'gobby')

  return (
    <div className={`mobile-chat-drawer ${isOpen ? '' : 'collapsed'}`}>
      <div
        className="mobile-chat-drawer-header"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span className="mobile-chat-drawer-title">
          <TerminalIcon />
          {isOpen ? 'Terminals' : activeTitle}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          {isOpen && (
            <>
              <button
                type="button"
                className="mobile-drawer-action"
                onClick={(e) => { e.stopPropagation(); onRefresh() }}
                title="Refresh"
              >
                <RefreshIcon />
              </button>
              <button
                type="button"
                className="mobile-drawer-action"
                onClick={(e) => { e.stopPropagation(); onCreate(); setIsOpen(false) }}
                title="New terminal"
              >
                <PlusIcon />
              </button>
            </>
          )}
          <span>{isOpen ? '\u25B2' : '\u25BC'}</span>
        </div>
      </div>

      {isOpen && (
        <div className="mobile-chat-drawer-content">
          {sessions.length === 0 && (
            <div className="mobile-chat-drawer-empty">
              No terminals found
            </div>
          )}

          {defaultSessions.length > 0 && (
            <DrawerGroup
              sessions={defaultSessions}
              attachedSession={attachedSession}
              streamingId={streamingId}
              terminalNames={terminalNames}
              onAttach={(name, socket) => { onAttach(name, socket); setIsOpen(false) }}
            />
          )}

          {gobbySessions.length > 0 && (
            <DrawerGroup
              label="Agent Terminals"
              sessions={gobbySessions}
              attachedSession={attachedSession}
              streamingId={streamingId}
              terminalNames={terminalNames}
              onAttach={(name, socket) => { onAttach(name, socket); setIsOpen(false) }}
            />
          )}
        </div>
      )}
    </div>
  )
}

function DrawerGroup({
  label,
  sessions,
  attachedSession,
  streamingId,
  terminalNames,
  onAttach,
}: {
  label?: string
  sessions: TmuxSession[]
  attachedSession: string | null
  streamingId: string | null
  terminalNames: Record<string, string>
  onAttach: (name: string, socket: string) => void
}) {
  return (
    <div className="mobile-chat-drawer-list">
      {label && <div className="session-group-label" style={{ padding: '0.375rem 1rem' }}>{label}</div>}
      {sessions.map((session) => {
        const isAttached = attachedSession === session.name && streamingId !== null
        const nameKey = `${session.socket}:${session.name}`
        const displayName = terminalNames[nameKey] || session.session_title || session.name

        return (
          <div
            key={`${session.socket}-${session.name}`}
            className={`session-item ${isAttached ? 'attached' : ''}`}
            onClick={() => onAttach(session.name, session.socket)}
            role="button"
            tabIndex={0}
            onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onAttach(session.name, session.socket) } }}
          >
            <div className="session-item-main">
              <span className={`session-dot ${session.socket === 'gobby' ? 'agent' : 'user'}`} />
              <span className="session-name">{displayName}</span>
              {session.agent_managed && (
                <span className="session-badge agent-badge">agent</span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

function TerminalIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" y1="19" x2="20" y2="19" />
    </svg>
  )
}

function RefreshIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
  )
}

function PlusIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}
