import type { ProjectWithStats } from '../../hooks/useProjects'

interface ProjectOverviewProps {
  projects: ProjectWithStats[]
  totalSessions: number
  totalOpenTasks: number
  activeFilter: string | null
  onFilter: (filter: string | null) => void
}

export function ProjectOverview({ projects, totalSessions, totalOpenTasks, activeFilter, onFilter }: ProjectOverviewProps) {
  const cards = [
    { key: 'total', label: 'Projects', count: projects.length, className: 'projects-overview-card--total' },
    { key: 'active', label: 'Active Sessions', count: totalSessions, className: 'projects-overview-card--sessions' },
    { key: 'tasks', label: 'Open Tasks', count: totalOpenTasks, className: 'projects-overview-card--tasks' },
  ]

  return (
    <div className="projects-overview">
      {cards.map(card => (
        <button
          key={card.key}
          className={`projects-overview-card ${card.className} ${activeFilter === card.key ? 'projects-overview-card--active' : ''}`}
          onClick={() => onFilter(activeFilter === card.key ? null : card.key)}
        >
          <span className="projects-overview-count">{card.count}</span>
          <span className="projects-overview-label">{card.label}</span>
        </button>
      ))}
    </div>
  )
}
