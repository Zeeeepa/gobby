interface SessionCounts {
  active: number
  paused: number
  handoff_ready: number
  total: number
}

interface Props {
  sessions: SessionCounts
}

type SegmentKey = 'active' | 'paused' | 'handoff_ready'

const SEGMENTS: readonly { key: SegmentKey; label: string; color: string }[] = [
  { key: 'active', label: 'Active', color: '#22c55e' },
  { key: 'paused', label: 'Paused', color: '#f59e0b' },
  { key: 'handoff_ready', label: 'Handoff', color: '#8b5cf6' },
]

export function SessionsCard({ sessions }: Props) {
  const { total } = sessions
  const other = Math.max(0, total - sessions.active - sessions.paused - sessions.handoff_ready)

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Sessions</h3>
      </div>
      <div className="dash-card-body">
        <div className="dash-big-stat">{total}</div>
        <div className="dash-bar-container">
          <div className="dash-bar-track">
            {total > 0 ? (
              <>
                {SEGMENTS.map(({ key, label, color }) => {
                  const value = sessions[key]
                  const pct = (value / total) * 100
                  return pct > 0 ? (
                    <div
                      key={key}
                      className="dash-bar-segment"
                      style={{ width: `${pct}%`, background: color }}
                      role="img"
                      aria-label={`${label}: ${value} of ${total}`}
                    />
                  ) : null
                })}
                {other > 0 && (
                  <div
                    className="dash-bar-segment"
                    style={{ width: `${(other / total) * 100}%`, background: '#737373' }}
                    role="img"
                    aria-label={`Other: ${other} of ${total}`}
                  />
                )}
              </>
            ) : null}
          </div>
          <div className="dash-bar-labels">
            {SEGMENTS.map(({ key, label, color }) => (
              <div key={key} className="dash-bar-label">
                <span className="dash-bar-label-dot" style={{ background: color }} />
                <span className="dash-bar-label-text">{label}</span>
                <span className="dash-bar-label-value">{sessions[key]}</span>
              </div>
            ))}
            {other > 0 && (
              <div className="dash-bar-label">
                <span className="dash-bar-label-dot" style={{ background: '#737373' }} />
                <span className="dash-bar-label-text">Other</span>
                <span className="dash-bar-label-value">{other}</span>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
