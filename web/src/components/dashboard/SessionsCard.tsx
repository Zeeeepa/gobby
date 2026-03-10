import type { AdminStatus } from '../../hooks/useDashboard'

interface Props {
  sessions: AdminStatus['sessions']
}

const STATUS_ROWS: { key: keyof AdminStatus['sessions']; label: string; color: string }[] = [
  { key: 'active', label: 'Active', color: '#22c55e' },
  { key: 'paused', label: 'Paused', color: '#f59e0b' },
  { key: 'handoff_ready', label: 'Handoff Ready', color: '#8b5cf6' },
]

export function SessionsCard({ sessions }: Props) {
  const other = Math.max(
    0,
    sessions.total - sessions.active - sessions.paused - sessions.handoff_ready
  )

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Sessions</h3>
      </div>
      <div className="dash-card-body">
        <div className="dash-status-list">
          {STATUS_ROWS.map(({ key, label, color }) => (
            <div key={key} className="dash-status-row">
              <span className="dash-legend-dot" style={{ background: color }} />
              <span className="dash-status-row-label">{label}</span>
              <span className="dash-status-row-value">{sessions[key]}</span>
            </div>
          ))}
          {other > 0 && (
            <div className="dash-status-row dash-status-row--dimmed">
              <span className="dash-legend-dot" style={{ background: '#737373' }} />
              <span className="dash-status-row-label">Expired/Closed</span>
              <span className="dash-status-row-value">{other}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
