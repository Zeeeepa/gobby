import { useEffect, useState } from 'react'
import type { GobbyTask } from '../../hooks/useTasks'

// =============================================================================
// Relative time helper
// =============================================================================

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

// =============================================================================
// Status label mapping
// =============================================================================

const STEP_LABELS: Record<string, string> = {
  open: 'Waiting',
  in_progress: 'Working',
  needs_review: 'In Review',
  approved: 'Approved',
  closed: 'Done',
  escalated: 'Escalated',
}

// =============================================================================
// TaskStatusStrip
// =============================================================================

interface TaskStatusStripProps {
  task: GobbyTask
  compact?: boolean
}

export function TaskStatusStrip({ task, compact }: TaskStatusStripProps) {
  const isActive = task.status === 'in_progress'
  const agentLabel = task.agent_name || (task.assignee ? `#${task.assignee.slice(0, 6)}` : null)
  const stepLabel = STEP_LABELS[task.status] || task.status

  // Live-updating relative timestamp
  const [timeLabel, setTimeLabel] = useState(() => relativeTime(task.updated_at))
  useEffect(() => {
    setTimeLabel(relativeTime(task.updated_at))
    if (!isActive) return
    const interval = window.setInterval(() => setTimeLabel(relativeTime(task.updated_at)), 30000)
    return () => window.clearInterval(interval)
  }, [task.updated_at, isActive])

  // Only show strip if task has activity (assigned or in-progress)
  if (!agentLabel && !isActive) return null

  return (
    <div className={`task-status-strip ${isActive ? 'task-status-strip--active' : ''} ${compact ? 'task-status-strip--compact' : ''}`}>
      {isActive && <span className="task-status-strip-pulse" />}
      {agentLabel && <span className="task-status-strip-agent">{agentLabel}</span>}
      <span className="task-status-strip-step">{stepLabel}</span>
      <span className="task-status-strip-time">{timeLabel}</span>
    </div>
  )
}
