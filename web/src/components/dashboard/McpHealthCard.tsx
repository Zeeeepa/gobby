import type { AdminStatus } from '../../hooks/useDashboard'

interface Props {
  mcpServers: AdminStatus['mcp_servers']
}

function healthClass(health: string | null): string {
  if (!health) return 'unknown'
  if (health === 'healthy') return 'healthy'
  if (health === 'degraded') return 'degraded'
  if (health === 'unhealthy') return 'unhealthy'
  return 'unknown'
}

export function McpHealthCard({ mcpServers }: Props) {
  const entries = Object.entries(mcpServers ?? {})
  const connected = entries.filter(([, v]) => v.connected).length

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">MCP Servers</h3>
      </div>
      <div className="dash-card-body">
        <div className="dash-health-header">{connected}/{entries.length} connected</div>
        <div className="dash-health-grid">
          {entries.map(([name, server]) => (
            <div key={name} className="dash-health-row">
              <span className={`dash-health-dot dash-health-dot--${healthClass(server.health)}`} />
              <span className="dash-health-name">{name}</span>
              <span className={`dash-health-transport dash-health-transport--${server.transport}`}>
                {server.transport}
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
