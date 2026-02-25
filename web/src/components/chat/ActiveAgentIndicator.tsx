import { useState } from 'react'
import { AgentPickerDropdown } from './AgentPickerDropdown'
import type { AgentDefInfo } from '../../hooks/useAgentDefinitions'

interface ActiveAgentIndicatorProps {
  agentName: string
  onAgentChange: (agentName: string) => void
  definitions: AgentDefInfo[]
  globalDefs: AgentDefInfo[]
  projectDefs: AgentDefInfo[]
  showScopeToggle: boolean
  hasGlobal: boolean
  hasProject: boolean
}

export function ActiveAgentIndicator({
  agentName,
  onAgentChange,
  definitions,
  globalDefs,
  projectDefs,
  showScopeToggle,
  hasGlobal,
  hasProject,
}: ActiveAgentIndicatorProps) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <>
      <button
        type="button"
        className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors active-agent-indicator"
        onClick={() => setIsOpen(!isOpen)}
        title={`Active agent: ${agentName}`}
      >
        <AgentIcon />
        <span className="active-agent-name">{agentName}</span>
      </button>
      {isOpen && (
        <AgentPickerDropdown
          definitions={definitions}
          globalDefs={globalDefs}
          projectDefs={projectDefs}
          showScopeToggle={showScopeToggle}
          hasGlobal={hasGlobal}
          hasProject={hasProject}
          activeAgent={agentName}
          onSelect={onAgentChange}
          onClose={() => setIsOpen(false)}
        />
      )}
    </>
  )
}

function AgentIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  )
}
