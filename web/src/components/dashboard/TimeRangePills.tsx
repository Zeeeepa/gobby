export type TimeRange = '1h' | '24h' | '7d' | '30d' | 'all'

const RANGES: { value: TimeRange; label: string }[] = [
  { value: '1h', label: '1h' },
  { value: '24h', label: '24h' },
  { value: '7d', label: '7d' },
  { value: '30d', label: '30d' },
  { value: 'all', label: 'All' },
]

interface Props {
  value: TimeRange
  onChange: (range: TimeRange) => void
}

export function TimeRangePills({ value, onChange }: Props) {
  return (
    <div className="dash-time-range">
      {RANGES.map(r => (
        <button
          key={r.value}
          className={`dash-time-range-btn${value === r.value ? ' dash-time-range-btn--active' : ''}`}
          onClick={() => onChange(r.value)}
        >
          {r.label}
        </button>
      ))}
    </div>
  )
}

export function rangeToHours(range: TimeRange): number {
  const map: Record<TimeRange, number> = {
    '1h': 1,
    '24h': 24,
    '7d': 168,
    '30d': 720,
    'all': 0,
  }
  return map[range]
}
