import type { SkillStats } from '../hooks/useSkills'

interface SkillsOverviewProps {
  stats: SkillStats | null
  activeFilter: string | null
  onFilter: (filter: string | null) => void
}

export function SkillsOverview({ stats, activeFilter, onFilter }: SkillsOverviewProps) {
  const cards = [
    { key: 'total', label: 'Total', count: stats?.total ?? 0, className: 'skills-overview-card--total' },
    { key: 'enabled', label: 'Enabled', count: stats?.enabled ?? 0, className: 'skills-overview-card--enabled' },
    { key: 'bundled', label: 'Bundled', count: stats?.bundled ?? 0, className: 'skills-overview-card--bundled' },
    { key: 'hubs', label: 'From Hubs', count: stats?.from_hubs ?? 0, className: 'skills-overview-card--hubs' },
  ]

  return (
    <div className="skills-overview">
      {cards.map(card => (
        <button
          key={card.key}
          className={`skills-overview-card ${card.className} ${activeFilter === card.key ? 'skills-overview-card--active' : ''}`}
          onClick={() => onFilter(activeFilter === card.key ? null : card.key)}
        >
          <span className="skills-overview-count">{card.count}</span>
          <span className="skills-overview-label">{card.label}</span>
        </button>
      ))}
    </div>
  )
}
