export interface StatusBadgeProps {
  status: string
  size?: 'sm' | 'md'
}

const STATUS_CLASS: Record<string, string> = {
  active: 'green', open: 'green', success: 'green',
  stale: 'amber', cleanup: 'amber', pending: 'amber',
  merged: 'purple',
  abandoned: 'red', closed: 'red', failure: 'red',
  syncing: 'blue', in_progress: 'blue',
  draft: 'muted', cancelled: 'muted', queued: 'muted',
}

export function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const key = status?.toLowerCase() ?? ''
  const variant = STATUS_CLASS[key] || 'muted'
  return (
    <span className={`sc-badge sc-badge--${size} sc-badge--${variant}`}>
      {status}
    </span>
  )
}
