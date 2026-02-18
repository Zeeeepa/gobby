type SegmentKey = 'open' | 'in_progress' | 'closed' | 'blocked'

interface TaskCounts extends Record<SegmentKey, number> {
  ready: number
}

interface Props {
  tasks: TaskCounts
}

const SEGMENTS: readonly { key: SegmentKey; label: string; color: string }[] = [
  { key: 'open', label: 'Open', color: '#3b82f6' },
  { key: 'in_progress', label: 'In Progress', color: '#f59e0b' },
  { key: 'closed', label: 'Closed', color: '#22c55e' },
  { key: 'blocked', label: 'Blocked', color: '#ef4444' },
]

const RADIUS = 36
const STROKE = 8
const SIZE = (RADIUS + STROKE) * 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export function TasksCard({ tasks }: Props) {
  const total = tasks.open + tasks.in_progress + tasks.closed + tasks.blocked

  let offset = 0
  const rings = SEGMENTS.map(({ key, color }) => {
    const value = tasks[key]
    const ratio = total > 0 ? value / total : 0
    const length = ratio * CIRCUMFERENCE
    const ring = { color, length, offset }
    offset += length
    return ring
  })

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Tasks</h3>
      </div>
      <div className="dash-card-body">
        <div className="dash-donut-container">
          <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`}>
            {/* Background ring */}
            <circle
              cx={SIZE / 2}
              cy={SIZE / 2}
              r={RADIUS}
              fill="none"
              stroke="var(--border-color)"
              strokeWidth={STROKE}
            />
            {/* Data segments */}
            {rings.map((ring, i) =>
              ring.length > 0 ? (
                <circle
                  key={i}
                  cx={SIZE / 2}
                  cy={SIZE / 2}
                  r={RADIUS}
                  fill="none"
                  stroke={ring.color}
                  strokeWidth={STROKE}
                  strokeDasharray={`${ring.length} ${CIRCUMFERENCE - ring.length}`}
                  strokeDashoffset={-ring.offset}
                  transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
                />
              ) : null
            )}
            {/* Center total */}
            <text
              x={SIZE / 2}
              y={SIZE / 2}
              textAnchor="middle"
              dominantBaseline="central"
              fill="var(--text-primary)"
              fontSize="16"
              fontWeight="600"
              fontFamily="var(--font-mono)"
            >
              {total}
            </text>
          </svg>
          <div className="dash-donut-legend">
            {SEGMENTS.map(({ key, label, color }) => (
              <div key={key} className="dash-legend-item">
                <span className="dash-legend-dot" style={{ background: color }} />
                <span className="dash-legend-label">{label}</span>
                <span className="dash-legend-value">{tasks[key]}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
