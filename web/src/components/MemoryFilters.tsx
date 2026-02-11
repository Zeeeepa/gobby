import type { MemoryFilters as MemoryFiltersType } from '../hooks/useMemory'

interface MemoryFiltersProps {
  filters: MemoryFiltersType
  onFiltersChange: (filters: MemoryFiltersType) => void
}

const MEMORY_TYPES = ['fact', 'preference', 'pattern', 'context'] as const

export function MemoryFilters({ filters, onFiltersChange }: MemoryFiltersProps) {
  return (
    <div className="memory-toolbar-filters">
      <input
        className="memory-filter-input"
        type="text"
        placeholder="Search memories..."
        value={filters.search}
        onChange={(e) => onFiltersChange({ ...filters, search: e.target.value })}
        aria-label="Search memories"
      />
      <select
        className="memory-filter-select"
        value={filters.memoryType ?? ''}
        onChange={(e) =>
          onFiltersChange({
            ...filters,
            memoryType: e.target.value || null,
          })
        }
      >
        <option value="">All types</option>
        {MEMORY_TYPES.map((t) => (
          <option key={t} value={t}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </option>
        ))}
      </select>
      <select
        className="memory-filter-select"
        value={
          filters.minImportance !== null ? String(filters.minImportance) : ''
        }
        onChange={(e) =>
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
    </div>
  )
}
