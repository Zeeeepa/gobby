import type { AdminStatus } from '../../hooks/useDashboard'

interface Props {
  tasks: AdminStatus['tasks']
}

const STATUS_ROWS: { key: keyof AdminStatus['tasks']; label: string; color: string; dimmed?: boolean }[] = [
  { key: 'open', label: 'Open', color: '#3b82f6' },
  { key: 'ready', label: 'Ready', color: '#8b5cf6' },
  { key: 'in_progress', label: 'In Progress', color: '#f59e0b' },
  { key: 'blocked', label: 'Blocked', color: '#ef4444' },
  { key: 'needs_review', label: 'Needs Review', color: '#06b6d4' },
  { key: 'review_approved', label: 'Approved', color: '#10b981' },
  { key: 'escalated', label: 'Escalated', color: '#f97316' },
  { key: 'closed_24h', label: 'Closed (24h)', color: '#737373', dimmed: true },
]

export function TasksCard({ tasks }: Props) {
  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Tasks</h3>
      </div>
      <div className="dash-card-body">
        <div className="dash-status-list">
          {STATUS_ROWS.map(({ key, label, color, dimmed }) => {
            const value = tasks[key] ?? 0
            return (
              <div
                key={key}
                className={`dash-status-row${dimmed ? ' dash-status-row--dimmed' : ''}`}
              >
                <span className="dash-legend-dot" style={{ background: color }} />
                <span className="dash-status-row-label">{label}</span>
                <span className="dash-status-row-value">{value}</span>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}
