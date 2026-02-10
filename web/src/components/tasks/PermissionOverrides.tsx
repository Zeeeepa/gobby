import { useState, useCallback, useEffect } from 'react'

// =============================================================================
// Types
// =============================================================================

interface PermissionRule {
  id: string
  label: string
  description: string
  icon: string
  category: 'tools' | 'access' | 'network'
  default: boolean
}

interface PermissionOverridesState {
  rules: Record<string, boolean>
  fileScope: string
}

// =============================================================================
// Constants
// =============================================================================

const PERMISSION_RULES: PermissionRule[] = [
  {
    id: 'file_edit',
    label: 'File Editing',
    description: 'Allow Edit, Write, and NotebookEdit tools',
    icon: '\u270E',
    category: 'tools',
    default: true,
  },
  {
    id: 'shell',
    label: 'Shell Access',
    description: 'Allow Bash command execution',
    icon: '\u25B6',
    category: 'tools',
    default: true,
  },
  {
    id: 'git_write',
    label: 'Git Write',
    description: 'Allow git push, branch, commit operations',
    icon: '\u2B61',
    category: 'tools',
    default: true,
  },
  {
    id: 'mcp_tools',
    label: 'MCP Tools',
    description: 'Allow calling tools on MCP servers',
    icon: '\u2699',
    category: 'tools',
    default: true,
  },
  {
    id: 'network',
    label: 'Network Access',
    description: 'Allow web fetch and external API calls',
    icon: '\u21C5',
    category: 'network',
    default: true,
  },
  {
    id: 'spawn_agents',
    label: 'Spawn Agents',
    description: 'Allow spawning sub-agents and terminals',
    icon: '\u2234',
    category: 'access',
    default: true,
  },
]

const STORAGE_KEY = 'gobby-perm-overrides-'

const CATEGORIES: { key: string; label: string }[] = [
  { key: 'tools', label: 'Tool Access' },
  { key: 'network', label: 'Network' },
  { key: 'access', label: 'Orchestration' },
]

// =============================================================================
// Helpers
// =============================================================================

function getStoredOverrides(taskId: string): PermissionOverridesState {
  try {
    const raw = localStorage.getItem(`${STORAGE_KEY}${taskId}`)
    if (raw) return JSON.parse(raw)
  } catch { /* noop */ }
  return { rules: {}, fileScope: '' }
}

function storeOverrides(taskId: string, state: PermissionOverridesState) {
  try {
    localStorage.setItem(`${STORAGE_KEY}${taskId}`, JSON.stringify(state))
  } catch { /* noop */ }
}

function hasOverrides(state: PermissionOverridesState): boolean {
  const hasRuleOverrides = Object.entries(state.rules).some(([id, val]) => {
    const rule = PERMISSION_RULES.find(r => r.id === id)
    return rule && val !== rule.default
  })
  return hasRuleOverrides || state.fileScope.trim().length > 0
}

// =============================================================================
// PermissionOverrides
// =============================================================================

interface PermissionOverridesProps {
  taskId: string
}

export function PermissionOverrides({ taskId }: PermissionOverridesProps) {
  const [state, setState] = useState<PermissionOverridesState>(() => getStoredOverrides(taskId))
  const [expanded, setExpanded] = useState(false)

  // Re-load when taskId changes
  useEffect(() => {
    setState(getStoredOverrides(taskId))
  }, [taskId])

  const toggleRule = useCallback((ruleId: string) => {
    setState(prev => {
      const rule = PERMISSION_RULES.find(r => r.id === ruleId)
      if (!rule) return prev
      const current = prev.rules[ruleId] ?? rule.default
      const next = { ...prev, rules: { ...prev.rules, [ruleId]: !current } }
      storeOverrides(taskId, next)
      return next
    })
  }, [taskId])

  const setFileScope = useCallback((value: string) => {
    setState(prev => {
      const next = { ...prev, fileScope: value }
      storeOverrides(taskId, next)
      return next
    })
  }, [taskId])

  const resetAll = useCallback(() => {
    const fresh: PermissionOverridesState = { rules: {}, fileScope: '' }
    setState(fresh)
    storeOverrides(taskId, fresh)
  }, [taskId])

  const overrideCount = Object.entries(state.rules).filter(([id, val]) => {
    const rule = PERMISSION_RULES.find(r => r.id === id)
    return rule && val !== rule.default
  }).length + (state.fileScope.trim() ? 1 : 0)

  const active = hasOverrides(state)

  return (
    <div className="perm-overrides">
      <button
        className="perm-overrides-header"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="perm-overrides-toggle-icon">{expanded ? '\u25BE' : '\u25B8'}</span>
        <span className="perm-overrides-label">Permission Overrides</span>
        {active ? (
          <span className="perm-overrides-badge perm-overrides-badge--active">
            {overrideCount} override{overrideCount !== 1 ? 's' : ''}
          </span>
        ) : (
          <span className="perm-overrides-badge">defaults</span>
        )}
      </button>

      {expanded && (
        <div className="perm-overrides-body">
          {CATEGORIES.map(cat => {
            const rules = PERMISSION_RULES.filter(r => r.category === cat.key)
            if (rules.length === 0) return null
            return (
              <div key={cat.key} className="perm-overrides-category">
                <div className="perm-overrides-category-label">{cat.label}</div>
                {rules.map(rule => {
                  const enabled = state.rules[rule.id] ?? rule.default
                  const isOverridden = enabled !== rule.default
                  return (
                    <div
                      key={rule.id}
                      className={`perm-overrides-rule ${isOverridden ? 'perm-overrides-rule--overridden' : ''}`}
                    >
                      <div className="perm-overrides-rule-info">
                        <span className="perm-overrides-rule-icon">{rule.icon}</span>
                        <div className="perm-overrides-rule-text">
                          <span className="perm-overrides-rule-label">{rule.label}</span>
                          <span className="perm-overrides-rule-desc">{rule.description}</span>
                        </div>
                      </div>
                      <button
                        className={`perm-toggle ${enabled ? 'perm-toggle--on' : 'perm-toggle--off'}`}
                        onClick={() => toggleRule(rule.id)}
                        title={enabled ? 'Disable' : 'Enable'}
                        role="switch"
                        aria-checked={enabled}
                      >
                        <span className="perm-toggle-track">
                          <span className="perm-toggle-thumb" />
                        </span>
                      </button>
                    </div>
                  )
                })}
              </div>
            )
          })}

          {/* File scope restriction */}
          <div className="perm-overrides-category">
            <div className="perm-overrides-category-label">File Scope</div>
            <div className="perm-overrides-file-scope">
              <input
                type="text"
                className="perm-overrides-file-input"
                value={state.fileScope}
                onChange={e => setFileScope(e.target.value)}
                placeholder="e.g. src/components/**, tests/**"
              />
              <span className="perm-overrides-file-hint">
                Restrict file access to matching glob patterns (comma-separated)
              </span>
            </div>
          </div>

          {/* Reset */}
          {active && (
            <button className="perm-overrides-reset" onClick={resetAll}>
              Reset to defaults
            </button>
          )}
        </div>
      )}
    </div>
  )
}
