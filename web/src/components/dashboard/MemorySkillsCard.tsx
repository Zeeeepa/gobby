interface Props {
  memory: { count: number }
  skills: { total: number }
}

export function MemorySkillsCard({ memory, skills }: Props) {
  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Memory & Skills</h3>
      </div>
      <div className="dash-card-body">
        <div className="dash-two-col">
          <div className="dash-two-col-section">
            <span className="dash-two-col-value">{memory.count}</span>
            <span className="dash-two-col-label">Memories</span>
          </div>
          <div className="dash-two-col-section">
            <span className="dash-two-col-value">{skills.total}</span>
            <span className="dash-two-col-label">Skills</span>
          </div>
        </div>
      </div>
    </div>
  )
}
