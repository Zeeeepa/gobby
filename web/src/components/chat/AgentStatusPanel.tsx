import { useState, useEffect, useMemo } from 'react'
import { cn } from '../../lib/utils'

interface AgentStatusPanelProps {
  agents: Array<{ run_id: string; provider: string; pid?: number; mode?: string; started_at?: string }>
  selectedAgent: string | null
  onSelectAgent: (runId: string | null) => void
  onClose: () => void
}

const PROVIDER_COLORS: Record<string, string> = {
  claude: '#c084fc',
  gemini: '#4ade80',
  codex: '#3b82f6',
  unknown: '#737373',
}

export function AgentStatusPanel({ agents, selectedAgent, onSelectAgent, onClose }: AgentStatusPanelProps) {
  return (
    <div className="agent-status-panel">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <div className="flex items-center gap-2">
          <span className="text-xs font-medium text-foreground">Active Agents</span>
          <span className="text-[10px] font-medium bg-accent/20 text-accent rounded-full px-1.5 py-0.5 min-w-[18px] text-center">
            {agents.length}
          </span>
        </div>
        <button
          className="p-1 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          onClick={onClose}
          title="Close panel"
        >
          <CloseIcon />
        </button>
      </div>

      <div className="flex-1 overflow-y-auto">
        {agents.length === 0 ? (
          <div className="px-3 py-8 text-center">
            <span className="text-xs text-muted-foreground">No agents running</span>
          </div>
        ) : (
          <div className="py-1">
            {agents.map((agent) => (
              <AgentRow
                key={agent.run_id}
                agent={agent}
                isSelected={agent.run_id === selectedAgent}
                onSelect={() => onSelectAgent(agent.run_id === selectedAgent ? null : agent.run_id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}

function AgentRow({
  agent,
  isSelected,
  onSelect,
}: {
  agent: { run_id: string; provider: string; pid?: number; mode?: string; started_at?: string }
  isSelected: boolean
  onSelect: () => void
}) {
  const [uptime, setUptime] = useState('0s')
  const startTime = useMemo(
    () => agent.started_at ? new Date(agent.started_at).getTime() : Date.now(),
    [agent.started_at]
  )

  useEffect(() => {
    const interval = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startTime) / 1000)
      if (elapsed < 60) setUptime(`${elapsed}s`)
      else if (elapsed < 3600) setUptime(`${Math.floor(elapsed / 60)}m`)
      else setUptime(`${Math.floor(elapsed / 3600)}h${Math.floor((elapsed % 3600) / 60)}m`)
    }, 1000)
    return () => clearInterval(interval)
  }, [startTime])

  const color = PROVIDER_COLORS[agent.provider] ?? PROVIDER_COLORS.unknown

  return (
    <button
      className={cn(
        'agent-status-item',
        isSelected && 'bg-accent/10'
      )}
      onClick={onSelect}
    >
      <div className="flex items-center gap-2 min-w-0">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: color }}
        />
        <span className="text-xs text-foreground truncate">{agent.provider}</span>
        {agent.mode && (
          <span className="text-[10px] text-muted-foreground bg-muted rounded px-1 shrink-0">
            {agent.mode}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2 shrink-0">
        {agent.pid && (
          <span className="text-[10px] text-muted-foreground font-mono">{agent.pid}</span>
        )}
        <span className="text-[10px] text-muted-foreground">{uptime}</span>
      </div>
    </button>
  )
}

function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}
