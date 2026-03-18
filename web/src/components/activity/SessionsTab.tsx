import { memo, useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { ResizeHandle } from '../chat/artifacts/ResizeHandle'
import type { GobbySession } from '../../hooks/useSessions'
import { useSessionDetail } from '../../hooks/useSessionDetail'
import { sessionMessagesToChatMessages } from '../sessions/transcriptAdapter'
import { MessageItem } from '../chat/MessageItem'
import { ArtifactContext } from '../chat/artifacts/ArtifactContext'

interface RunningAgent {
  run_id: string
  provider: string
  pid?: number
  mode?: string
  started_at?: string
  session_id?: string
}

interface SessionsTabProps {
  onKillAgent?: (runId: string) => void
  onExpireSession?: (sessionId: string) => void
}

function getBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || ''
}

export const SessionsTab = memo(function SessionsTab({ onKillAgent, onExpireSession }: SessionsTabProps) {
  const [agents, setAgents] = useState<RunningAgent[]>([])
  const [cliSessions, setCliSessions] = useState<GobbySession[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [topHeight, setTopHeight] = useState(35)
  const [expiringIds, setExpiringIds] = useState<Set<string>>(new Set())
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // No-op artifact context for MessageItem rendering
  const noopArtifactCtx = useMemo(() => ({
    openCodeAsArtifact: () => {},
    openFileAsArtifact: () => {},
  }), [])

  // Fetch agents and sessions from API
  const fetchData = useCallback(async () => {
    const baseUrl = getBaseUrl()
    try {
      const [agentsRes, activeRes, pausedRes] = await Promise.all([
        fetch(`${baseUrl}/api/agents/running`).then((r) => (r.ok ? r.json() : { agents: [] })),
        fetch(`${baseUrl}/api/sessions?status=active&limit=50`).then((r) => (r.ok ? r.json() : { sessions: [] })),
        fetch(`${baseUrl}/api/sessions?status=paused&limit=20`).then((r) => (r.ok ? r.json() : { sessions: [] })),
      ])
      setAgents(agentsRes.agents ?? agentsRes ?? [])
      const active = (activeRes.sessions ?? activeRes ?? []).filter((s: any) => s.source !== "pipeline" && s.source !== "cron")
      const paused = (pausedRes.sessions ?? pausedRes ?? []).filter((s: any) => s.source !== "pipeline" && s.source !== "cron")
      setCliSessions([...active, ...paused])
      setExpiringIds(new Set())
      setFetchError(null)
    } catch (err) {
      console.error('Failed to fetch sessions:', err)
      setFetchError('Failed to load sessions')
    } finally {
      setLoading(false)
    }
  }, [])

  // Initial fetch + poll every 5s
  useEffect(() => {
    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [fetchData])

  // Build session entries, deduplicating agents that also appear in sessions
  const entries: SessionEntry[] = useMemo(() => {
    // Collect session IDs owned by agents so we can skip them in the CLI list
    const agentSessionIds = new Set(
      agents.map((a) => a.session_id).filter(Boolean) as string[]
    )

    const agentEntries: SessionEntry[] = agents.map((a) => {
      // Find matching session for richer metadata
      const matchedSession = a.session_id
        ? cliSessions.find((s) => s.id === a.session_id)
        : undefined

      return {
        id: a.session_id ?? a.run_id,
        type: 'agent' as const,
        label: matchedSession?.title ?? (a.mode === 'agent' ? `Agent ${a.run_id.slice(0, 8)}` : `Session ${a.run_id.slice(0, 8)}`),
        provider: a.provider,
        status: 'active' as const,
        runId: a.run_id,
        startedAt: a.started_at,
        seqNum: matchedSession?.seq_num,
        sessionMode: 'autonomous',
      }
    })

    const sessionEntries: SessionEntry[] = cliSessions
      .filter((s) => !agentSessionIds.has(s.id))
      .map((s) => ({
        id: s.id,
        type: 'cli' as const,
        label: s.title ?? `CLI ${s.ref}`,
        provider: s.source ?? 'unknown',
        status: (s.status === 'paused' ? 'paused' : 'active') as 'active' | 'paused',
        startedAt: s.updated_at,
        seqNum: s.seq_num,
        sessionMode: ((s.agent_depth ?? 0) > 0 ? 'autonomous' : 'interactive') as 'interactive' | 'autonomous',
      }))

    // Filter out entries being expired
    return [...agentEntries, ...sessionEntries].filter((e) => !expiringIds.has(e.id))
  }, [agents, cliSessions, expiringIds])

  // Fetch selected session messages
  const { messages, isLoading } = useSessionDetail(selectedSessionId)
  const chatMessages = sessionMessagesToChatMessages(messages)

  // Auto-scroll when new messages arrive
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [chatMessages.length])

  const handleSelect = useCallback((id: string) => {
    setSelectedSessionId((prev) => (prev === id ? null : id))
  }, [])

  const handleExpire = useCallback((entry: SessionEntry) => {
    if (!window.confirm('Expire this session?')) return
    setExpiringIds((prev) => new Set(prev).add(entry.id))
    setSelectedSessionId((prev) => (prev === entry.id ? null : prev))
    if (entry.type === 'agent' && entry.runId) {
      onKillAgent?.(entry.runId)
    } else {
      onExpireSession?.(entry.id)
    }
  }, [onKillAgent, onExpireSession])

  if (loading) {
    return <div className="activity-tab-empty"><p>Loading sessions...</p></div>
  }

  if (fetchError && entries.length === 0) {
    return <div className="activity-tab-empty"><p>{fetchError}</p></div>
  }

  if (entries.length === 0) {
    return (
      <div className="activity-tab-empty">
        <p>No active sessions</p>
        <p className="text-xs text-muted-foreground mt-1">
          Agent and CLI sessions will appear here when active
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* Session list */}
      <div className={`overflow-y-auto ${selectedSessionId ? 'border-b border-border' : 'flex-1'}`} style={selectedSessionId ? { height: `${topHeight}%` } : undefined}>
        {entries.map((entry) => {
          const isSelected = entry.id === selectedSessionId
          const isPaused = entry.status === 'paused'
          const displayLabel = entry.seqNum ? `#${entry.seqNum}: ${entry.label}` : entry.label

          return (
            <div
              key={`${entry.type}-${entry.id}`}
              className={`session-entry${isSelected ? ' session-entry--active' : ''}${isPaused ? ' session-entry--paused' : ''}`}
              onClick={() => handleSelect(entry.id)}
            >
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <span className="text-sm text-foreground truncate">{displayLabel}</span>
              </div>
              <div className="flex items-center gap-1.5">
                <span className="session-type-badge">
                  {entry.sessionMode === 'autonomous' ? 'Autonomous' : 'Interactive'}
                </span>
                <span className="session-type-badge">
                  {isPaused ? 'Paused' : 'Active'}
                </span>
                <button
                  className="session-expire-btn"
                  onClick={(e) => { e.stopPropagation(); handleExpire(entry) }}
                  title="Expire session"
                >
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
                  </svg>
                </button>
              </div>
            </div>
          )
        })}
      </div>

      {/* Resize handle */}
      {selectedSessionId && (
        <ResizeHandle direction="vertical" onResize={setTopHeight} panelHeight={topHeight} minHeight={15} maxHeight={80} />
      )}

      {/* Message area */}
      {selectedSessionId && (
        <div className="flex-1 flex flex-col min-h-0">
          {/* Session header */}
          <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border bg-muted/30">
            <span className="text-xs text-muted-foreground">Watching session</span>
            <button
              className="text-xs text-muted-foreground hover:text-foreground ml-auto"
              onClick={() => setSelectedSessionId(null)}
            >
              Close
            </button>
          </div>

          {/* Messages */}
          <ArtifactContext.Provider value={noopArtifactCtx}>
            <div className="flex-1 overflow-y-auto chat-scaled">
              {isLoading ? (
                <div className="activity-tab-empty"><p>Loading messages...</p></div>
              ) : chatMessages.length === 0 ? (
                <div className="activity-tab-empty"><p>No messages yet</p></div>
              ) : (
                <>
                  {chatMessages.map((msg) => (
                    <MessageItem key={msg.id} message={msg} />
                  ))}
                  <div ref={messagesEndRef} />
                </>
              )}
            </div>
          </ArtifactContext.Provider>
        </div>
      )}
    </div>
  )
})

interface SessionEntry {
  id: string
  type: 'agent' | 'cli'
  label: string
  provider: string
  status: 'active' | 'paused'
  runId?: string
  startedAt?: string
  seqNum?: number | null
  sessionMode?: 'interactive' | 'autonomous'
}
