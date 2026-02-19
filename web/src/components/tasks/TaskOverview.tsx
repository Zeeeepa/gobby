import type { GobbyTask, TaskStats } from '../../hooks/useTasks'

// =============================================================================
// TaskOverview
// =============================================================================

interface TaskOverviewProps {
  tasks: GobbyTask[]
  stats: TaskStats
  activeFilter: string | null
  onFilterStatus: (status: string | null) => void
}

export function TaskOverview({ stats, activeFilter, onFilterStatus }: TaskOverviewProps) {
  const openCount = stats['open'] || 0
  const inProgressCount = stats['in_progress'] || 0
  const reviewCount = (stats['needs_review'] || 0) + (stats['review_approved'] || 0)
  const escalatedCount = stats['escalated'] || 0
  const closedCount = stats['closed'] || 0

  const cards = [
    {
      key: 'open',
      label: 'Open',
      count: openCount,
      filterStatus: 'open',
      className: 'task-overview-card--now',
    },
    {
      key: 'in_progress',
      label: 'In Progress',
      count: inProgressCount,
      filterStatus: 'in_progress',
      className: 'task-overview-card--review',
    },
    {
      key: 'review',
      label: 'Needs Review',
      count: reviewCount,
      filterStatus: 'in_review',
      className: 'task-overview-card--stuck',
    },
    {
      key: 'escalated',
      label: 'Escalated',
      count: escalatedCount,
      filterStatus: 'escalated',
      className: 'task-overview-card--stuck',
    },
    {
      key: 'closed',
      label: 'Closed',
      count: closedCount,
      filterStatus: 'closed',
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
