import type { GobbySession } from '../hooks/useSessions'
import { SourceIcon } from './SourceIcon'
import { formatRelativeTime } from '../utils/formatTime'
import { useState, useEffect, useRef, useMemo } from 'react'

interface AgentInfo {
  run_id: string
  provider: string
  pid?: number
  mode?: string
  started_at?: string
  tmux_session_name?: string
}

interface ConversationPickerProps {
  sessions: GobbySession[]
  recentCliSessions?: GobbySession[]
  activeSessionId: string | null
  onNewChat: () => void
  onSelectSession: (session: GobbySession) => void
  onDeleteSession?: (session: GobbySession) => void
  onContinueSession?: (session: GobbySession) => void
  onRenameSession?: (id: string, title: string) => void
  agents?: AgentInfo[]
  onNavigateToAgent?: (agent: AgentInfo) => void
}

const PROVIDER_COLORS: Record<string, string> = {
  claude: '#c084fc',
  gemini: '#4ade80',
  codex: '#3b82f6',
  unknown: '#737373',
}

export function ConversationPicker({
  sessions,
  recentCliSessions = [],
  activeSessionId,
  onNewChat,
  onSelectSession,
  onDeleteSession,
  onContinueSession,
  onRenameSession,
  agents = [],
  onNavigateToAgent,
}: ConversationPickerProps) {
  const [search, setSearch] = useState('')
  const [isOpen, setIsOpen] = useState(true)
  const pickerRef = useRef<HTMLDivElement>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')
  const saveOnBlurRef = useRef(true)

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
              type="button"
              className="terminals-action-btn"
              onClick={onNewChat}
              title="New Chat"
            >
              <PlusIcon />
            </button>
          )}
          <button
            type="button"
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

          <div className="session-group">
          <div className="sessions-list">
            {filtered.length === 0 && (
              <div className="terminals-empty-sidebar">No conversations</div>
            )}
            {filtered.map((session) => {
              const title = session.title || `Chat ${session.ref}`
              const isActive = session.external_id === activeSessionId
              return (
                <div
                  key={session.id}
                  className={`session-item ${isActive ? 'attached' : ''}`}
                  onClick={() => { if (editingId !== session.id) onSelectSession(session) }}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => { if (editingId !== session.id && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onSelectSession(session) } }}
                >
                  <div className="session-item-main">
                    <span className="session-source-dot web-chat" />
                    {editingId === session.id ? (
                      <input
                        className="session-name-input"
                        value={editValue}
                        onChange={e => setEditValue(e.target.value)}
                        onBlur={() => {
                          if (saveOnBlurRef.current && onRenameSession) {
                            onRenameSession(session.id, editValue)
                          }
                          saveOnBlurRef.current = true
                          setEditingId(null)
                        }}
                        onKeyDown={e => {
                          if (e.key === 'Enter') {
                            saveOnBlurRef.current = false
                            if (onRenameSession) onRenameSession(session.id, editValue)
                            setEditingId(null)
                          } else if (e.key === 'Escape') {
                            saveOnBlurRef.current = false
                            setEditingId(null)
                          }
                        }}
                        onClick={e => e.stopPropagation()}
                        aria-label="Rename chat"
                        autoFocus
                      />
                    ) : (
                      <span
                        className="session-name"
                        title={title}
                        onDoubleClick={e => {
                          if (!onRenameSession) return
                          e.stopPropagation()
                          setEditingId(session.id)
                          setEditValue(title)
                        }}
                      >
                        {title}
                      </span>
                    )}
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

          {recentCliSessions.length > 0 && onContinueSession && (
            <div className="session-group">
              <div className="session-group-label">Recent CLI Sessions</div>
              {recentCliSessions.map((session) => {
                const title = session.title || `${session.source} #${session.ref}`
                return (
                  <div
                    key={session.id}
                    className="session-item"
                    onClick={() => onContinueSession(session)}
                    role="button"
                    tabIndex={0}
                    onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onContinueSession(session) } }}
                  >
                    <div className="session-item-main">
                      <SourceIcon source={session.source} size={14} />
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
          )}

          {agents.length > 0 && (
            <div className="session-group">
              <div className="session-group-label">Active Agents ({agents.length})</div>
              {agents.map((agent) => (
                <div
                  key={agent.run_id}
                  className="session-item"
                  {...(onNavigateToAgent ? {
                    onClick: () => onNavigateToAgent(agent),
                    role: 'button' as const,
                    tabIndex: 0,
                    onKeyDown: (e: React.KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onNavigateToAgent(agent) } },
                  } : {})}
                >
                  <div className="session-item-main">
                    <span
                      className="session-source-dot"
                      style={{ background: PROVIDER_COLORS[agent.provider] ?? PROVIDER_COLORS.unknown }}
                    />
                    <span className="session-name">{agent.provider}</span>
                    {agent.mode && (
                      <span className="session-badge agent-badge">{agent.mode}</span>
                    )}
                  </div>
                  <div className="session-item-actions">
                    <span className="session-pid">
                      <AgentUptime startedAt={agent.started_at} />
                    </span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}

function AgentUptime({ startedAt }: { startedAt?: string }) {
  const startTime = useMemo(() => {
    if (startedAt) {
      const t = new Date(startedAt).getTime()
      if (!Number.isNaN(t)) return t
    }
    return null
  }, [startedAt])
  const [uptime, setUptime] = useState(startTime ? '0s' : '—')

  useEffect(() => {
    if (startTime === null) return
    const update = () => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000)
      if (elapsed < 60) setUptime(`${elapsed}s`)
      else if (elapsed < 3600) setUptime(`${Math.floor(elapsed / 60)}m`)
      else setUptime(`${Math.floor(elapsed / 3600)}h${Math.floor((elapsed % 3600) / 60)}m`)
    }
    update()
    const interval = setInterval(update, 1000)
    return () => clearInterval(interval)
  }, [startTime])

  return <>{uptime}</>
}

function TrashIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
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
