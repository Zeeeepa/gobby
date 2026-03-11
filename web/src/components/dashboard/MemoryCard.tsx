import type { AdminStatus } from '../../hooks/useDashboard'

interface Props {
  memory: AdminStatus['memory']
}

const TYPE_COLORS: Record<string, { label: string; color: string }> = {
  fact: { label: 'Facts', color: '#3b82f6' },
  preference: { label: 'Preferences', color: '#8b5cf6' },
  pattern: { label: 'Patterns', color: '#f59e0b' },
  context: { label: 'Context', color: '#10b981' },
}

const SIZE = 120
const STROKE = 18
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export function MemoryCard({ memory }: Props) {
  const byType = memory.by_type ?? {}
  const segments = Object.entries(byType)
    .map(([type, count]) => {
      const meta = TYPE_COLORS[type] ?? { label: type, color: '#737373' }
      return { key: type, label: meta.label, color: meta.color, value: count }
    })
    .filter(s => s.value > 0)

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
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="dash-status-list">
            {segments.map(({ key, label, color, value }) => (
              <div key={key} className="dash-status-row">
                <span className="dash-legend-dot" style={{ background: color }} />
                <span className="dash-status-row-label">{label}</span>
                <span className="dash-status-row-value">{value}</span>
              </div>
            ))}
          </div>
          {memory.recent_count > 0 && (
            <div className="dash-status-row dash-status-row--dimmed" style={{ marginTop: 6 }}>
              <span className="dash-status-row-label">Created (24h)</span>
              <span className="dash-status-row-value">{memory.recent_count}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
