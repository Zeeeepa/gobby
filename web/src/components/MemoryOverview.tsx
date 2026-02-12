import { useMemo } from 'react'
import type { GobbyMemory, MemoryStats } from '../hooks/useMemory'

interface MemoryOverviewProps {
  memories: GobbyMemory[]
  stats: MemoryStats | null
  activeFilter: string | null
  onFilter: (filter: string | null) => void
}

const TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000

export function MemoryOverview({ memories, stats, activeFilter, onFilter }: MemoryOverviewProps) {
  const importantCount = useMemo(
    () => memories.filter(m => m.importance >= 0.7).length,
    [memories]
  )

  const needsReviewCount = useMemo(
    () => memories.filter(m => m.importance < 0.3).length,
    [memories]
  )

  const recentCount = useMemo(() => {
    const cutoff = Date.now() - TWENTY_FOUR_HOURS_MS
    return memories.filter(m => new Date(m.created_at).getTime() > cutoff).length
  }, [memories])

  const cards = [
    { key: 'total', label: 'Total', count: stats?.total_count ?? 0, filterKey: 'total', className: 'memory-overview-card--total' },
    { key: 'important', label: 'Important', count: importantCount, filterKey: 'important', className: 'memory-overview-card--important' },
    { key: 'review', label: 'Needs Review', count: needsReviewCount, filterKey: 'needs_review', className: 'memory-overview-card--review' },
    { key: 'recent', label: 'New (24h)', count: recentCount, filterKey: 'recent', className: 'memory-overview-card--recent' },
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
