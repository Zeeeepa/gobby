import { useState } from 'react'
import type { AdminStatus } from '../../hooks/useDashboard'
import { TimeRangePills, type TimeRange } from './TimeRangePills'

interface Props {
  sessions: AdminStatus['sessions']
}

const SEGMENTS: { key: string; label: string; color: string }[] = [
  { key: 'active', label: 'Active', color: '#22c55e' },
  { key: 'paused', label: 'Paused', color: '#f59e0b' },
  { key: 'handoff_ready', label: 'Handoff Ready', color: '#8b5cf6' },
]

const SIZE = 120
const STROKE = 18
const RADIUS = (SIZE - STROKE) / 2
const CIRCUMFERENCE = 2 * Math.PI * RADIUS

export function SessionsCard({ sessions }: Props) {
  const [range, setRange] = useState<TimeRange>('all')

  const other = Math.max(
    0,
    sessions.total - sessions.active - sessions.paused - sessions.handoff_ready
  )

  const segments = [
    ...SEGMENTS.map(s => ({ ...s, value: sessions[s.key as keyof typeof sessions] as number })),
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

  return (
    <div className="dash-card">
      <div className="dash-card-header">
        <h3 className="dash-card-title">Sessions</h3>
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
            fontSize="22" fontWeight="bold">{sessions.total}</text>
          <text x={SIZE / 2} y={SIZE / 2 + 12} textAnchor="middle" fill="#a3a3a3"
            fontSize="10">total</text>
        </svg>
        <div className="dash-status-list" style={{ flex: 1, minWidth: 0 }}>
          {segments.map(({ key, label, color, value }) => (
            <div key={key} className={`dash-status-row${key === 'other' ? ' dash-status-row--dimmed' : ''}`}>
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
