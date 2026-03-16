import { useState } from 'react'
import { useTimeStats, rangeToDays } from '../../hooks/useTimeStats'
import { TimeRangePills, type TimeRange } from './TimeRangePills'

type TaskStats = {
  open: number; in_progress: number; closed: number
  needs_review: number; review_approved: number; escalated: number
  ready: number; blocked: number; closed_24h: number
}

const SEGMENTS: { key: keyof TaskStats; label: string; color: string; dimmed?: boolean }[] = [
  { key: 'ready', label: 'Ready', color: '#8b5cf6' },
  { key: 'in_progress', label: 'In Progress', color: '#f59e0b' },
  { key: 'blocked', label: 'Blocked', color: '#ef4444' },
  { key: 'needs_review', label: 'Needs Review', color: '#06b6d4' },
  { key: 'review_approved', label: 'Approved', color: '#10b981' },
  { key: 'escalated', label: 'Escalated', color: '#f97316' },
  { key: 'closed_24h', label: 'Closed (24h)', color: '#737373', dimmed: true },
]

const SIZE = 120
const STROKE = 18
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export function TasksCard() {
  const [range, setRange] = useState<TimeRange>('all')
  const { data } = useTimeStats(rangeToDays(range))

  const tasks = data?.tasks ?? {
    open: 0, in_progress: 0, closed: 0,
    needs_review: 0, review_approved: 0, escalated: 0,
    ready: 0, blocked: 0, closed_24h: 0,
  }

  const activeTotal = tasks.open + tasks.in_progress + tasks.needs_review +
    tasks.review_approved + tasks.escalated
  const segments = SEGMENTS.map(s => ({ ...s, value: tasks[s.key] ?? 0 }))
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

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Tasks</h3>
        <TimeRangePills value={range} onChange={setRange} />
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
            fontSize="22" fontWeight="bold">{activeTotal}</text>
          <text x={SIZE / 2} y={SIZE / 2 + 12} textAnchor="middle" fill="#a3a3a3"
            fontSize="10">active</text>
        </svg>
        <div className="dash-status-list" style={{ flex: 1, minWidth: 0 }}>
          {segments.map(({ key, label, color, value, dimmed }) => (
            <div key={key} className={`dash-status-row${dimmed ? ' dash-status-row--dimmed' : ''}`}>
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
