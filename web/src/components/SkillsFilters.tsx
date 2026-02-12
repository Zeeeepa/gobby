import type { SkillStats } from '../hooks/useSkills'

interface SkillsFiltersProps {
  stats: SkillStats | null
  category: string | null
  sourceType: string | null
  onCategoryChange: (cat: string | null) => void
  onSourceTypeChange: (st: string | null) => void
  onClear: () => void
}

export function SkillsFilters({ stats, category, sourceType, onCategoryChange, onSourceTypeChange, onClear }: SkillsFiltersProps) {
  const categories = stats?.by_category ? Object.keys(stats.by_category).sort() : []
  const sourceTypes = stats?.by_source_type ? Object.keys(stats.by_source_type).sort() : []
  const hasFilters = category !== null || sourceType !== null

  return (
    <div className="skills-filters">
      <div className="skills-filters-chips">
        {categories.map(cat => (
          <button
            key={cat}
            className={`skills-category-chip ${category === cat ? 'skills-category-chip--active' : ''}`}
            onClick={() => onCategoryChange(category === cat ? null : cat)}
          >
            {cat}
            {stats?.by_category[cat] != null && (
              <span className="skills-category-chip-count">{stats.by_category[cat]}</span>
            )}
          </button>
        ))}
      </div>

      <div className="skills-filters-selects">
        <select
          className="skills-filter-select"
          value={sourceType || ''}
          onChange={e => onSourceTypeChange(e.target.value || null)}
        >
          <option value="">All Sources</option>
          {sourceTypes.map(st => (
            <option key={st} value={st}>{st}</option>
          ))}
        </select>

        {hasFilters && (
          <button className="skills-clear-filters" onClick={onClear}>
            Clear filters
          </button>
        )}
      </div>
    </div>
  )
}
