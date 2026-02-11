import { useState, useCallback } from 'react'

// =============================================================================
// Types
// =============================================================================

type OversightMode = 'hands_off' | 'ask_risky' | 'ask_each'

interface OversightOption {
  value: OversightMode
  label: string
  description: string
  icon: string
}

const OPTIONS: OversightOption[] = [
  {
    value: 'hands_off',
    label: 'Hands-off',
    description: 'Full autonomy - agent works independently',
    icon: '\u26A1',
  },
  {
    value: 'ask_risky',
    label: 'Ask before risky',
    description: 'Pause on destructive or high-risk actions',
    icon: '\u26A0',
  },
  {
    value: 'ask_each',
    label: 'Ask each step',
    description: 'Require approval before every action',
    icon: '\u2705',
  },
]

const STORAGE_PREFIX = 'gobby-oversight-'

function getStoredMode(taskId: string): OversightMode {
  try {
    const stored = localStorage.getItem(`${STORAGE_PREFIX}${taskId}`)
    if (stored && OPTIONS.some(o => o.value === stored)) return stored as OversightMode
  } catch {
    // localStorage unavailable
  }
  return 'ask_risky' // sensible default
}

function storeMode(taskId: string, mode: OversightMode) {
  try {
    localStorage.setItem(`${STORAGE_PREFIX}${taskId}`, mode)
  } catch {
    // localStorage unavailable
  }
}

// =============================================================================
// OversightSelector
// =============================================================================

interface OversightSelectorProps {
  taskId: string
}

export function OversightSelector({ taskId }: OversightSelectorProps) {
  const [mode, setMode] = useState<OversightMode>(() => getStoredMode(taskId))
  const [showDetails, setShowDetails] = useState(false)

  const handleChange = useCallback((newMode: OversightMode) => {
    setMode(newMode)
    storeMode(taskId, newMode)
  }, [taskId])

  const current = OPTIONS.find(o => o.value === mode)!

  return (
    <div className="oversight-selector">
      <div className="oversight-selector-header">
        <span className="oversight-selector-label">Oversight</span>
        <button
          className="oversight-selector-info"
          onClick={() => setShowDetails(!showDetails)}
          title="What is oversight mode?"
        >
          ?
        </button>
      </div>

      {showDetails && (
        <div className="oversight-selector-help">
          Controls how much autonomy the agent has when working on this task.
        </div>
      )}

      <div className="oversight-selector-options">
        {OPTIONS.map(opt => (
          <button
            key={opt.value}
            className={`oversight-option ${mode === opt.value ? 'oversight-option--active' : ''}`}
            onClick={() => handleChange(opt.value)}
            aria-pressed={mode === opt.value}
            title={opt.description}
          >
            <span className="oversight-option-icon">{opt.icon}</span>
            <span className="oversight-option-label">{opt.label}</span>
          </button>
        ))}
      </div>

      <div className="oversight-selector-desc">{current.description}</div>
    </div>
  )
}
