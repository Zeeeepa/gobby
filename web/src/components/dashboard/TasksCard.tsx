import { useTimeStats } from '../../hooks/useTimeStats'

type TaskStats = {
  open: number; in_progress: number; closed: number
  needs_review: number; review_approved: number; escalated: number
  ready: number; blocked: number; closed_24h: number
}

const PIE_SEGMENTS: { key: keyof TaskStats; label: string; color: string }[] = [
  { key: 'ready', label: 'Ready', color: '#8b5cf6' },
  { key: 'in_progress', label: 'In Progress', color: '#f59e0b' },
  { key: 'blocked', label: 'Blocked', color: '#ef4444' },
  { key: 'needs_review', label: 'Needs Review', color: '#06b6d4' },
  { key: 'review_approved', label: 'Approved', color: '#10b981' },
  { key: 'escalated', label: 'Escalated', color: '#f97316' },
]

const SIZE = 120
const STROKE = 18
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

interface Props {
  hours: number
  projectId?: string
}

export function TasksCard({ hours, projectId }: Props) {
  const { data } = useTimeStats(hours, projectId)

  const tasks = data?.tasks ?? {
    open: 0, in_progress: 0, closed: 0,
    needs_review: 0, review_approved: 0, escalated: 0,
    ready: 0, blocked: 0, closed_24h: 0,
  }

  const openTotal = tasks.ready + tasks.in_progress + tasks.blocked +
    tasks.needs_review + tasks.review_approved + tasks.escalated
  const segments = PIE_SEGMENTS.map(s => ({ ...s, value: tasks[s.key] ?? 0 }))
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
        <h3 className="dash-card-title">Tasks</h3>
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
            fontSize="22" fontWeight="bold">{openTotal}</text>
          <text x={SIZE / 2} y={SIZE / 2 + 12} textAnchor="middle" fill="#a3a3a3"
            fontSize="10">open</text>
        </svg>
        <div className="dash-status-list" style={{ flex: 1, minWidth: 0 }}>
          {segments.map(({ key, label, color, value }) => (
            <div key={key} className="dash-status-row">
              <span className="dash-legend-dot" style={{ background: color }} />
              <span className="dash-status-row-label">{label}</span>
              <span className="dash-status-row-value">{value}</span>
            </div>
          ))}
          {tasks.closed > 0 && (
            <div className="dash-status-row dash-status-row--dimmed">
              <span className="dash-legend-dot" style={{ background: '#737373' }} />
              <span className="dash-status-row-label">Closed</span>
              <span className="dash-status-row-value">{tasks.closed}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
