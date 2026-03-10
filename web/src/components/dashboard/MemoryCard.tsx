import type { AdminStatus } from '../../hooks/useDashboard'

interface Props {
  memory: AdminStatus['memory']
  skills: { total: number }
}

export function MemoryCard({ memory, skills }: Props) {
  const neo4j = memory.neo4j

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Memory</h3>
      </div>
      <div className="dash-card-body">
        <div className="dash-status-list">
          <div className="dash-status-row">
            <span className="dash-status-row-label">Total Memories</span>
            <span className="dash-status-row-value">{memory.count}</span>
          </div>
          <div className="dash-status-row">
            <span className="dash-status-row-label">Skills</span>
            <span className="dash-status-row-value">{skills.total}</span>
          </div>
          {neo4j && (
            <div className="dash-status-row">
              <span
                className={`dash-health-dot dash-health-dot--${neo4j.healthy ? 'healthy' : neo4j.configured ? 'unhealthy' : 'unknown'}`}
              />
              <span className="dash-status-row-label">Neo4j</span>
              <span className="dash-status-row-value" style={{ fontSize: 11 }}>
                {neo4j.healthy ? 'connected' : neo4j.configured ? 'disconnected' : 'not configured'}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
