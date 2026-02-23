import { useState, useEffect, useCallback, useMemo } from 'react'
import * as yaml from 'js-yaml'
import { useAgentRuns } from '../hooks/useAgentRuns'
import type { RunningAgent, AgentRun } from '../hooks/useAgentRuns'
import { YamlEditorModal } from './WorkflowsPage'

// =============================================================================
// Types
// =============================================================================

interface AgentDefInfo {
  definition: {
    name: string
    description: string | null
    role: string | null
    goal: string | null
    personality: string | null
    instructions: string | null
    provider: string
    model: string | null
    mode: string
    terminal: string
    isolation: string | null
    base_branch: string
    timeout: number
    max_turns: number
    default_workflow: string | null
    sandbox: Record<string, unknown> | null
    skill_profile: Record<string, unknown> | null
    workflows: Record<string, WorkflowSummary> | null
    lifecycle_variables: Record<string, unknown>
    default_variables: Record<string, unknown>
  }
  source: string
  source_path: string | null
  db_id: string | null
  overridden_by: string | null
  deleted_at: string | null
}

interface WorkflowSummary {
  file?: string
  type?: string
  description?: string
  mode?: string
  internal?: boolean
  step_count?: number
}

interface CreateFormData {
  name: string
  description: string
  role: string
  goal: string
  personality: string
  instructions: string
  provider: string
  model: string
  mode: string
  terminal: string
  isolation: string
  base_branch: string
  timeout: number
  max_turns: number
}

// =============================================================================
// Constants
// =============================================================================

const SOURCE_LABELS: Record<string, string> = {
  'project-file': 'Project',
  'user-file': 'User',
  'built-in-file': 'Built-in',
  'project-db': 'Project DB',
  'global-db': 'Global DB',
}

const PROVIDER_COLORS: Record<string, string> = {
  claude: '#6366f1',
  gemini: '#a855f7',
  codex: '#22c55e',
  cursor: '#3b82f6',
  windsurf: '#14b8a6',
  copilot: '#f97316',
}

const MODE_COLORS: Record<string, string> = {
  terminal: '#f59e0b',
  headless: '#6b7280',
  embedded: '#06b6d4',
  self: '#ec4899',
}

const STATUS_COLORS: Record<string, string> = {
  running: '#3b82f6',
  pending: '#f59e0b',
  success: '#10b981',
  error: '#ef4444',
  timeout: '#f97316',
  cancelled: '#6b7280',
}

const ISOLATION_COLORS: Record<string, string> = {
  clone: '#ef4444',
  worktree: '#eab308',
  current: '#6b7280',
}

const PROVIDER_MODELS: Record<string, { value: string; label: string }[]> = {
  claude: [
    { value: '', label: '(default)' },
    { value: 'opus', label: 'Opus' },
    { value: 'sonnet', label: 'Sonnet' },
    { value: 'haiku', label: 'Haiku' },
  ],
  gemini: [
    { value: '', label: '(default)' },
    { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
    { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
    { value: 'gemini-2.0-flash', label: 'Gemini 2.0 Flash' },
  ],
  codex: [
    { value: '', label: '(default)' },
    { value: 'gpt-4o', label: 'GPT-4o' },
    { value: 'o3', label: 'o3' },
    { value: 'o4-mini', label: 'o4-mini' },
  ],
  cursor: [
    { value: '', label: '(default)' },
  ],
  windsurf: [
    { value: '', label: '(default)' },
  ],
  copilot: [
    { value: '', label: '(default)' },
  ],
}

function getBaseUrl(): string {
  return ''
}

// =============================================================================
// Component
// =============================================================================

interface AgentDefinitionsPageProps {
  searchText: string
  sourceFilter: 'installed' | 'templates' | 'deleted'
  devMode: boolean
  showCreateForm: boolean
  onToggleCreateForm: (show: boolean) => void
}

export function AgentDefinitionsPage({ searchText, sourceFilter, devMode, showCreateForm, onToggleCreateForm }: AgentDefinitionsPageProps) {
  const { running, recentRuns, cancelAgent } = useAgentRuns()
  const [definitions, setDefinitions] = useState<AgentDefInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [showRecentRuns, setShowRecentRuns] = useState(false)
  const [customModelInput, setCustomModelInput] = useState(false)
  const [expandedName, setExpandedName] = useState<string | null>(null)
  const [filterSource, setFilterSource] = useState<string>('all')
  const [filterProvider, setFilterProvider] = useState<string>('all')
  const [editingId, setEditingId] = useState<string | null>(null)
  const [importingName, setImportingName] = useState<string | null>(null)
  const [importResult, setImportResult] = useState<{ name: string; ok: boolean } | null>(null)
  const [toastMessage, setToastMessage] = useState<{ text: string; type: 'success' | 'error' } | null>(null)

  // YAML editor state
  const [yamlAgent, setYamlAgent] = useState<AgentDefInfo | null>(null)
  const [yamlContent, setYamlContent] = useState('')
  const [yamlLoading, setYamlLoading] = useState(false)

  const showToast = useCallback((text: string, type: 'success' | 'error') => {
    setToastMessage({ text, type })
    setTimeout(() => setToastMessage(null), 4000)
  }, [])

  const [createForm, setCreateForm] = useState<CreateFormData>({
    name: '', description: '', role: '', goal: '', personality: '', instructions: '',
    provider: 'claude', model: '', mode: 'headless', terminal: 'auto', isolation: '',
    base_branch: 'main', timeout: 120, max_turns: 10,
  })

  const fetchDefinitions = useCallback(async (includeDeleted = false) => {
    setLoading(true)
    try {
      const params = includeDeleted ? '?include_deleted=true' : ''
      const res = await fetch(`${getBaseUrl()}/api/agents/definitions${params}`)
      const data = await res.json()
      if (data.status === 'success') {
        setDefinitions(data.definitions)
      }
    } catch (e) {
      console.error('Failed to fetch agent definitions:', e)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchDefinitions(true) }, [fetchDefinitions])

  // Clear editing state when form closes; reset form when opening for create
  useEffect(() => {
    if (!showCreateForm) {
      setEditingId(null)
    } else if (!editingId) {
      setCreateForm({
        name: '', description: '', role: '', goal: '', personality: '', instructions: '',
        provider: 'claude', model: '', mode: 'headless', terminal: 'auto', isolation: '',
        base_branch: 'main', timeout: 120, max_turns: 10,
      })
    }
  }, [showCreateForm, editingId])

  const [providerModels, setProviderModels] = useState(PROVIDER_MODELS)

  useEffect(() => {
    fetch(`${getBaseUrl()}/admin/models`)
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data) setProviderModels(prev => ({ ...prev, ...data }))
      })
      .catch(e => console.error('Failed to fetch model list:', e))
  }, [])

  const filtered = useMemo(() => definitions.filter(d => {
    // Source filter (exclusive)
    if (sourceFilter === 'installed') {
      if (d.source === 'template' || d.deleted_at) return false
    } else if (sourceFilter === 'templates') {
      if (d.source !== 'template' || d.deleted_at) return false
    } else if (sourceFilter === 'deleted') {
      if (!d.deleted_at) return false
    }

    if (filterSource !== 'all' && d.source !== filterSource) return false
    if (filterProvider !== 'all' && d.definition.provider !== filterProvider) return false
    if (searchText.trim()) {
      const q = searchText.toLowerCase()
      if (
        !d.definition.name.toLowerCase().includes(q) &&
        !(d.definition.description && d.definition.description.toLowerCase().includes(q)) &&
        !(d.definition.role && d.definition.role.toLowerCase().includes(q)) &&
        !d.definition.provider.toLowerCase().includes(q)
      ) return false
    }
    return true
  }), [definitions, sourceFilter, filterSource, filterProvider, searchText])

  const sources = useMemo(
    () => [...new Set(definitions.map(d => d.source))].sort(),
    [definitions]
  )
  const providers = useMemo(
    () => [...new Set(definitions.map(d => d.definition.provider))].sort(),
    [definitions]
  )

  const handleCreate = async () => {
    try {
      const body: Record<string, unknown> = {
        name: createForm.name,
        provider: createForm.provider,
        mode: createForm.mode,
        terminal: createForm.terminal,
        base_branch: createForm.base_branch,
        timeout: createForm.timeout,
        max_turns: createForm.max_turns,
      }
      if (createForm.description) body.description = createForm.description
      if (createForm.role) body.role = createForm.role
      if (createForm.goal) body.goal = createForm.goal
      if (createForm.personality) body.personality = createForm.personality
      if (createForm.instructions) body.instructions = createForm.instructions
      if (createForm.model) body.model = createForm.model
      if (createForm.isolation) body.isolation = createForm.isolation

      const res = await fetch(`${getBaseUrl()}/api/agents/definitions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        onToggleCreateForm(false)
        setCreateForm({
          name: '', description: '', role: '', goal: '', personality: '', instructions: '',
          provider: 'claude', model: '', mode: 'headless', terminal: 'auto', isolation: '',
          base_branch: 'main', timeout: 120, max_turns: 10,
        })
        fetchDefinitions(true)
        showToast(`Agent "${createForm.name}" created`, 'success')
      } else {
        showToast('Failed to create agent definition', 'error')
      }
    } catch (e) {
      console.error('Failed to create agent definition:', e)
      showToast('Failed to create agent definition', 'error')
    }
  }

  const handleEdit = (item: AgentDefInfo) => {
    const d = item.definition
    setCreateForm({
      name: d.name,
      description: d.description || '',
      role: d.role || '',
      goal: d.goal || '',
      personality: d.personality || '',
      instructions: d.instructions || '',
      provider: d.provider,
      model: d.model || '',
      mode: d.mode,
      terminal: d.terminal,
      isolation: d.isolation || '',
      base_branch: d.base_branch,
      timeout: d.timeout,
      max_turns: d.max_turns,
    })
    setEditingId(item.db_id)
    onToggleCreateForm(true)
  }

  const handleUpdate = async () => {
    if (!editingId) return
    try {
      const body: Record<string, unknown> = {
        name: createForm.name,
        description: createForm.description || null,
        role: createForm.role || null,
        goal: createForm.goal || null,
        personality: createForm.personality || null,
        instructions: createForm.instructions || null,
        provider: createForm.provider,
        model: createForm.model || null,
        mode: createForm.mode,
        terminal: createForm.terminal,
        isolation: createForm.isolation || null,
        base_branch: createForm.base_branch,
        timeout: createForm.timeout,
        max_turns: createForm.max_turns,
      }

      const res = await fetch(`${getBaseUrl()}/api/agents/definitions/${editingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        onToggleCreateForm(false)
        setEditingId(null)
        setCreateForm({
          name: '', description: '', role: '', goal: '', personality: '', instructions: '',
          provider: 'claude', model: '', mode: 'headless', terminal: 'auto', isolation: '',
          base_branch: 'main', timeout: 120, max_turns: 10,
        })
        fetchDefinitions(true)
        showToast(`Agent "${createForm.name}" updated`, 'success')
      } else {
        showToast('Failed to update agent definition', 'error')
      }
    } catch (e) {
      console.error('Failed to update agent definition:', e)
      showToast('Failed to update agent definition', 'error')
    }
  }

  const handleDelete = async (dbId: string) => {
    if (!confirm('Delete this agent definition?')) return
    try {
      const res = await fetch(`${getBaseUrl()}/api/agents/definitions/${dbId}`, {
        method: 'DELETE',
      })
      if (res.ok) {
        fetchDefinitions(true)
        showToast('Agent definition deleted', 'success')
      } else {
        showToast('Failed to delete agent definition', 'error')
      }
    } catch (e) {
      console.error('Failed to delete agent definition:', e)
      showToast('Failed to delete agent definition', 'error')
    }
  }

  const handleRestore = async (dbId: string) => {
    try {
      const res = await fetch(`${getBaseUrl()}/api/agents/definitions/${dbId}/restore`, {
        method: 'POST',
      })
      if (res.ok) {
        fetchDefinitions(true)
        showToast('Agent definition restored', 'success')
      } else {
        showToast('Failed to restore agent definition', 'error')
      }
    } catch (e) {
      console.error('Failed to restore agent definition:', e)
      showToast('Failed to restore agent definition', 'error')
    }
  }

  const handleDownload = useCallback(async (name: string) => {
    try {
      const res = await fetch(`${getBaseUrl()}/api/agents/definitions/${name}/export`)
      if (res.ok) {
        const text = await res.text()
        const blob = new Blob([text], { type: 'application/x-yaml' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${name}.yaml`
        a.click()
        URL.revokeObjectURL(url)
      }
    } catch (e) {
      console.error('Failed to download agent:', e)
    }
  }, [])

  const handleYamlEdit = useCallback(async (item: AgentDefInfo) => {
    setYamlLoading(true)
    setYamlAgent(item)
    try {
      const res = await fetch(`${getBaseUrl()}/api/agents/definitions/${item.definition.name}/export`)
      if (res.ok) {
        const text = await res.text()
        setYamlContent(text)
      } else {
        setYamlContent('')
        window.alert('Failed to load agent YAML')
        setYamlAgent(null)
      }
    } catch (e) {
      console.error('Failed to load agent YAML:', e)
      setYamlContent('')
      setYamlAgent(null)
    } finally {
      setYamlLoading(false)
    }
  }, [])

  const handleYamlSave = useCallback(async () => {
    if (!yamlAgent) return
    let parsed: Record<string, unknown>
    try {
      parsed = yaml.load(yamlContent, { schema: yaml.JSON_SCHEMA }) as Record<string, unknown>
    } catch (e) {
      throw new Error(`Invalid YAML: ${e instanceof Error ? e.message : String(e)}`)
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('Invalid YAML: expected an object')
    }
    const isDb = yamlAgent.source.endsWith('-db')
    if (isDb && yamlAgent.db_id) {
      const body: Record<string, unknown> = {
        name: (parsed.name as string) || yamlAgent.definition.name,
        description: parsed.description ?? null,
        role: parsed.role ?? null,
        goal: parsed.goal ?? null,
        personality: parsed.personality ?? null,
        instructions: parsed.instructions ?? null,
        provider: parsed.provider || yamlAgent.definition.provider,
        model: parsed.model ?? null,
        mode: parsed.mode || yamlAgent.definition.mode,
        terminal: parsed.terminal || yamlAgent.definition.terminal,
        isolation: parsed.isolation ?? null,
        base_branch: (parsed.base_branch as string) || yamlAgent.definition.base_branch,
        timeout: parsed.timeout ?? yamlAgent.definition.timeout,
        max_turns: parsed.max_turns ?? yamlAgent.definition.max_turns,
      }
      const res = await fetch(`${getBaseUrl()}/api/agents/definitions/${yamlAgent.db_id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (!res.ok) throw new Error('Failed to save agent definition')
    } else {
      // For file-based agents, import to DB
      const res = await fetch(`${getBaseUrl()}/api/agents/definitions/import/${yamlAgent.definition.name}`, {
        method: 'POST',
      })
      if (!res.ok) throw new Error('Failed to import agent definition to DB')
    }
    setYamlAgent(null)
    fetchDefinitions(true)
  }, [yamlAgent, yamlContent, fetchDefinitions])

  const handleUseAsTemplate = async (name: string) => {
    try {
      const res = await fetch(`${getBaseUrl()}/api/agents/definitions/${encodeURIComponent(name)}/use-as-template`, {
        method: 'POST',
      })
      if (res.ok) {
        fetchDefinitions(true)
        showToast(`Created custom copy of "${name}"`, 'success')
      } else {
        const data = await res.json().catch(() => ({}))
        showToast(data.detail || 'Failed to use as template', 'error')
      }
    } catch (e) {
      console.error('Failed to use agent as template:', e)
      showToast('Failed to use as template', 'error')
    }
  }

  const handleUseAllAsTemplates = async () => {
    try {
      const res = await fetch(`${getBaseUrl()}/api/workflows/use-all-bundled-as-templates?workflow_type=agent`, {
        method: 'POST',
      })
      if (res.ok) {
        const data = await res.json()
        fetchDefinitions(true)
        showToast(`Created ${data.count || 0} template copies`, 'success')
      } else {
        showToast('Failed to use all as templates', 'error')
      }
    } catch (e) {
      console.error('Failed to use all bundled agents as templates:', e)
      showToast('Failed to use all as templates', 'error')
    }
  }

  const handleImport = async (name: string) => {
    setImportingName(name)
    setImportResult(null)
    try {
      const res = await fetch(`${getBaseUrl()}/api/agents/definitions/import/${name}`, {
        method: 'POST',
      })
      setImportResult({ name, ok: res.ok })
      if (res.ok) fetchDefinitions(true)
    } catch (e) {
      console.error('Failed to import agent definition:', e)
      setImportResult({ name, ok: false })
    } finally {
      setImportingName(null)
      setTimeout(() => setImportResult(null), 3000)
    }
  }

  return (
    <div className="agent-defs-tab">
      {toastMessage && (
        <div
          className={`agent-defs-toast ${toastMessage.type === 'success' ? 'agent-defs-toast--success' : ''}`}
          onClick={() => setToastMessage(null)}
        >
          {toastMessage.text}
        </div>
      )}

      {/* Filter chips */}
      <div className="workflows-filter-bar">
        <div className="workflows-filter-chips">
          {sources.map(s => (
            <button
              type="button"
              key={s}
              className={`workflows-filter-chip ${filterSource === s ? 'workflows-filter-chip--active' : ''}`}
              onClick={() => setFilterSource(filterSource === s ? 'all' : s)}
            >
              {SOURCE_LABELS[s] || s}
            </button>
          ))}
          {providers.map(p => (
            <button
              type="button"
              key={p}
              className={`workflows-filter-chip ${filterProvider === p ? 'workflows-filter-chip--active' : ''}`}
              onClick={() => setFilterProvider(filterProvider === p ? 'all' : p)}
            >
              {p}
            </button>
          ))}
          {(filterSource !== 'all' || filterProvider !== 'all') && (
            <button
              type="button"
              className="workflows-filter-chip rules-filter-clear"
              onClick={() => { setFilterSource('all'); setFilterProvider('all') }}
            >
              Clear
            </button>
          )}
        </div>
        {sourceFilter === 'templates' && (
          <button
            type="button"
            className="workflows-toolbar-btn"
            onClick={handleUseAllAsTemplates}
          >
            Use All as Templates
          </button>
        )}
      </div>

      {/* Create form */}
      {showCreateForm && (
        <div className="agent-defs-create-form">
          <div className="agent-defs-form-grid">
            <label>
              <span>Name *</span>
              <input
                value={createForm.name}
                onChange={e => setCreateForm(f => ({ ...f, name: e.target.value }))}
                placeholder="my-agent"
              />
            </label>
            <label>
              <span>Provider</span>
              <select
                value={createForm.provider}
                onChange={e => {
                  const newProvider = e.target.value
                  const newModels = providerModels[newProvider]
                  const modelValid = newModels?.some(m => m.value === createForm.model)
                  setCustomModelInput(false)
                  setCreateForm(f => ({
                    ...f,
                    provider: newProvider,
                    model: modelValid ? f.model : '',
                  }))
                }}
              >
                <option value="claude">claude</option>
                <option value="gemini">gemini</option>
                <option value="codex">codex</option>
                <option value="cursor">cursor</option>
              </select>
            </label>
            <label>
              <span>Mode</span>
              <select
                value={createForm.mode}
                onChange={e => setCreateForm(f => ({ ...f, mode: e.target.value }))}
              >
                <option value="headless">headless</option>
                <option value="terminal">terminal</option>
                <option value="embedded">embedded</option>
              </select>
            </label>
            <label>
              <span>Model</span>
              <ModelSelector
                model={createForm.model}
                models={providerModels[createForm.provider]}
                customModelInput={customModelInput}
                setCustomModelInput={setCustomModelInput}
                setCreateForm={setCreateForm}
              />
            </label>
            <label>
              <span>Isolation</span>
              <select
                value={createForm.isolation}
                onChange={e => setCreateForm(f => ({ ...f, isolation: e.target.value }))}
              >
                <option value="">none</option>
                <option value="current">current</option>
                <option value="worktree">worktree</option>
                <option value="clone">clone</option>
              </select>
            </label>
            <label>
              <span>Terminal</span>
              <select
                value={createForm.terminal}
                onChange={e => setCreateForm(f => ({ ...f, terminal: e.target.value }))}
              >
                <option value="auto">auto</option>
                <option value="ghostty">ghostty</option>
                <option value="iterm">iterm</option>
                <option value="tmux">tmux</option>
                <option value="kitty">kitty</option>
              </select>
            </label>
            <label>
              <span>Timeout (s)</span>
              <input
                type="number"
                value={createForm.timeout}
                onChange={e => setCreateForm(f => ({ ...f, timeout: Number(e.target.value) }))}
              />
            </label>
            <label>
              <span>Max turns</span>
              <input
                type="number"
                value={createForm.max_turns}
                onChange={e => setCreateForm(f => ({ ...f, max_turns: Number(e.target.value) }))}
              />
            </label>
            <label className="agent-defs-form-wide">
              <span>Description</span>
              <input
                value={createForm.description}
                onChange={e => setCreateForm(f => ({ ...f, description: e.target.value }))}
                placeholder="What this agent does..."
              />
            </label>
            <label>
              <span>Role</span>
              <input
                value={createForm.role}
                onChange={e => setCreateForm(f => ({ ...f, role: e.target.value }))}
                placeholder="e.g. Senior security engineer"
              />
            </label>
            <label>
              <span>Goal</span>
              <input
                value={createForm.goal}
                onChange={e => setCreateForm(f => ({ ...f, goal: e.target.value }))}
                placeholder="What success looks like..."
              />
            </label>
            <label>
              <span>Personality</span>
              <input
                value={createForm.personality}
                onChange={e => setCreateForm(f => ({ ...f, personality: e.target.value }))}
                placeholder="Communication style, tone..."
              />
            </label>
            <label className="agent-defs-form-wide">
              <span>Instructions</span>
              <textarea
                value={createForm.instructions}
                onChange={e => setCreateForm(f => ({ ...f, instructions: e.target.value }))}
                placeholder="Detailed rules, constraints, approach..."
                rows={3}
              />
            </label>
          </div>
          <div className="agent-defs-form-actions">
            <button className="agent-defs-btn" onClick={() => { onToggleCreateForm(false); setEditingId(null) }}>Cancel</button>
            <button
              className="agent-defs-btn agent-defs-btn--primary"
              onClick={editingId ? handleUpdate : handleCreate}
              disabled={!createForm.name.trim()}
            >
              {editingId ? 'Save' : 'Create'}
            </button>
          </div>
        </div>
      )}

      {/* Running agents */}
      {(running.length > 0 || recentRuns.length > 0) && (
        <div className="agent-runs-section">
          <div className="agent-runs-header">
            <h3 className="agent-runs-title">
              Running Agents
              {running.length > 0 && (
                <span className="agent-runs-count agent-runs-count--active">{running.length}</span>
              )}
            </h3>
            {recentRuns.length > 0 && (
              <button
                className="agent-defs-btn"
                onClick={() => setShowRecentRuns(!showRecentRuns)}
              >
                {showRecentRuns ? 'Hide history' : `History (${recentRuns.length})`}
              </button>
            )}
          </div>

          {running.length > 0 ? (
            <div className="agent-runs-list">
              {running.map(agent => (
                <RunningAgentCard key={agent.run_id} agent={agent} onCancel={cancelAgent} />
              ))}
            </div>
          ) : (
            <div className="agent-runs-empty">No agents currently running</div>
          )}

          {showRecentRuns && recentRuns.length > 0 && (
            <div className="agent-runs-history">
              <table className="agent-runs-table">
                <thead>
                  <tr>
                    <th>Status</th>
                    <th>Provider</th>
                    <th>Prompt</th>
                    <th>Turns</th>
                    <th>Duration</th>
                    <th>Started</th>
                  </tr>
                </thead>
                <tbody>
                  {recentRuns.map(run => (
                    <AgentRunRow key={run.id} run={run} />
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Card grid */}
      <div className="workflows-content">
        {loading ? (
          <div className="workflows-loading">Loading agent definitions...</div>
        ) : filtered.length === 0 ? (
          <div className="workflows-empty">No agent definitions found</div>
        ) : (
          <div className="workflows-grid">
            {filtered.map(item => {
              const d = item.definition
              const isExpanded = expandedName === d.name
              const isDb = item.source.endsWith('-db')
              const isTemplate = item.source === 'template'
              const workflowCount = d.workflows ? Object.keys(d.workflows).length : 0

              return (
                <div
                  key={d.name}
                  className={`agent-def-card${isExpanded ? ' agent-def-card--expanded' : ''}${item.deleted_at ? ' agent-def-card--deleted' : ''}${isTemplate ? ' workflows-card--template' : ''}`}
                >
                  {/* Collapsed header */}
                  <button
                    className="agent-def-header"
                    onClick={() => setExpandedName(isExpanded ? null : d.name)}
                  >
                    <div className="agent-def-header-top">
                      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                        <span className={`agent-def-name${item.deleted_at ? ' agent-def-name--deleted' : ''}`}>{d.name}</span>
                        <span className="workflows-card-type workflows-card-type--agent">agent</span>
                      </div>
                    </div>
                    {d.description && (
                      <div className="agent-def-desc">
                        {d.description.split('\n')[0].slice(0, 100)}
                      </div>
                    )}
                    <div className="agent-def-badges">
                      <span className="workflows-card-badge workflows-card-badge--source">
                        {SOURCE_LABELS[item.source] || item.source}
                      </span>
                      <span
                        className="agent-def-badge agent-def-badge--filled"
                        style={{ background: PROVIDER_COLORS[d.provider] || '#666' }}
                      >
                        {d.provider}
                      </span>
                      <span
                        className="agent-def-badge agent-def-badge--filled"
                        style={{ background: MODE_COLORS[d.mode] || '#666' }}
                      >
                        {d.mode}
                      </span>
                      {d.isolation && (
                        <span
                          className="agent-def-badge agent-def-badge--filled"
                          style={{ background: ISOLATION_COLORS[d.isolation] || '#666' }}
                        >
                          {d.isolation}
                        </span>
                      )}
                      {workflowCount > 0 && (
                        <span className="agent-def-badge agent-def-badge--dim">
                          {workflowCount} workflow{workflowCount !== 1 ? 's' : ''}
                        </span>
                      )}
                      <span className="agent-def-badge agent-def-badge--dim">
                        {d.timeout}s
                      </span>
                    </div>
                  </button>

                  {/* Card footer - always visible */}
                  <div className="workflows-card-footer">
                    {item.deleted_at ? (
                      <div className="workflows-card-actions">
                        {item.db_id && (
                          <button
                            type="button"
                            className="workflows-action-btn workflows-action-btn--restore"
                            onClick={() => handleRestore(item.db_id!)}
                            title="Restore this agent"
                          >
                            Restore
                          </button>
                        )}
                      </div>
                    ) : isTemplate ? (
                      <>
                        <div />
                        <div className="workflows-card-actions">
                          {devMode ? (
                            <>
                              <button type="button" className="workflows-action-btn" onClick={() => handleYamlEdit(item)} title="Edit as YAML">YAML</button>
                              {item.db_id && (
                                <button type="button" className="workflows-action-btn" onClick={() => handleEdit(item)} title="Edit agent definition">Edit</button>
                              )}
                              <button type="button" className="workflows-action-icon" onClick={() => handleDownload(d.name)} title="Download YAML" aria-label="Download agent as YAML">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v9m0 0L5 8m3 3 3-3M2.5 12.5v1a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-1" /></svg>
                              </button>
                              {item.db_id && (
                                <button type="button" className="workflows-action-icon workflows-action-icon--danger" onClick={() => handleDelete(item.db_id!)} title="Delete" aria-label="Delete agent">
                                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2.5 4.5h11M5.5 4.5V3a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v1.5M6.5 7v4.5M9.5 7v4.5" /><path d="M3.5 4.5 4 13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l.5-8.5" /></svg>
                                </button>
                              )}
                            </>
                          ) : (
                            <>
                              <button type="button" className="workflows-action-btn" onClick={() => handleUseAsTemplate(d.name)} title="Create a custom copy">Use as Template</button>
                              <button type="button" className="workflows-action-icon" onClick={() => handleDownload(d.name)} title="Download YAML" aria-label="Download agent as YAML">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v9m0 0L5 8m3 3 3-3M2.5 12.5v1a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-1" /></svg>
                              </button>
                            </>
                          )}
                        </div>
                      </>
                    ) : (
                      <>
                        <div />
                        <div className="workflows-card-actions">
                          <button type="button" className="workflows-action-btn" onClick={() => handleYamlEdit(item)} title="Edit as YAML">YAML</button>
                          {isDb && item.db_id && (
                            <button type="button" className="workflows-action-btn" onClick={() => handleEdit(item)} title="Edit agent definition">Edit</button>
                          )}
                          <button type="button" className="workflows-action-icon" onClick={() => handleDownload(d.name)} title="Download YAML" aria-label="Download agent as YAML">
                            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v9m0 0L5 8m3 3 3-3M2.5 12.5v1a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-1" /></svg>
                          </button>
                          {isDb && item.db_id ? (
                            <button type="button" className="workflows-action-icon workflows-action-icon--danger" onClick={() => handleDelete(item.db_id!)} title="Delete" aria-label="Delete agent">
                              <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2.5 4.5h11M5.5 4.5V3a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v1.5M6.5 7v4.5M9.5 7v4.5" /><path d="M3.5 4.5 4 13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l.5-8.5" /></svg>
                            </button>
                          ) : (
                            <button type="button" className="workflows-action-btn" onClick={() => handleImport(d.name)} disabled={importingName === d.name} title="Import to DB for customization">
                              {importingName === d.name ? '...' : 'Import'}
                            </button>
                          )}
                          {importResult?.name === d.name && (
                            <span className={`agent-def-import-result ${importResult.ok ? 'agent-def-import-result--ok' : 'agent-def-import-result--err'}`}>
                              {importResult.ok ? 'OK' : 'Fail'}
                            </span>
                          )}
                        </div>
                      </>
                    )}
                  </div>

                  {/* Expanded detail */}
                  {isExpanded && (
                    <div className="agent-def-detail">
                      {/* Property grid */}
                      <div className="agent-def-props">
                        <PropRow label="Provider" value={d.provider} />
                        <PropRow label="Model" value={d.model || '(default)'} />
                        <PropRow label="Mode" value={d.mode} />
                        <PropRow label="Terminal" value={d.terminal} />
                        <PropRow label="Isolation" value={d.isolation || 'none'} />
                        <PropRow label="Base branch" value={d.base_branch} />
                        <PropRow label="Timeout" value={`${d.timeout}s`} />
                        <PropRow label="Max turns" value={String(d.max_turns)} />
                        {d.default_workflow && (
                          <PropRow label="Default workflow" value={d.default_workflow} />
                        )}
                      </div>

                      {/* Role / Goal / Personality as full-width sections */}
                      {d.role && (
                        <div className="agent-def-section">
                          <div className="agent-def-section-title">Role</div>
                          <pre className="agent-def-description-full">{d.role}</pre>
                        </div>
                      )}
                      {d.goal && (
                        <div className="agent-def-section">
                          <div className="agent-def-section-title">Goal</div>
                          <pre className="agent-def-description-full">{d.goal}</pre>
                        </div>
                      )}
                      {d.personality && (
                        <div className="agent-def-section">
                          <div className="agent-def-section-title">Personality</div>
                          <pre className="agent-def-description-full">{d.personality}</pre>
                        </div>
                      )}

                      {/* Full description */}
                      {d.description && d.description.includes('\n') && (
                        <div className="agent-def-section">
                          <div className="agent-def-section-title">Description</div>
                          <pre className="agent-def-description-full">{d.description}</pre>
                        </div>
                      )}

                      {/* Instructions */}
                      {d.instructions && (
                        <div className="agent-def-section">
                          <div className="agent-def-section-title">Instructions</div>
                          <pre className="agent-def-description-full">{d.instructions}</pre>
                        </div>
                      )}

                      {/* Workflows */}
                      {d.workflows && workflowCount > 0 && (
                        <div className="agent-def-section">
                          <div className="agent-def-section-title">Workflows</div>
                          <div className="agent-def-workflow-list">
                            {Object.entries(d.workflows).map(([wfName, wf]) => (
                              <div key={wfName} className="agent-def-workflow-item">
                                <span className="agent-def-workflow-name">{wfName}</span>
                                {wf.type && <span className="agent-def-badge agent-def-badge--dim">{wf.type}</span>}
                                {wf.file && <span className="agent-def-badge agent-def-badge--dim">{wf.file}</span>}
                                {wf.mode && <span className="agent-def-badge agent-def-badge--filled" style={{ background: MODE_COLORS[wf.mode] || '#666' }}>{wf.mode}</span>}
                                {wf.internal && <span className="agent-def-badge agent-def-badge--dim">internal</span>}
                                {wf.step_count != null && <span className="agent-def-badge agent-def-badge--dim">{wf.step_count} steps</span>}
                                {wf.description && <span className="agent-def-workflow-desc">{wf.description}</span>}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Sandbox config */}
                      {d.sandbox && (
                        <div className="agent-def-section">
                          <div className="agent-def-section-title">Sandbox</div>
                          <pre className="agent-def-json">{JSON.stringify(d.sandbox, null, 2)}</pre>
                        </div>
                      )}

                      {/* Skill profile */}
                      {d.skill_profile && (
                        <div className="agent-def-section">
                          <div className="agent-def-section-title">Skill Profile</div>
                          <pre className="agent-def-json">{JSON.stringify(d.skill_profile, null, 2)}</pre>
                        </div>
                      )}

                      {/* Source info */}
                      <div className="agent-def-section">
                        <div className="agent-def-section-title">Source</div>
                        <div className="agent-def-source-info">
                          {item.source_path ? (
                            <code>{item.source_path}</code>
                          ) : (
                            <span>Database ({item.source}){item.db_id ? ` — ${item.db_id.slice(0, 8)}` : ''}</span>
                          )}
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>

      {/* YAML editor modal */}
      {yamlAgent && (
        <YamlEditorModal
          workflowName={yamlAgent.definition.name}
          yamlContent={yamlContent}
          loading={yamlLoading}
          onChange={setYamlContent}
          onSave={handleYamlSave}
          onClose={() => setYamlAgent(null)}
        />
      )}
    </div>
  )
}

// =============================================================================
// Sub-components
// =============================================================================

function ModelSelector({
  model,
  models,
  customModelInput,
  setCustomModelInput,
  setCreateForm,
}: {
  model: string
  models: { value: string; label: string }[] | undefined
  customModelInput: boolean
  setCustomModelInput: (v: boolean) => void
  setCreateForm: React.Dispatch<React.SetStateAction<CreateFormData>>
}) {
  const isKnown = models?.some(m => m.value === model)
  const showCustom = customModelInput || !models || (!isKnown && model !== '')

  if (showCustom) {
    return (
      <div className="agent-defs-model-field">
        <input
          value={model}
          onChange={e => setCreateForm(f => ({ ...f, model: e.target.value }))}
          placeholder="e.g. claude-sonnet-4-5-20250929"
          autoFocus={customModelInput}
        />
        {models && (
          <button
            type="button"
            className="agent-defs-model-toggle"
            onClick={() => { setCustomModelInput(false); setCreateForm(f => ({ ...f, model: '' })) }}
            title="Switch to preset list"
          >
            &times;
          </button>
        )}
      </div>
    )
  }

  return (
    <select
      value={model}
      onChange={e => {
        if (e.target.value === '__custom__') {
          setCustomModelInput(true)
          setCreateForm(f => ({ ...f, model: '' }))
        } else {
          setCreateForm(f => ({ ...f, model: e.target.value }))
        }
      }}
    >
      {models?.map(m => (
        <option key={m.value} value={m.value}>{m.label}</option>
      ))}
      <option value="__custom__">Custom...</option>
    </select>
  )
}

function PropRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="agent-def-prop-row">
      <span className="agent-def-prop-label">{label}</span>
      <span className="agent-def-prop-value">{value}</span>
    </div>
  )
}

function formatDuration(startIso: string, endIso?: string | null): string {
  const start = new Date(startIso).getTime()
  const end = endIso ? new Date(endIso).getTime() : Date.now()
  if (isNaN(start) || isNaN(end)) return '\u2014'
  const seconds = Math.floor((end - start) / 1000)
  if (seconds < 60) return `${seconds}s`
  const minutes = Math.floor(seconds / 60)
  const secs = seconds % 60
  if (minutes < 60) return `${minutes}m ${secs}s`
  const hours = Math.floor(minutes / 60)
  return `${hours}h ${minutes % 60}m`
}

function formatTimeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  if (isNaN(diff)) return '\u2014'
  const minutes = Math.floor(diff / 60000)
  if (minutes < 1) return 'just now'
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours / 24)}d ago`
}

function RunningAgentCard({ agent, onCancel }: { agent: RunningAgent; onCancel: (id: string) => void }) {
  return (
    <div className="agent-run-card agent-run-card--running">
      <div className="agent-run-card-top">
        <span className="agent-run-pulse" />
        <span className="agent-run-id">{agent.run_id}</span>
        <span
          className="agent-def-badge agent-def-badge--filled"
          style={{ background: PROVIDER_COLORS[agent.provider] || '#666' }}
        >
          {agent.provider}
        </span>
        <span
          className="agent-def-badge agent-def-badge--filled"
          style={{ background: MODE_COLORS[agent.mode] || '#666' }}
        >
          {agent.mode}
        </span>
        {agent.workflow_name && (
          <span className="agent-def-badge agent-def-badge--dim">{agent.workflow_name}</span>
        )}
      </div>
      <div className="agent-run-card-bottom">
        <span className="agent-run-duration">{formatDuration(agent.started_at)}</span>
        {agent.pid && <span className="agent-run-meta">PID {agent.pid}</span>}
        <span className="agent-run-session">{agent.session_id.slice(0, 8)}</span>
        <button
          className="agent-defs-btn agent-defs-btn--danger agent-run-cancel"
          onClick={() => onCancel(agent.run_id)}
        >
          Cancel
        </button>
      </div>
    </div>
  )
}

function AgentRunRow({ run }: { run: AgentRun }) {
  const duration = run.started_at
    ? formatDuration(run.started_at, run.completed_at)
    : '—'

  return (
    <tr className="agent-run-row">
      <td>
        <span
          className="agent-run-status"
          style={{ color: STATUS_COLORS[run.status] || '#888' }}
        >
          {run.status}
        </span>
      </td>
      <td>
        <span
          className="agent-def-badge agent-def-badge--filled"
          style={{ background: PROVIDER_COLORS[run.provider] || '#666' }}
        >
          {run.provider}
        </span>
      </td>
      <td className="agent-run-prompt-cell">
        <span className="agent-run-prompt" title={run.prompt}>
          {run.prompt.slice(0, 80)}{run.prompt.length > 80 ? '...' : ''}
        </span>
      </td>
      <td>{run.turns_used}</td>
      <td>{duration}</td>
      <td>{run.started_at ? formatTimeAgo(run.started_at) : '—'}</td>
    </tr>
  )
}
