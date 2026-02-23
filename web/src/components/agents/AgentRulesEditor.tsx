import { useState, useEffect, useCallback } from 'react'

interface RuleInfo {
  name: string
  description?: string
}

interface AgentRulesEditorProps {
  definitionId: string
  rules: string[]
  onRulesChange: (rules: string[]) => void
}

export function AgentRulesEditor({ definitionId, rules, onRulesChange }: AgentRulesEditorProps) {
  const [availableRules, setAvailableRules] = useState<RuleInfo[]>([])
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    fetch('/api/rules')
      .then(r => r.json())
      .then(data => {
        const items = (data.rules || []).map((r: { name: string; description?: string }) => ({
          name: r.name,
          description: r.description,
        }))
        setAvailableRules(items)
      })
      .catch(() => setAvailableRules([]))
  }, [])

  const addableRules = availableRules.filter(r => !rules.includes(r.name))

  const handleAdd = useCallback(async (ruleName: string) => {
    try {
      const res = await fetch(`/api/agents/definitions/${definitionId}/rules`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ add: [ruleName] }),
      })
      if (res.ok) {
        const data = await res.json()
        onRulesChange(data.rules || [...rules, ruleName])
      }
    } catch (e) {
      console.error('Failed to add rule:', e)
    }
    setAdding(false)
  }, [definitionId, rules, onRulesChange])

  const handleRemove = useCallback(async (ruleName: string) => {
    try {
      const res = await fetch(`/api/agents/definitions/${definitionId}/rules`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ remove: [ruleName] }),
      })
      if (res.ok) {
        const data = await res.json()
        onRulesChange(data.rules || rules.filter(r => r !== ruleName))
      }
    } catch (e) {
      console.error('Failed to remove rule:', e)
    }
  }, [definitionId, rules, onRulesChange])

  return (
    <div className="agent-rules-editor">
      <div className="agent-rules-chips">
        {rules.map(name => (
          <span key={name} className="agent-rules-chip">
            {name}
            <button
              type="button"
              className="agent-rules-chip-remove"
              onClick={() => handleRemove(name)}
              title={`Remove ${name}`}
            >
              &times;
            </button>
          </span>
        ))}
        {rules.length === 0 && !adding && (
          <span className="agent-rules-empty">No rules assigned</span>
        )}
      </div>
      {adding ? (
        <select
          className="agent-edit-input agent-rules-add-select"
          autoFocus
          value=""
          onChange={e => { if (e.target.value) handleAdd(e.target.value) }}
          onBlur={() => setAdding(false)}
        >
          <option value="">Select rule...</option>
          {addableRules.map(r => (
            <option key={r.name} value={r.name}>{r.name}</option>
          ))}
        </select>
      ) : (
        <button
          type="button"
          className="agent-defs-btn agent-rules-add-btn"
          onClick={() => setAdding(true)}
          disabled={addableRules.length === 0}
        >
          + Add Rule
        </button>
      )}
    </div>
  )
}
