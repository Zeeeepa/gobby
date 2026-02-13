import type { McpServer, McpStatus } from '../hooks/useMcp'

interface McpOverviewProps {
  servers: McpServer[]
  status: McpStatus | null
  totalToolCount: number
  activeFilter: string | null
  onFilter: (filter: string | null) => void
}

export function McpOverview({ servers, status, totalToolCount, activeFilter, onFilter }: McpOverviewProps) {
  const connectedCount = status?.connected_servers ?? servers.filter(s => s.connected).length
  const internalCount = servers.filter(s => s.transport === 'internal').length

  const cards = [
    { key: 'total', label: 'Servers', count: servers.length, className: 'mcp-overview-card--total' },
    { key: 'connected', label: 'Connected', count: connectedCount, className: 'mcp-overview-card--connected' },
    { key: 'tools', label: 'Tools', count: totalToolCount, className: 'mcp-overview-card--tools' },
    { key: 'internal', label: 'Internal', count: internalCount, className: 'mcp-overview-card--internal' },
  ]

  return (
    <div className="mcp-overview">
      {cards.map(card => (
        <button
          key={card.key}
          className={`mcp-overview-card ${card.className} ${activeFilter === card.key ? 'mcp-overview-card--active' : ''}`}
          onClick={() => onFilter(activeFilter === card.key ? null : card.key)}
        >
          <span className="mcp-overview-count">{card.count}</span>
          <span className="mcp-overview-label">{card.label}</span>
        </button>
      ))}
    </div>
  )
}
