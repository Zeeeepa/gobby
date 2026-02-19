import { useMemo } from 'react'
import type { GobbyMemory, MemoryStats } from '../hooks/useMemory'

interface MemoryOverviewProps {
  memories: GobbyMemory[]
  stats: MemoryStats | null
  activeFilter: string | null
  onFilter: (filter: string | null) => void
}

const TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000

export function MemoryOverview({ memories, activeFilter, onFilter }: MemoryOverviewProps) {
  const typeCounts = useMemo(() => {
    const counts: Record<string, number> = {}
    for (const m of memories) {
      counts[m.memory_type] = (counts[m.memory_type] || 0) + 1
    }
    return counts
  }, [memories])

  const recentCount = useMemo(() => {
    const cutoff = Date.now() - TWENTY_FOUR_HOURS_MS
    return memories.filter(m => new Date(m.created_at).getTime() > cutoff).length
  }, [memories])

  const cards = [
    { key: 'fact', label: 'Facts', count: typeCounts['fact'] ?? 0, filterKey: 'fact', className: 'memory-overview-card--total' },
    { key: 'preference', label: 'Preferences', count: typeCounts['preference'] ?? 0, filterKey: 'preference', className: 'memory-overview-card--important' },
    { key: 'pattern', label: 'Patterns', count: typeCounts['pattern'] ?? 0, filterKey: 'pattern', className: 'memory-overview-card--review' },
    { key: 'context', label: 'Context', count: typeCounts['context'] ?? 0, filterKey: 'context', className: 'memory-overview-card--context' },
    { key: 'recent', label: 'New (24H)', count: recentCount, filterKey: 'recent', className: 'memory-overview-card--recent' },
  ]

  return (
    <div className="memory-overview">
      {cards.map(card => (
        <button
          key={card.key}
          className={`memory-overview-card ${card.className} ${activeFilter === card.filterKey ? 'memory-overview-card--active' : ''}`}
          onClick={() => onFilter(activeFilter === card.filterKey ? null : card.filterKey)}
        >
          <span className="memory-overview-count">{card.count}</span>
          <span className="memory-overview-label">{card.label}</span>
        </button>
      ))}
    </div>
  )
}
