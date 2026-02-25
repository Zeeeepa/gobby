import { useState } from 'react'
import { CodeMirrorEditor } from '../CodeMirrorEditor'
import { AgentRulesEditor } from './AgentRulesEditor'
import { AgentVariablesEditor } from './AgentVariablesEditor'

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
  editingId?: string | null
  branches?: string[]
  isGitProject?: boolean
  rules?: string[]
  onRulesChange?: (rules: string[]) => void
  variables?: Record<string, unknown>
  onVariablesChange?: (variables: Record<string, unknown>) => void
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

function FormSelect({ label, value, onChange, options, disabled }: {
  label: string; value: string; onChange: (v: string) => void
  options: { value: string; label: string }[]
  disabled?: boolean
}) {
  return (
    <label className={`agent-edit-field${disabled ? ' agent-edit-field--disabled' : ''}`}>
      <span className="agent-edit-label">{label}</span>
      <select className="agent-edit-input" value={value} onChange={e => onChange(e.target.value)} disabled={disabled}>
        {options.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
    </label>
  )
}

function FormNumber({ label, value, onChange, hint }: {
  label: string; value: number; onChange: (v: number) => void; hint?: string
}) {
  return (
    <label className="agent-edit-field">
      <span className="agent-edit-label">
        {label}
        {hint && <span className="agent-edit-hint">{hint}</span>}
      </span>
      <input
        className="agent-edit-input"
        type="number"
        min={0}
        value={value}
        onChange={e => onChange(Number(e.target.value))}
      />
    </label>
  )
}

export function AgentEditForm({
  form, onChange, onSave, onCancel, isEditing, providerModels, saveDisabled,
  editingId, branches = [], isGitProject = true,
  rules, onRulesChange, variables, onVariablesChange,
}: AgentEditFormProps) {
  const [customModelInput, setCustomModelInput] = useState(false)
  const [customBranchInput, setCustomBranchInput] = useState(false)

  const isInheritProvider = form.provider === 'inherit'
  const models = isInheritProvider ? [{ value: '', label: '(default)' }] : providerModels[form.provider]
  const isKnown = models?.some(m => m.value === form.model)
  const showCustomModel = !isInheritProvider && (customModelInput || !models || (!isKnown && form.model !== ''))

  const branchKnown = form.base_branch === 'inherit' || branches.includes(form.base_branch)
  const showCustomBranch = isGitProject && (customBranchInput || (!branchKnown && form.base_branch !== ''))

  const set = <K extends keyof AgentFormData>(key: K, value: AgentFormData[K]) =>
    onChange({ ...form, [key]: value })

  return (
    <div className="agent-edit-form">
      <div className="agent-edit-columns">
        {/* Left column: dropdowns */}
        <div className="agent-edit-col-left">
          <FormSelect label="Provider" value={form.provider} onChange={v => {
            if (v === 'inherit') {
              setCustomModelInput(false)
              onChange({ ...form, provider: v, model: '' })
            } else {
              const newModels = providerModels[v]
              const valid = newModels?.some(m => m.value === form.model)
              setCustomModelInput(false)
              onChange({ ...form, provider: v, model: valid ? form.model : '' })
            }
          }} options={[
            { value: 'inherit', label: 'Inherit' },
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
                {!isInheritProvider && <option value="__custom__">Custom...</option>}
              </select>
            )}
          </label>

          <FormSelect label="Mode" value={form.mode} onChange={v => set('mode', v)} options={[
            { value: 'self', label: 'Self (inherit)' },
            { value: 'headless', label: 'Headless' },
            { value: 'terminal', label: 'Terminal' },
            { value: 'embedded', label: 'Embedded' },
          ]} />

          <FormSelect
            label="Isolation"
            value={isGitProject ? form.isolation : ''}
            onChange={v => set('isolation', v)}
            options={[
              { value: '', label: 'None' },
              { value: 'none', label: 'None (explicit)' },
              { value: 'worktree', label: 'Worktree' },
              { value: 'clone', label: 'Clone' },
            ]}
            disabled={!isGitProject}
          />

          <label className={`agent-edit-field${!isGitProject ? ' agent-edit-field--disabled' : ''}`}>
            <span className="agent-edit-label">Base branch</span>
            {!isGitProject ? (
              <select className="agent-edit-input" disabled value="inherit">
                <option value="inherit">Inherit</option>
              </select>
            ) : showCustomBranch ? (
              <div className="agent-edit-model-field">
                <input
                  className="agent-edit-input"
                  value={form.base_branch}
                  onChange={e => set('base_branch', e.target.value)}
                  placeholder="branch name"
                  autoFocus={customBranchInput}
                />
                <button type="button" className="agent-edit-model-toggle" onClick={() => { setCustomBranchInput(false); set('base_branch', 'inherit') }}>&times;</button>
              </div>
            ) : (
              <select className="agent-edit-input" value={form.base_branch} onChange={e => {
                if (e.target.value === '__custom__') { setCustomBranchInput(true); set('base_branch', '') }
                else set('base_branch', e.target.value)
              }}>
                <option value="inherit">Inherit</option>
                {branches.map(b => <option key={b} value={b}>{b}</option>)}
                <option value="__custom__">Custom...</option>
              </select>
            )}
          </label>

          <FormNumber label="Timeout (s)" value={form.timeout} onChange={v => set('timeout', v)} hint="0 = unlimited" />
          <FormNumber label="Max turns" value={form.max_turns} onChange={v => set('max_turns', v)} hint="0 = unlimited" />
        </div>

        {/* Right column: text fields */}
        <div className="agent-edit-col-right">
          <FormInput label="Name" value={form.name} onChange={v => set('name', v)} placeholder="my-agent" required />
          <FormInput label="Description" value={form.description} onChange={v => set('description', v)} placeholder="What this agent does..." />
          <FormInput label="Role" value={form.role} onChange={v => set('role', v)} placeholder="e.g. Senior security engineer" />
          <FormInput label="Goal" value={form.goal} onChange={v => set('goal', v)} placeholder="What success looks like..." />
          <FormInput label="Personality" value={form.personality} onChange={v => set('personality', v)} placeholder="Communication style, tone..." />
          <div className="agent-edit-field agent-edit-field--wide">
            <span className="agent-edit-label">Instructions</span>
            <div className="agent-edit-codemirror">
              <CodeMirrorEditor
                content={form.instructions}
                language="markdown"
                onChange={v => set('instructions', v)}
              />
            </div>
          </div>
        </div>
      </div>

      {/* Rules & Variables editors — only for existing DB agents */}
      {editingId && onRulesChange && rules !== undefined && (
        <div className="agent-edit-section">
          <span className="agent-edit-label">Rules</span>
          <AgentRulesEditor
            definitionId={editingId}
            rules={rules}
            onRulesChange={onRulesChange}
          />
        </div>
      )}
      {editingId && onVariablesChange && variables !== undefined && (
        <div className="agent-edit-section">
          <span className="agent-edit-label">Variables</span>
          <AgentVariablesEditor
            definitionId={editingId}
            variables={variables}
            onVariablesChange={onVariablesChange}
          />
        </div>
      )}

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
