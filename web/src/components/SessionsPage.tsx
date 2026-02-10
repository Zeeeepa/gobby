import { useState, useMemo } from 'react'
import type { GobbySession, SessionFilters, ProjectInfo } from '../hooks/useSessions'
import { KNOWN_SOURCES } from '../hooks/useSessions'
import { useSessionDetail } from '../hooks/useSessionDetail'
import { SessionDetail } from './SessionDetail'
import { SourceIcon } from './SourceIcon'
import { formatRelativeTime } from '../utils/formatTime'

interface SessionsPageProps {
  sessions: GobbySession[]
  projects: ProjectInfo[]
  filters: SessionFilters
  onFiltersChange: (filters: SessionFilters) => void
  isLoading: boolean
  onRefresh: () => void
  onAskGobby: (context: string) => void
}

function sourceLabel(source: string): string {
  switch (source) {
    case 'web-chat': return 'Web Chat'
    case 'claude': return 'Claude'
    case 'gemini': return 'Gemini'
    case 'codex': return 'Codex'
    default: return source
  }
}

export function SessionsPage({
  sessions,
  projects,
  filters,
  onFiltersChange,
  isLoading,
  onRefresh,
  onAskGobby,
}: SessionsPageProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)

  const detail = useSessionDetail(selectedSessionId)

  // Time-group sessions
  const grouped = useMemo(() => {
    const now = Date.now()
    const groups: { label: string; sessions: GobbySession[] }[] = [
      { label: 'Today', sessions: [] },
      { label: 'Yesterday', sessions: [] },
      { label: 'Previous 7 Days', sessions: [] },
      { label: 'Older', sessions: [] },
    ]

    for (const s of sessions) {
      const diffMs = now - new Date(s.updated_at).getTime()
      const diffDays = diffMs / 86_400_000
      if (diffDays < 1) groups[0].sessions.push(s)
      else if (diffDays < 2) groups[1].sessions.push(s)
      else if (diffDays < 7) groups[2].sessions.push(s)
      else groups[3].sessions.push(s)
    }

    return groups.filter((g) => g.sessions.length > 0)
  }, [sessions])

  return (
    <div className="sessions-page">
      {/* Left panel: session browser */}
      <div className={`sessions-browser ${sidebarOpen ? '' : 'collapsed'}`}>
        <div className="sessions-sidebar-header">
          {sidebarOpen && <span className="sessions-sidebar-title">Sessions</span>}
          <div className="sessions-sidebar-actions">
            {sidebarOpen && (
              <button
                className="terminals-action-btn"
                onClick={onRefresh}
                title="Refresh"
                disabled={isLoading}
              >
                <RefreshIcon />
              </button>
            )}
            <button
              className="terminals-sidebar-toggle"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              title={sidebarOpen ? 'Collapse' : 'Expand'}
            >
              {sidebarOpen ? '\u25C0' : '\u25B6'}
            </button>
          </div>
        </div>

        {sidebarOpen && (
          <>
            <div className="sessions-filter-bar">
              <input
                className="sessions-filter-input"
                type="text"
                placeholder="Search sessions..."
                value={filters.search}
                onChange={(e) =>
                  onFiltersChange({ ...filters, search: e.target.value })
                }
              />
              <div className="sessions-filter-row">
                <select
                  className="sessions-filter-select"
                  value={filters.source || ''}
                  onChange={(e) =>
                    onFiltersChange({ ...filters, source: e.target.value || null })
                  }
                >
                  <option value="">All Sources</option>
                  {KNOWN_SOURCES.map((s) => (
                    <option key={s} value={s}>
                      {sourceLabel(s)}
                    </option>
                  ))}
                </select>
                <select
                  className="sessions-filter-select"
                  value={filters.projectId || ''}
                  onChange={(e) =>
                    onFiltersChange({ ...filters, projectId: e.target.value || null })
                  }
                >
                  <option value="">All Projects</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
              <select
                className="sessions-filter-select"
                value={filters.sortOrder}
                onChange={(e) =>
                  onFiltersChange({
                    ...filters,
                    sortOrder: e.target.value as 'newest' | 'oldest',
                  })
                }
              >
                <option value="newest">Newest First</option>
                <option value="oldest">Oldest First</option>
              </select>
            </div>

            <div className="sessions-list">
              {sessions.length === 0 && !isLoading && (
                <div className="terminals-empty-sidebar">No sessions found</div>
              )}
              {isLoading && sessions.length === 0 && (
                <div className="terminals-empty-sidebar">Loading...</div>
              )}

              {grouped.map((group) => (
                <div key={group.label} className="session-group">
                  <div className="session-group-label">{group.label}</div>
                  {group.sessions.map((session) => {
                    const title = session.title || `Untitled #${session.ref}`
                    const isSelected = session.id === selectedSessionId
                    return (
                      <div
                        key={session.id}
                        className={`session-item ${isSelected ? 'attached' : ''}`}
                        onClick={() => setSelectedSessionId(session.id)}
                      >
                        <div className="session-item-main">
                          <SourceIcon source={session.source} size={14} />
                          <span className="session-name" title={title}>
                            {title}
                          </span>
                        </div>
                        <div className="session-item-actions">
                          {session.model && (
                            <span className="session-detail-model-badge">
                              {session.model.split('-').slice(-1)[0]}
                            </span>
                          )}
                          <span className="session-meta-count">{session.message_count}msg</span>
                          <span className="session-pid">
                            {formatRelativeTime(session.updated_at)}
                          </span>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Right panel: session detail or empty state */}
      <div className="sessions-main">
        {detail.session ? (
          <SessionDetail
            session={detail.session}
            messages={detail.messages}
            totalMessages={detail.totalMessages}
            hasMore={detail.hasMore}
            isLoading={detail.isLoading}
            onLoadMore={detail.loadMore}
            onAskGobby={onAskGobby}
          />
        ) : (
          <div className="sessions-empty">
            <SessionsIcon size={48} />
            <h3>Select a session</h3>
            <p>Choose a session from the list to view details, stats, and transcript.</p>
          </div>
        )}
      </div>
    </div>
  )
}

function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
  )
}

function SessionsIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
      <line x1="8" y1="21" x2="16" y2="21" />
      <line x1="12" y1="17" x2="12" y2="21" />
    </svg>
  )
}
