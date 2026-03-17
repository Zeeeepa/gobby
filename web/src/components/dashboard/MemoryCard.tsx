import { useTimeStats } from '../../hooks/useTimeStats'

const TYPE_COLORS: Record<string, { label: string; color: string }> = {
  fact: { label: 'Facts', color: '#3b82f6' },
  preference: { label: 'Preferences', color: '#8b5cf6' },
  pattern: { label: 'Patterns', color: '#f59e0b' },
  context: { label: 'Context', color: '#10b981' },
}

const FALLBACK_COLOR = '#737373'
const MAX_CATEGORIES = 5

const SIZE = 120
const STROKE = 18
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

interface Props {
  hours: number
  projectId?: string
}

export function MemoryCard({ hours, projectId }: Props) {
  const { data } = useTimeStats(hours, projectId)

  const memory = data?.memory ?? { count: 0, by_type: {}, recent_count: 0 }

  const byType = memory.by_type ?? {}
  const allSegments = Object.entries(byType)
    .map(([type, count]) => {
      const meta = TYPE_COLORS[type] ?? { label: type, color: FALLBACK_COLOR }
      return { key: type, label: meta.label, color: meta.color, value: count }
    })
    .filter(s => s.value > 0)
    .sort((a, b) => b.value - a.value)

  // Show top 5, collapse rest into "Other"
  const top = allSegments.slice(0, MAX_CATEGORIES)
  const restValue = allSegments.slice(MAX_CATEGORIES).reduce((sum, s) => sum + s.value, 0)
  const segments = restValue > 0
    ? [...top, { key: '_other', label: 'Other', color: FALLBACK_COLOR, value: restValue }]
    : top

  const total = segments.reduce((sum, s) => sum + s.value, 0)

  let offset = 0
  const arcs = segments.map(s => {
    const fraction = total > 0 ? s.value / total : 0
    const dashLen = fraction * CIRCUMFERENCE
    const arc = { ...s, dashLen, dashOffset: -offset }
    offset += dashLen
    return arc
  })

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Memory</h3>
      </div>
      <div className="dash-card-body" style={{ display: 'flex', gap: 16, alignItems: 'center' }}>
        <svg width={SIZE} height={SIZE} style={{ flexShrink: 0 }}>
          {total === 0 ? (
            <circle cx={SIZE / 2} cy={SIZE / 2} r={RADIUS}
              fill="none" stroke="#333" strokeWidth={STROKE} />
          ) : (
            arcs.map(a => (
              <circle key={a.key} cx={SIZE / 2} cy={SIZE / 2} r={RADIUS}
                fill="none" stroke={a.color} strokeWidth={STROKE}
                strokeDasharray={`${a.dashLen} ${CIRCUMFERENCE - a.dashLen}`}
                strokeDashoffset={a.dashOffset}
                transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
              />
            ))
          )}
          <text x={SIZE / 2} y={SIZE / 2 - 6} textAnchor="middle" fill="#e5e5e5"
            fontSize="22" fontWeight="bold">{memory.count}</text>
          <text x={SIZE / 2} y={SIZE / 2 + 12} textAnchor="middle" fill="#a3a3a3"
            fontSize="10">total</text>
        </svg>
        <div className="dash-status-list" style={{ flex: 1, minWidth: 0 }}>
          {segments.map(({ key, label, color, value }) => (
            <div key={key} className={`dash-status-row${key === '_other' ? ' dash-status-row--dimmed' : ''}`}>
              <span className="dash-legend-dot" style={{ background: color }} />
              <span className="dash-status-row-label">{label}</span>
              <span className="dash-status-row-value">{value}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
