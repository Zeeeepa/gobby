import type { AdminStatus } from '../../hooks/useDashboard'

function formatUptime(seconds: number | null): string {
  if (seconds == null) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.round((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  if (m > 0) return `${m}m`
  return `${Math.round(seconds)}s`
}

interface Props {
  data: AdminStatus
}

export function SystemHealthCard({ data }: Props) {
  const { server, process, background_tasks, status, memory, mcp_servers } = data
  const neo4j = memory?.neo4j
  const qdrant = memory?.qdrant

  // External MCP servers summary
  const externalMcps = Object.entries(mcp_servers ?? {}).filter(([, info]) => !info.internal)
  const externalHealthy = externalMcps.filter(([, info]) => info.health === 'healthy' || info.connected).length
  const externalTotal = externalMcps.length

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
          {background_tasks.active > 0 && (
            <div className="dash-stat">
              <span className="dash-stat-value">{background_tasks.active}</span>
              <span className="dash-stat-label">Background Tasks</span>
            </div>
          )}
        </div>

        <div className="dash-services-status">
          {[
            qdrant && {
              id: 'qdrant',
              label: `Qdrant ${qdrant.healthy ? 'connected' : qdrant.configured ? 'disconnected' : 'not configured'}`,
              status: qdrant.healthy ? 'healthy' : qdrant.configured ? 'unhealthy' : 'unknown',
            },
            neo4j && {
              id: 'neo4j',
              label: `Neo4j ${neo4j.healthy ? 'connected' : neo4j.configured ? 'disconnected' : 'not configured'}`,
              status: neo4j.healthy ? 'healthy' : neo4j.configured ? 'unhealthy' : 'unknown',
            },
            externalTotal > 0 && {
              id: 'external-mcps',
              label: `External MCPs ${externalHealthy}/${externalTotal} connected`,
              status: externalHealthy === externalTotal ? 'healthy' : externalHealthy > 0 ? 'degraded' : 'unhealthy',
            },
          ]
            .filter((s): s is { id: string; label: string; status: string } => !!s)
            .sort((a, b) => a.label.localeCompare(b.label))
            .map(s => (
              <div key={s.id} className="dash-service-row">
                <span className={`dash-health-dot dash-health-dot--${s.status}`} />
                <span>{s.label}</span>
              </div>
            ))}
        </div>
      </div>
    </div>
  )
}
