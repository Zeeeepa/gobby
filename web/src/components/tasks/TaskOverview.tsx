import { useMemo } from 'react'
import type { GobbyTask, TaskStats } from '../../hooks/useTasks'

// =============================================================================
// Constants
// =============================================================================

const COMPLETED_STATUSES = new Set(['closed'])
const TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000

// =============================================================================
// TaskOverview
// =============================================================================

interface TaskOverviewProps {
  tasks: GobbyTask[]
  stats: TaskStats
  activeFilter: string | null
  onFilterStatus: (status: string | null) => void
}

export function TaskOverview({ tasks, stats, activeFilter, onFilterStatus }: TaskOverviewProps) {
  const nowCount = stats['in_progress'] || 0
  const stuckCount = (stats['escalated'] || 0)
  const reviewCount = (stats['needs_review'] || 0) + (stats['approved'] || 0)
  const recentlyCompleted = useMemo(() => {
    const cutoff = Date.now() - TWENTY_FOUR_HOURS_MS
    return tasks.filter(
      t => COMPLETED_STATUSES.has(t.status) && new Date(t.updated_at).getTime() > cutoff
    ).length
  }, [tasks])

  const cards = [
    {
      key: 'now',
      label: 'Now',
      count: nowCount,
      filterStatus: 'in_progress',
      className: 'task-overview-card--now',
    },
    {
      key: 'review',
      label: 'In Review',
      count: reviewCount,
      filterStatus: 'in_review',
      className: 'task-overview-card--review',
    },
    {
      key: 'stuck',
      label: 'Stuck',
      count: stuckCount,
      filterStatus: 'escalated',
      className: 'task-overview-card--stuck',
    },
    {
      key: 'recent',
      label: 'Recently Done',
      count: recentlyCompleted,
      filterStatus: 'recently_done',
      className: 'task-overview-card--recent',
    },
  ]

  return (
    <div className="task-overview">
      {cards.map(card => (
        <button
          key={card.key}
          className={`task-overview-card ${card.className} ${activeFilter === card.filterStatus ? 'task-overview-card--active' : ''}`}
          onClick={() => onFilterStatus(activeFilter === card.filterStatus ? null : card.filterStatus)}
        >
          <span className="task-overview-count">{card.count}</span>
          <span className="task-overview-label">{card.label}</span>
        </button>
      ))}
    </div>
  )
}
