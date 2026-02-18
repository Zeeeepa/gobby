interface StatusBadgeProps {
  status: string
  size?: 'sm' | 'md'
}

const STATUS_COLORS: Record<string, { bg: string; color: string }> = {
  // Worktree/clone statuses
  active: { bg: '#052e16', color: '#4ade80' },
  stale: { bg: '#451a03', color: '#fb923c' },
  merged: { bg: '#1e1b4b', color: '#a78bfa' },
  abandoned: { bg: '#450a0a', color: '#f87171' },
  syncing: { bg: '#0c4a6e', color: '#38bdf8' },
  cleanup: { bg: '#451a03', color: '#fbbf24' },
  // PR states
  open: { bg: '#052e16', color: '#4ade80' },
  closed: { bg: '#450a0a', color: '#f87171' },
  draft: { bg: '#1a1a2e', color: '#a3a3a3' },
  // CI conclusions
  success: { bg: '#052e16', color: '#4ade80' },
  failure: { bg: '#450a0a', color: '#f87171' },
  cancelled: { bg: '#1a1a2e', color: '#737373' },
  pending: { bg: '#451a03', color: '#fbbf24' },
  in_progress: { bg: '#0c4a6e', color: '#38bdf8' },
  queued: { bg: '#1a1a2e', color: '#a3a3a3' },
}

export function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const key = status?.toLowerCase() ?? ''
  const colors = STATUS_COLORS[key] || { bg: '#1a1a2e', color: '#a3a3a3' }
  return (
    <span
      className={`sc-badge sc-badge--${size}`}
      style={{ background: colors.bg, color: colors.color }}
    >
      {status}
    </span>
  )
}
