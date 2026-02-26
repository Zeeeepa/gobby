import type { MemoryFilters as MemoryFiltersType, MemoryStats } from '../../hooks/useMemory'

interface MemoryFiltersProps {
  filters: MemoryFiltersType
  stats: MemoryStats | null
  recentCount: number
  onFiltersChange: (filters: MemoryFiltersType) => void
}

const MEMORY_TYPES = [
  { key: 'fact', label: 'Fact', color: 'var(--accent)' },
  { key: 'preference', label: 'Preference', color: '#c084fc' },
  { key: 'pattern', label: 'Pattern', color: '#34d399' },
  { key: 'context', label: 'Context', color: '#fbbf24' },
] as const

export function MemoryFilters({ filters, stats, recentCount, onFiltersChange }: MemoryFiltersProps) {
  return (
    <div className="memory-filter-bar">
      <div className="memory-filter-chips">
        {MEMORY_TYPES.map(t => {
          const count = stats?.by_type?.[t.key] ?? 0
          const isActive = filters.memoryType === t.key
          return (
            <button
              key={t.key}
              className={`memory-type-chip ${isActive ? 'active' : ''}`}
              onClick={() =>
                onFiltersChange({
                  ...filters,
                  memoryType: isActive ? null : t.key,
                  recentOnly: false,
                })
              }
            >
              <span className="memory-type-dot" style={{ backgroundColor: t.color }} />
              {t.label}
              <span className="memory-type-chip-count">{count}</span>
            </button>
          )
        })}
        <button
          className={`memory-type-chip ${filters.recentOnly ? 'active' : ''}`}
          onClick={() =>
            onFiltersChange({
              ...filters,
              recentOnly: !filters.recentOnly,
              memoryType: null,
            })
          }
        >
          <span className="memory-type-dot" style={{ backgroundColor: '#22c55e' }} />
          24H
          <span className="memory-type-chip-count">{recentCount}</span>
        </button>
      </div>

      {(filters.memoryType !== null || filters.recentOnly) && (
        <button
          className="memory-filter-clear"
          onClick={() =>
            onFiltersChange({ ...filters, memoryType: null, recentOnly: false })
          }
        >
          Clear filters
        </button>
      )}
    </div>
  )
}
