import type { MemoryFilters as MemoryFiltersType, MemoryStats } from '../hooks/useMemory'

interface MemoryFiltersProps {
  filters: MemoryFiltersType
  stats: MemoryStats | null
  onFiltersChange: (filters: MemoryFiltersType) => void
}

const MEMORY_TYPES = [
  { key: 'fact', label: 'Fact', color: 'var(--accent)' },
  { key: 'preference', label: 'Preference', color: '#c084fc' },
  { key: 'pattern', label: 'Pattern', color: '#34d399' },
  { key: 'context', label: 'Context', color: '#fbbf24' },
] as const

export function MemoryFilters({ filters, stats, onFiltersChange }: MemoryFiltersProps) {
  const hasFilters = filters.memoryType !== null || filters.minImportance !== null

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
                })
              }
            >
              <span className="memory-type-dot" style={{ backgroundColor: t.color }} />
              {t.label}
              <span className="memory-type-chip-count">{count}</span>
            </button>
          )
        })}
      </div>

      <select
        className="memory-filter-select"
        value={filters.minImportance !== null ? String(filters.minImportance) : ''}
        onChange={e =>
          onFiltersChange({
            ...filters,
            minImportance: e.target.value ? Number(e.target.value) : null,
          })
        }
      >
        <option value="">Any importance</option>
        <option value="0.3">Low (0.3+)</option>
        <option value="0.5">Medium (0.5+)</option>
        <option value="0.7">High (0.7+)</option>
        <option value="0.9">Critical (0.9+)</option>
      </select>

      {hasFilters && (
        <button
          className="memory-filter-clear"
          onClick={() =>
            onFiltersChange({ ...filters, memoryType: null, minImportance: null })
          }
        >
          Clear filters
        </button>
      )}
    </div>
  )
}
