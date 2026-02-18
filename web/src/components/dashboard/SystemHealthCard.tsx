import type { AdminStatus } from '../../hooks/useDashboard'

function formatUptime(seconds: number | null): string {
  if (seconds == null) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

interface Props {
  data: AdminStatus
}

export function SystemHealthCard({ data }: Props) {
  const { server, process, background_tasks, status } = data

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">System Health</h3>
        <span className={`dash-status-badge dash-status-badge--${status}`}>
          {status}
        </span>
      </div>
      <div className="dash-card-body">
        <div className="dash-stat-grid">
          <div className="dash-stat">
            <span className="dash-stat-value">{formatUptime(server.uptime_seconds)}</span>
            <span className="dash-stat-label">Uptime</span>
          </div>
          <div className="dash-stat">
            <span className="dash-stat-value">
              {process ? `${process.memory_rss_mb}` : '—'}
            </span>
            <span className="dash-stat-label">Memory (MB)</span>
          </div>
          <div className="dash-stat">
            <span className="dash-stat-value">
              {process ? `${process.cpu_percent}%` : '—'}
            </span>
            <span className="dash-stat-label">CPU</span>
          </div>
          <div className="dash-stat">
            <span className="dash-stat-value">{background_tasks.active}</span>
            <span className="dash-stat-label">Background Tasks</span>
          </div>
        </div>
      </div>
    </div>
  )
}
