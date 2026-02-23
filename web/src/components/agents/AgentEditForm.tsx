import { useState } from 'react'

export interface AgentFormData {
  name: string
  description: string
  role: string
  goal: string
  personality: string
  instructions: string
  provider: string
  model: string
  mode: string
  isolation: string
  base_branch: string
  timeout: number
  max_turns: number
}

interface AgentEditFormProps {
  form: AgentFormData
  onChange: (form: AgentFormData) => void
  onSave: () => void
  onCancel: () => void
  isEditing: boolean
  providerModels: Record<string, { value: string; label: string }[]>
  saveDisabled?: boolean
}

function FormInput({ label, value, onChange, placeholder, required }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; required?: boolean
}) {
  return (
    <label className="agent-edit-field">
      <span className="agent-edit-label">{label}{required ? ' *' : ''}</span>
      <input
        className="agent-edit-input"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
      />
    </label>
  )
}

function FormSelect({ label, value, onChange, options }: {
  label: string; value: string; onChange: (v: string) => void
  options: { value: string; label: string }[]
}) {
  return (
    <label className="agent-edit-field">
      <span className="agent-edit-label">{label}</span>
      <select className="agent-edit-input" value={value} onChange={e => onChange(e.target.value)}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  )
}

function FormTextarea({ label, value, onChange, placeholder, rows = 3 }: {
  label: string; value: string; onChange: (v: string) => void; placeholder?: string; rows?: number
}) {
  return (
    <label className="agent-edit-field agent-edit-field--wide">
      <span className="agent-edit-label">{label}</span>
      <textarea
        className="agent-edit-input agent-edit-textarea"
        value={value}
        onChange={e => onChange(e.target.value)}
        placeholder={placeholder}
        rows={rows}
      />
    </label>
  )
}

function FormNumber({ label, value, onChange }: {
  label: string; value: number; onChange: (v: number) => void
}) {
  return (
    <label className="agent-edit-field">
      <span className="agent-edit-label">{label}</span>
      <input
        className="agent-edit-input"
        type="number"
        value={value}
        onChange={e => onChange(Number(e.target.value))}
      />
    </label>
  )
}

export function AgentEditForm({ form, onChange, onSave, onCancel, isEditing, providerModels, saveDisabled }: AgentEditFormProps) {
  const [customModelInput, setCustomModelInput] = useState(false)
  const models = providerModels[form.provider]
  const isKnown = models?.some(m => m.value === form.model)
  const showCustomModel = customModelInput || !models || (!isKnown && form.model !== '')

  const set = <K extends keyof AgentFormData>(key: K, value: AgentFormData[K]) =>
    onChange({ ...form, [key]: value })

  return (
    <div className="agent-edit-form">
      <div className="agent-edit-columns">
        {/* Left column: dropdowns */}
        <div className="agent-edit-col-left">
          <FormSelect label="Provider" value={form.provider} onChange={v => {
            const newModels = providerModels[v]
            const valid = newModels?.some(m => m.value === form.model)
            setCustomModelInput(false)
            onChange({ ...form, provider: v, model: valid ? form.model : '' })
          }} options={[
            { value: 'claude', label: 'Claude' },
            { value: 'gemini', label: 'Gemini' },
            { value: 'codex', label: 'Codex' },
            { value: 'cursor', label: 'Cursor' },
          ]} />

          <label className="agent-edit-field">
            <span className="agent-edit-label">Model</span>
            {showCustomModel ? (
              <div className="agent-edit-model-field">
                <input
                  className="agent-edit-input"
                  value={form.model}
                  onChange={e => set('model', e.target.value)}
                  placeholder="e.g. claude-sonnet-4-5-20250929"
                  autoFocus={customModelInput}
                />
                {models && (
                  <button type="button" className="agent-edit-model-toggle" onClick={() => { setCustomModelInput(false); set('model', '') }}>&times;</button>
                )}
              </div>
            ) : (
              <select className="agent-edit-input" value={form.model} onChange={e => {
                if (e.target.value === '__custom__') { setCustomModelInput(true); set('model', '') }
                else set('model', e.target.value)
              }}>
                {models?.map(m => <option key={m.value} value={m.value}>{m.label}</option>)}
                <option value="__custom__">Custom...</option>
              </select>
            )}
          </label>

          <FormSelect label="Mode" value={form.mode} onChange={v => set('mode', v)} options={[
            { value: 'headless', label: 'Headless' },
            { value: 'terminal', label: 'Terminal' },
            { value: 'embedded', label: 'Embedded' },
          ]} />

          <FormSelect label="Isolation" value={form.isolation} onChange={v => set('isolation', v)} options={[
            { value: '', label: 'None' },
            { value: 'none', label: 'None (explicit)' },
            { value: 'worktree', label: 'Worktree' },
            { value: 'clone', label: 'Clone' },
          ]} />

          <FormInput label="Base branch" value={form.base_branch} onChange={v => set('base_branch', v)} placeholder="main" />
          <FormNumber label="Timeout (s)" value={form.timeout} onChange={v => set('timeout', v)} />
          <FormNumber label="Max turns" value={form.max_turns} onChange={v => set('max_turns', v)} />
        </div>

        {/* Right column: text fields */}
        <div className="agent-edit-col-right">
          <FormInput label="Name" value={form.name} onChange={v => set('name', v)} placeholder="my-agent" required />
          <FormInput label="Description" value={form.description} onChange={v => set('description', v)} placeholder="What this agent does..." />
          <FormInput label="Role" value={form.role} onChange={v => set('role', v)} placeholder="e.g. Senior security engineer" />
          <FormInput label="Goal" value={form.goal} onChange={v => set('goal', v)} placeholder="What success looks like..." />
          <FormInput label="Personality" value={form.personality} onChange={v => set('personality', v)} placeholder="Communication style, tone..." />
          <FormTextarea label="Instructions" value={form.instructions} onChange={v => set('instructions', v)} placeholder="Detailed rules, constraints, approach..." rows={4} />
        </div>
      </div>

      <div className="agent-edit-actions">
        <button className="agent-defs-btn" onClick={onCancel}>Cancel</button>
        <button
          className="agent-defs-btn agent-defs-btn--primary"
          onClick={onSave}
          disabled={saveDisabled}
        >
          {isEditing ? 'Save' : 'Create'}
        </button>
      </div>
    </div>
  )
}
