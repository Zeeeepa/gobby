import { useState, useRef, useEffect } from 'react'
import type { AgentDefInfo } from '../../hooks/useAgentDefinitions'

interface AgentPickerDropdownProps {
  definitions: AgentDefInfo[]
  globalDefs: AgentDefInfo[]
  projectDefs: AgentDefInfo[]
  showScopeToggle: boolean
  hasGlobal: boolean
  hasProject: boolean
  activeAgent?: string
  onSelect: (agentName: string) => void
  onClose: () => void
  position?: 'above' | 'below'
}

export function AgentPickerDropdown({
  globalDefs,
  projectDefs,
  showScopeToggle,
  hasProject,
  activeAgent,
  onSelect,
  onClose,
  position = 'below',
}: AgentPickerDropdownProps) {
  const [scope, setScope] = useState<'global' | 'project'>(hasProject ? 'project' : 'global')
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose()
      }
    }
    function handleKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('mousedown', handleClick)
    document.addEventListener('keydown', handleKey)
    return () => {
      document.removeEventListener('mousedown', handleClick)
      document.removeEventListener('keydown', handleKey)
    }
  }, [onClose])

  const visibleDefs = scope === 'project' && hasProject ? projectDefs : globalDefs

  return (
    <div
      ref={ref}
      className={`agent-picker-dropdown ${position === 'above' ? 'agent-picker-dropdown--above' : ''}`}
    >
      {showScopeToggle && (
        <div className="agent-picker-scope-toggle">
          <button
            type="button"
            className={`agent-picker-scope-btn ${scope === 'global' ? 'active' : ''}`}
            onClick={() => setScope('global')}
          >
            Global
          </button>
          <button
            type="button"
            className={`agent-picker-scope-btn ${scope === 'project' ? 'active' : ''}`}
            onClick={() => setScope('project')}
          >
            Project
          </button>
        </div>
      )}
      <div className="agent-picker-list">
        {visibleDefs.length === 0 && (
          <div className="agent-picker-empty">No agents</div>
        )}
        {visibleDefs.map((d) => {
          const name = d.definition.name
          const isActive = name === activeAgent
          return (
            <button
              key={`${d.source}-${name}`}
              type="button"
              className={`agent-picker-item ${isActive ? 'agent-picker-item--active' : ''}`}
              onClick={() => {
                onSelect(name)
                onClose()
              }}
            >
              <div className="agent-picker-item-main">
                <AgentIcon />
                <span className="agent-picker-item-name">{name}</span>
                {isActive && <span className="agent-picker-item-check">&#10003;</span>}
              </div>
              {d.definition.description && (
                <div className="agent-picker-item-desc">{d.definition.description}</div>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}

function AgentIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  )
}
