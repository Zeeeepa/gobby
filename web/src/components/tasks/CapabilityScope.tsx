import { useState, useEffect, useCallback } from 'react'

// =============================================================================
// Types
// =============================================================================

interface MCPServer {
  name: string
  state: string
  connected: boolean
  available: boolean
  transport: string
  enabled?: boolean
}

interface CapabilityGroup {
  label: string
  items: CapabilityItem[]
}

interface CapabilityItem {
  name: string
  available: boolean
  detail?: string
}

// =============================================================================
// Helpers
// =============================================================================

function getBaseUrl(): string {
  const isSecure = window.location.protocol === 'https:'
  return isSecure ? '' : `http://${window.location.hostname}:60887`
}

/** Categorize MCP servers into capability groups. */
function categorizeServers(servers: MCPServer[]): CapabilityGroup[] {
  const groups: CapabilityGroup[] = []

  // Task management
  const taskServer = servers.find(s => s.name === 'gobby-tasks')
  const workflowServer = servers.find(s => s.name === 'gobby-workflows')
  groups.push({
    label: 'Task Management',
    items: [
      { name: 'Tasks', available: taskServer?.available ?? false, detail: taskServer?.state },
      { name: 'Workflows', available: workflowServer?.available ?? false, detail: workflowServer?.state },
    ],
  })

  // Memory & Knowledge
  const memoryServer = servers.find(s => s.name === 'gobby-memory')
  const skillsServer = servers.find(s => s.name === 'gobby-skills')
  groups.push({
    label: 'Memory & Knowledge',
    items: [
      { name: 'Memory', available: memoryServer?.available ?? false, detail: memoryServer?.state },
      { name: 'Skills', available: skillsServer?.available ?? false, detail: skillsServer?.state },
    ],
  })

  // Code & Git
  const worktreeServer = servers.find(s => s.name === 'gobby-worktrees')
  const cloneServer = servers.find(s => s.name === 'gobby-clones')
  const mergeServer = servers.find(s => s.name === 'gobby-merge')
  const github = servers.find(s => s.name === 'github')
  groups.push({
    label: 'Code & Git',
    items: [
      { name: 'Worktrees', available: worktreeServer?.available ?? false },
      { name: 'Clones', available: cloneServer?.available ?? false },
      { name: 'Merge', available: mergeServer?.available ?? false },
      { name: 'GitHub', available: github?.available ?? false, detail: github?.transport },
    ],
  })

  // Agent Orchestration
  const agentServer = servers.find(s => s.name === 'gobby-agents')
  const orchestration = servers.find(s => s.name === 'gobby-orchestration')
  const pipelines = servers.find(s => s.name === 'gobby-pipelines')
  groups.push({
    label: 'Orchestration',
    items: [
      { name: 'Agents', available: agentServer?.available ?? false },
      { name: 'Orchestration', available: orchestration?.available ?? false },
      { name: 'Pipelines', available: pipelines?.available ?? false },
    ],
  })

  // External services
  const external = servers.filter(
    s => !s.name.startsWith('gobby-') && s.name !== 'github'
  )
  if (external.length > 0) {
    groups.push({
      label: 'External Services',
      items: external.map(s => ({
        name: s.name,
        available: s.available,
        detail: s.transport,
      })),
    })
  }

  return groups
}

// =============================================================================
// CapabilityScope
// =============================================================================

interface CapabilityScopeProps {
  sessionId: string
}

export function CapabilityScope({ sessionId: _sessionId }: CapabilityScopeProps) {
  const [servers, setServers] = useState<MCPServer[]>([])
  const [isLoading, setIsLoading] = useState(true)

  const fetchCapabilities = useCallback(async () => {
    setIsLoading(true)
    try {
      const baseUrl = getBaseUrl()
      const response = await fetch(`${baseUrl}/mcp/servers`)
      if (response.ok) {
        const data = await response.json()
        setServers(data.servers || [])
      }
    } catch (e) {
      console.error('Failed to fetch MCP servers:', e)
    }
    setIsLoading(false)
  }, [])

  useEffect(() => {
    fetchCapabilities()
  }, [fetchCapabilities])

  if (isLoading) return <div className="capability-loading">Loading capabilities...</div>
  if (servers.length === 0) return <div className="capability-empty">No capability data</div>

  const groups = categorizeServers(servers)
  const totalAvailable = servers.filter(s => s.available).length
  const totalServers = servers.length

  return (
    <div className="capability-scope">
      {/* Summary bar */}
      <div className="capability-summary">
        <span className="capability-summary-count">{totalAvailable}/{totalServers}</span>
        <span className="capability-summary-label">servers available</span>
      </div>

      {/* Capability groups */}
      {groups.map(group => (
        <div key={group.label} className="capability-group">
          <div className="capability-group-label">{group.label}</div>
          <div className="capability-group-items">
            {group.items.map(item => (
              <div
                key={item.name}
                className={`capability-item ${item.available ? 'capability-item--active' : 'capability-item--inactive'}`}
              >
                <span className="capability-item-dot" />
                <span className="capability-item-name">{item.name}</span>
                {item.detail && (
                  <span className="capability-item-detail">{item.detail}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}
