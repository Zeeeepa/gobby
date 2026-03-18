import { memo, useState, useEffect, useCallback, useRef } from 'react'
import type { GobbySession } from '../../hooks/useSessions'
import { useSessionDetail } from '../../hooks/useSessionDetail'
import { sessionMessagesToChatMessages } from '../sessions/transcriptAdapter'
import { MessageItem } from '../chat/MessageItem'

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
  gemini_cli: 'bg-green-400',
  codex: 'bg-blue-400',
  windsurf: 'bg-sky-400',
  cursor: 'bg-pink-400',
  copilot: 'bg-indigo-400',
}

const SOURCE_LABELS: Record<string, string> = {
  claude_code: 'Claude',
  gemini_cli: 'Gemini',
  codex: 'Codex',
  windsurf: 'Windsurf',
  cursor: 'Cursor',
  copilot: 'Copilot',
}

function getBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || ''
}

export const SessionsTab = memo(function SessionsTab({ onKillAgent }: SessionsTabProps) {
  const [agents, setAgents] = useState<RunningAgent[]>([])
  const [cliSessions, setCliSessions] = useState<GobbySession[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedSessionId, setSelectedSessionId] = useState<string | null>(null)
  const [mode, setMode] = useState<'observe' | 'attach'>('observe')
  const messagesEndRef = useRef<HTMLDivElement>(null)

  // Fetch agents and sessions from API
  const fetchData = useCallback(async () => {
    const baseUrl = getBaseUrl()
    try {
      const [agentsRes, sessionsRes] = await Promise.all([
        fetch(`${baseUrl}/api/agents/running`).then((r) => (r.ok ? r.json() : { agents: [] })),
        fetch(`${baseUrl}/api/sessions?status=active&limit=50`).then((r) => (r.ok ? r.json() : { sessions: [] })),
      ])
      setAgents(agentsRes.agents ?? agentsRes ?? [])
      setCliSessions(sessionsRes.sessions ?? sessionsRes ?? [])
    } catch {
      // Keep existing data on error
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

  // Build session entries from fetched data
  const entries: SessionEntry[] = [
    ...agents.map((a): SessionEntry => ({
      id: a.session_id ?? a.run_id,
      type: 'agent',
      label: a.mode === 'agent' ? `Agent ${a.run_id.slice(0, 8)}` : `Session ${a.run_id.slice(0, 8)}`,
      provider: a.provider,
      runId: a.run_id,
      startedAt: a.started_at,
    })),
    ...cliSessions.map((s): SessionEntry => ({
      id: s.external_id ?? s.id,
      type: 'cli',
      label: s.title ?? `CLI ${s.ref}`,
      provider: s.source ?? 'unknown',
      startedAt: s.updated_at,
    })),
  ]

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
      {/* Session list header */}
      <div className={`overflow-y-auto ${selectedSessionId ? 'max-h-[35%] border-b border-border' : 'flex-1'}`}>
        {entries.map((entry) => {
          const dotColor = SOURCE_DOT_COLORS[entry.provider] ?? 'bg-neutral-400'
          const providerLabel = SOURCE_LABELS[entry.provider] ?? entry.provider
          const isSelected = entry.id === selectedSessionId

          return (
            <div
              key={entry.id}
              className={`session-entry${isSelected ? ' session-entry--active' : ''}`}
              onClick={() => handleSelect(entry.id)}
            >
              <div className="flex items-center gap-2 min-w-0 flex-1">
                <span className={`w-2 h-2 rounded-full shrink-0 ${dotColor}`} />
                <span className="text-sm text-foreground truncate">{entry.label}</span>
                <span className="text-[10px] text-muted-foreground shrink-0">{providerLabel}</span>
              </div>
              <div className="flex items-center gap-1.5">
                {entry.type === 'agent' && (
                  <span className="session-type-badge">agent</span>
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
          {/* Mode bar */}
          <div className="flex items-center gap-2 px-3 py-1.5 border-b border-border bg-muted/30">
            <button
              className={`session-mode-btn${mode === 'observe' ? ' session-mode-btn--active' : ''}`}
              onClick={() => setMode('observe')}
            >
              Observe
            </button>
            <button
              className={`session-mode-btn${mode === 'attach' ? ' session-mode-btn--active' : ''}`}
              onClick={() => setMode('attach')}
            >
              Attach
            </button>
            <button
              className="text-xs text-muted-foreground hover:text-foreground ml-auto"
              onClick={() => setSelectedSessionId(null)}
            >
              Close
            </button>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto p-2 space-y-2">
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
  runId?: string
  startedAt?: string
}
