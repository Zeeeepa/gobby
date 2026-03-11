import { useState } from 'react'
import type { AdminStatus } from '../../hooks/useDashboard'

interface Props {
  mcpServers: AdminStatus['mcp_servers']
}

const VALID_HEALTH = new Set(['healthy', 'degraded', 'unhealthy'])

function healthClass(health: string | null): string {
  return (health && VALID_HEALTH.has(health)) ? health : 'unknown'
}

export function McpHealthCard({ mcpServers }: Props) {
  const entries = Object.entries(mcpServers ?? {})
  const connected = entries.filter(([, v]) => v.connected).length
  const unhealthy = entries.filter(([, v]) => v.health !== 'healthy' && v.health !== null)
  const healthy = entries.filter(([, v]) => v.health === 'healthy' || v.health === null)
  const allHealthy = unhealthy.length === 0
  const [expanded, setExpanded] = useState(false)

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">MCP Servers</h3>
        {allHealthy && (
          <span className="dash-status-badge dash-status-badge--healthy">
            all connected
          </span>
        )}
      </div>
      <div className="dash-card-body">
        <div className="dash-health-header">
          <span className={`dash-health-dot dash-health-dot--${allHealthy ? 'healthy' : 'degraded'}`} />
          {' '}{connected}/{entries.length} connected
        </div>

        {/* Always show unhealthy servers */}
        {unhealthy.length > 0 && (
          <div className="dash-health-grid">
            {unhealthy.map(([name, server]) => (
              <div key={name} className="dash-health-row">
                <span className={`dash-health-dot dash-health-dot--${healthClass(server.health)}`} />
                <span className="dash-health-name">{name}</span>
                <span className={`dash-health-transport dash-health-transport--${server.transport}`}>
                  {server.transport}
                </span>
              </div>
            ))}
          </div>
        )}

        {/* Collapsible healthy servers */}
        {healthy.length > 0 && (
          <>
            <button
              className="dash-mcp-toggle"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? 'Hide' : 'Show'} {healthy.length} healthy server{healthy.length !== 1 ? 's' : ''}
            </button>
            {expanded && (
              <div className="dash-health-grid">
                {healthy.map(([name, server]) => (
                  <div key={name} className="dash-health-row">
                    <span className={`dash-health-dot dash-health-dot--${healthClass(server.health)}`} />
                    <span className="dash-health-name">{name}</span>
                    <span className={`dash-health-transport dash-health-transport--${server.transport}`}>
                      {server.transport}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
