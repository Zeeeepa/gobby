import type { GobbySkill } from '../hooks/useSkills'

interface SkillsTableProps {
  skills: GobbySkill[]
  onSelect: (skill: GobbySkill) => void
  onToggle: (skillId: string, enabled: boolean) => void
  onEdit: (skill: GobbySkill) => void
  onDelete: (skillId: string) => void
}

function SourceBadge({ sourceType }: { sourceType: string | null }) {
  const st = sourceType || 'unknown'
  return <span className={`skills-source-badge skills-source-badge--${st}`}>{st}</span>
}

export function SkillsTable({ skills, onSelect, onToggle, onEdit, onDelete }: SkillsTableProps) {
  if (skills.length === 0) {
    return (
      <div className="skills-empty">
        <p>No skills found</p>
      </div>
    )
  }

  return (
    <div className="skills-table">
      {skills.map(skill => (
        <div
          key={skill.id}
          className="skills-row"
          onClick={() => onSelect(skill)}
        >
          <div className="skills-row-toggle" onClick={e => e.stopPropagation()}>
            <label className="skills-toggle">
              <input
                type="checkbox"
                checked={skill.enabled}
                onChange={() => onToggle(skill.id, !skill.enabled)}
              />
              <span className="skills-toggle-slider" />
            </label>
          </div>

          <div className="skills-row-info">
            <div className="skills-row-header">
              <span className="skills-row-name">{skill.name}</span>
              {skill.always_apply && <span className="skills-badge skills-badge--always">always</span>}
              <SourceBadge sourceType={skill.source_type} />
              {skill.version && <span className="skills-badge skills-badge--version">v{skill.version}</span>}
            </div>
            <div className="skills-row-description">{skill.description}</div>
          </div>

          <div className="skills-row-actions" onClick={e => e.stopPropagation()}>
            <button
              className="skills-action-btn"
              title="Edit"
              onClick={() => onEdit(skill)}
            >
              <EditIcon />
            </button>
            <button
              className="skills-action-btn skills-action-btn--danger"
              title="Delete"
              onClick={() => onDelete(skill.id)}
            >
              <DeleteIcon />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}

function EditIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
      <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
    </svg>
  )
}

function DeleteIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  )
}
