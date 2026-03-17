import { useState } from 'react'
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
  const [showAllMcps, setShowAllMcps] = useState(false)

  // External MCP servers (non-internal)
  const externalMcps = Object.entries(mcp_servers ?? {})
    .filter(([, info]) => !info.internal)
    .sort(([a], [b]) => a.localeCompare(b))

  const visibleMcps = showAllMcps ? externalMcps : externalMcps.slice(0, 3)
  const hasMoreMcps = externalMcps.length > 3

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

        <div className="dash-services-status">
          {qdrant && (
            <div className="dash-service-row">
              <span
                className={`dash-health-dot dash-health-dot--${qdrant.healthy ? 'healthy' : qdrant.configured ? 'unhealthy' : 'unknown'}`}
              />
              <span>Qdrant {qdrant.healthy ? 'connected' : qdrant.configured ? 'disconnected' : 'not configured'}</span>
            </div>
          )}
          {neo4j && (
            <div className="dash-service-row">
              <span
                className={`dash-health-dot dash-health-dot--${neo4j.healthy ? 'healthy' : neo4j.configured ? 'unhealthy' : 'unknown'}`}
              />
              <span>Neo4j {neo4j.healthy ? 'connected' : neo4j.configured ? 'disconnected' : 'not configured'}</span>
            </div>
          )}
        </div>

        {externalMcps.length > 0 && (
          <div className="dash-external-mcps">
            <div className="dash-external-mcps-header">External MCPs</div>
            {visibleMcps.map(([name, info]) => (
              <div key={name} className="dash-service-row">
                <span
                  className={`dash-health-dot dash-health-dot--${info.health === 'healthy' ? 'healthy' : info.connected ? 'degraded' : 'unhealthy'}`}
                />
                <span className="dash-health-name">{name}</span>
              </div>
            ))}
            {hasMoreMcps && (
              <button
                className="dash-mcp-toggle"
                onClick={() => setShowAllMcps(!showAllMcps)}
              >
                {showAllMcps ? 'Show less' : `Show all ${externalMcps.length} servers`}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  )
}
