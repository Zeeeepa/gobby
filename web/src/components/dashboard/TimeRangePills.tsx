export type TimeRange = '24h' | '7d' | '30d' | 'all'

const RANGES: { value: TimeRange; label: string }[] = [
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
