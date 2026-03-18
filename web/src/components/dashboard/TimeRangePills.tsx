import { cn } from '../../lib/utils'

export type TimeRange = '1h' | '6h' | '12h' | '24h' | '7d' | '30d' | 'all'

const RANGES: { value: TimeRange; label: string }[] = [
  { value: '1h', label: '1h' },
  { value: '6h', label: '6h' },
  { value: '12h', label: '12h' },
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
    <div className="flex rounded-md border border-border text-xs">
      {RANGES.map((r, i) => (
        <button
          key={r.value}
          className={cn(
            'px-2 py-1 transition-colors',
            i === 0 && 'rounded-l-md',
            i === RANGES.length - 1 && 'rounded-r-md',
            value === r.value
              ? 'bg-accent text-accent-foreground'
              : 'text-muted-foreground hover:bg-muted',
          )}
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
    '6h': 6,
    '12h': 12,
    '24h': 24,
    '7d': 168,
    '30d': 720,
    'all': 0,
  }
  return map[range]
}
