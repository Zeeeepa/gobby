import { useTimeStats } from '../../hooks/useTimeStats'

const STATUS_SEGMENTS: { key: string; label: string; color: string }[] = [
  { key: 'active', label: 'Active', color: '#22c55e' },
  { key: 'paused', label: 'Paused', color: '#f59e0b' },
  { key: 'handoff_ready', label: 'Handoff Ready', color: '#8b5cf6' },
]

const SOURCE_COLORS: Record<string, string> = {
  claude_code: '#f97316',
  gemini: '#3b82f6',
  cursor: '#06b6d4',
  windsurf: '#10b981',
  copilot: '#8b5cf6',
}

const SIZE = 120
const STROKE = 18
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

interface Props {
  hours: number
  projectId?: string
}

export function SessionsCard({ hours, projectId }: Props) {
  const { data } = useTimeStats(hours, projectId)

  const sessions = data?.sessions ?? { active: 0, paused: 0, handoff_ready: 0, total: 0, by_source: {} }

  const other = Math.max(
    0,
    sessions.total - sessions.active - sessions.paused - sessions.handoff_ready
  )

  const segments = [
    ...STATUS_SEGMENTS.map(s => ({ ...s, value: sessions[s.key as keyof typeof sessions] as number })),
    ...(other > 0 ? [{ key: 'other', label: 'Expired/Closed', color: '#737373', value: other }] : []),
  ]

  const total = segments.reduce((sum, s) => sum + s.value, 0)

  let offset = 0
  const arcs = segments
    .filter(s => s.value > 0)
    .map(s => {
      const fraction = total > 0 ? s.value / total : 0
      const dashLen = fraction * CIRCUMFERENCE
      const arc = { ...s, dashLen, dashOffset: -offset }
      offset += dashLen
      return arc
    })

  // Source breakdown from by_source data
  const bySource = sessions.by_source ?? {}
  const sourceEntries = Object.entries(bySource)
    .map(([src, statuses]) => ({
      source: src,
      total: Object.values(statuses).reduce((sum, n) => sum + n, 0),
    }))
    .sort((a, b) => b.total - a.total)

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Sessions</h3>
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
            fontSize="22" fontWeight="bold">{sessions.total}</text>
          <text x={SIZE / 2} y={SIZE / 2 + 12} textAnchor="middle" fill="#a3a3a3"
            fontSize="10">total</text>
        </svg>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="dash-status-list">
            {segments.map(({ key, label, color, value }) => (
              <div key={key} className={`dash-status-row${key === 'other' ? ' dash-status-row--dimmed' : ''}`}>
                <span className="dash-legend-dot" style={{ background: color }} />
                <span className="dash-status-row-label">{label}</span>
                <span className="dash-status-row-value">{value}</span>
              </div>
            ))}
          </div>
          {sourceEntries.length > 0 && (
            <div className="dash-breakdown">
              {sourceEntries.map(({ source, total: cnt }) => (
                <div key={source} className="dash-breakdown-row">
                  <span className="dash-breakdown-label">
                    <span className="dash-legend-dot" style={{
                      background: SOURCE_COLORS[source] ?? '#737373',
                      display: 'inline-block',
                      marginRight: 6,
                      verticalAlign: 'middle',
                    }} />
                    {source.replace(/_/g, ' ')}
                  </span>
                  <span className="dash-breakdown-value">{cnt}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
