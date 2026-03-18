import { memo, useState, useEffect, useCallback, useRef, useMemo } from 'react'
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
}

const SOURCE_DOT_COLORS: Record<string, string> = {
  claude_code: 'bg-purple-400',
  claude: 'bg-purple-400',
  claude_sdk_web_chat: 'bg-purple-400',
  gemini_cli: 'bg-green-400',
  gemini: 'bg-green-400',
  codex: 'bg-blue-400',
  windsurf: 'bg-sky-400',
  cursor: 'bg-pink-400',
  copilot: 'bg-indigo-400',
  pipeline: 'bg-amber-400',
  cron: 'bg-amber-400',
}

const SOURCE_LABELS: Record<string, string> = {
  claude_code: 'Claude',
  claude: 'Claude',
  claude_sdk_web_chat: 'Web Chat',
  gemini_cli: 'Gemini',
  gemini: 'Gemini',
  codex: 'Codex',
  windsurf: 'Windsurf',
  cursor: 'Cursor',
  copilot: 'Copilot',
  pipeline: 'Pipeline',
  cron: 'Cron',
}

function getBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || ''
}

export const SessionsTab = memo(function SessionsTab({ onKillAgent }: SessionsTabProps) {
  const [agents, setAgents] = useState<RunningAgent[]>([])
  const [cliSessions, setCliSessions] = useState<GobbySession[]>([])
  const [loading, setLoading] = useState(true)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
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
      const active = (activeRes.sessions ?? activeRes ?? []).filter((s: any) => s.source !== "pipeline")
      const paused = (pausedRes.sessions ?? pausedRes ?? []).filter((s: any) => s.source !== "pipeline")
      setCliSessions([...active, ...paused])
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
      }))

    return [...agentEntries, ...sessionEntries]
  }, [agents, cliSessions])

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

  const handleKill = useCallback((runId: string) => {
    if (!window.confirm('Kill this agent session?')) return
    onKillAgent?.(runId)
  }, [onKillAgent])

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
      <div className={`overflow-y-auto ${selectedSessionId ? 'max-h-[35%] border-b border-border' : 'flex-1'}`}>
        {entries.map((entry) => {
          const dotColor = SOURCE_DOT_COLORS[entry.provider] ?? 'bg-neutral-400'
          const providerLabel = SOURCE_LABELS[entry.provider] ?? entry.provider
          const isSelected = entry.id === selectedSessionId
          const isPaused = entry.status === 'paused'

          return (
            <div
              key={`${entry.type}-${entry.id}`}
              className={`session-entry${isSelected ? ' session-entry--active' : ''}${isPaused ? ' session-entry--paused' : ''}`}
              onClick={() => handleSelect(entry.id)}
            >
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <span className={`w-2 h-2 rounded-full shrink-0 ${dotColor}${!isPaused ? ' session-dot-pulse' : ''}`} />
                <span className="text-sm text-foreground truncate">{entry.label}</span>
                <span className="text-[10px] text-muted-foreground shrink-0">{providerLabel}</span>
              </div>
              <div className="flex items-center gap-1.5">
                {entry.type === 'agent' && (
                  <span className="session-type-badge">agent</span>
                )}
                {isPaused && (
                  <span className="session-type-badge">paused</span>
                )}
                {isSelected && entry.type === 'agent' && entry.runId && onKillAgent && (
                  <button
                    className="session-kill-btn"
                    onClick={(e) => { e.stopPropagation(); handleKill(entry.runId!) }}
                    title="Kill agent"
                  >
                    {'\u2717'}
                  </button>
                )}
              </div>
            </div>
          )
        })}
      </div>

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
}
