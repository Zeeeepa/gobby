import { useState, useEffect, useCallback, useMemo } from 'react'

// =============================================================================
// Types
// =============================================================================

interface AgentDefInfo {
  definition: {
    name: string
    description: string | null
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

const SOURCE_COLORS: Record<string, string> = {
  'project-file': '#3b82f6',
  'user-file': '#8b5cf6',
  'built-in-file': '#6b7280',
  'project-db': '#10b981',
  'global-db': '#f59e0b',
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

const ISOLATION_COLORS: Record<string, string> = {
  clone: '#ef4444',
  worktree: '#eab308',
  current: '#6b7280',
}

function getBaseUrl(): string {
  return ''
}

// =============================================================================
// Component
// =============================================================================

export function AgentDefinitionsPage() {
  const [definitions, setDefinitions] = useState<AgentDefInfo[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedName, setExpandedName] = useState<string | null>(null)
  const [filterSource, setFilterSource] = useState<string>('all')
  const [filterProvider, setFilterProvider] = useState<string>('all')
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [importingName, setImportingName] = useState<string | null>(null)
  const [importResult, setImportResult] = useState<{ name: string; ok: boolean } | null>(null)
  const [createForm, setCreateForm] = useState<CreateFormData>({
    name: '', description: '', provider: 'claude', model: '',
    mode: 'headless', terminal: 'auto', isolation: '',
    base_branch: 'main', timeout: 120, max_turns: 10,
  })

  const fetchDefinitions = useCallback(async () => {
    setLoading(true)
    try {
      const res = await fetch(`${getBaseUrl()}/api/agents/definitions`)
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

  useEffect(() => { fetchDefinitions() }, [fetchDefinitions])

  const filtered = useMemo(() => definitions.filter(d => {
    if (filterSource !== 'all' && d.source !== filterSource) return false
    if (filterProvider !== 'all' && d.definition.provider !== filterProvider) return false
    return true
  }), [definitions, filterSource, filterProvider])

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
      if (createForm.model) body.model = createForm.model
      if (createForm.isolation) body.isolation = createForm.isolation

      const res = await fetch(`${getBaseUrl()}/api/agents/definitions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
      if (res.ok) {
        setShowCreateForm(false)
        setCreateForm({
          name: '', description: '', provider: 'claude', model: '',
          mode: 'headless', terminal: 'auto', isolation: '',
          base_branch: 'main', timeout: 120, max_turns: 10,
        })
        fetchDefinitions()
      }
    } catch (e) {
      console.error('Failed to create agent definition:', e)
    }
  }

  const handleDelete = async (dbId: string) => {
    if (!confirm('Delete this agent definition?')) return
    try {
      const res = await fetch(`${getBaseUrl()}/api/agents/definitions/${dbId}`, {
        method: 'DELETE',
      })
      if (res.ok) fetchDefinitions()
    } catch (e) {
      console.error('Failed to delete agent definition:', e)
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
      if (res.ok) fetchDefinitions()
    } catch (e) {
      console.error('Failed to import agent definition:', e)
      setImportResult({ name, ok: false })
    } finally {
      setImportingName(null)
      setTimeout(() => setImportResult(null), 3000)
    }
  }

  return (
    <main className="agent-defs-page">
      {/* Toolbar */}
      <div className="agent-defs-toolbar">
        <div className="agent-defs-toolbar-left">
          <h2 className="agent-defs-title">Agent Definitions</h2>
          <span className="agent-defs-count">{filtered.length}</span>
        </div>
        <div className="agent-defs-toolbar-right">
          <select
            className="agent-defs-filter"
            value={filterSource}
            onChange={e => setFilterSource(e.target.value)}
          >
            <option value="all">All sources</option>
            {sources.map(s => (
              <option key={s} value={s}>{SOURCE_LABELS[s] || s}</option>
            ))}
          </select>
          <select
            className="agent-defs-filter"
            value={filterProvider}
            onChange={e => setFilterProvider(e.target.value)}
          >
            <option value="all">All providers</option>
            {providers.map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <button className="agent-defs-btn" onClick={fetchDefinitions} title="Refresh">
            <RefreshIcon />
          </button>
          <button
            className="agent-defs-btn agent-defs-btn--primary"
            onClick={() => setShowCreateForm(!showCreateForm)}
          >
            + New
          </button>
        </div>
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
                onChange={e => setCreateForm(f => ({ ...f, provider: e.target.value }))}
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
              <input
                value={createForm.model}
                onChange={e => setCreateForm(f => ({ ...f, model: e.target.value }))}
                placeholder="e.g. claude-sonnet-4-5-20250929"
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
          </div>
          <div className="agent-defs-form-actions">
            <button className="agent-defs-btn" onClick={() => setShowCreateForm(false)}>Cancel</button>
            <button
              className="agent-defs-btn agent-defs-btn--primary"
              onClick={handleCreate}
              disabled={!createForm.name.trim()}
            >
              Create
            </button>
          </div>
        </div>
      )}

      {/* Card grid */}
      {loading ? (
        <div className="agent-defs-empty">Loading agent definitions...</div>
      ) : filtered.length === 0 ? (
        <div className="agent-defs-empty">No agent definitions found</div>
      ) : (
        <div className="agent-defs-grid">
          {filtered.map(item => {
            const d = item.definition
            const isExpanded = expandedName === d.name
            const isDb = item.source.endsWith('-db')
            const workflowCount = d.workflows ? Object.keys(d.workflows).length : 0

            return (
              <div
                key={d.name}
                className={`agent-def-card${isExpanded ? ' agent-def-card--expanded' : ''}`}
              >
                {/* Collapsed header */}
                <button
                  className="agent-def-header"
                  onClick={() => setExpandedName(isExpanded ? null : d.name)}
                >
                  <div className="agent-def-header-top">
                    <span className="agent-def-name">{d.name}</span>
                    <span className="agent-def-chevron">{isExpanded ? '\u25B2' : '\u25BC'}</span>
                  </div>
                  {d.description && (
                    <div className="agent-def-desc">
                      {d.description.split('\n')[0].slice(0, 100)}
                    </div>
                  )}
                  <div className="agent-def-badges">
                    <span
                      className="agent-def-badge"
                      style={{ borderColor: SOURCE_COLORS[item.source] || '#666', color: SOURCE_COLORS[item.source] || '#666' }}
                    >
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

                    {/* Full description */}
                    {d.description && d.description.includes('\n') && (
                      <div className="agent-def-section">
                        <div className="agent-def-section-title">Description</div>
                        <pre className="agent-def-description-full">{d.description}</pre>
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

                    {/* Actions */}
                    <div className="agent-def-actions">
                      {isDb && item.db_id && (
                        <button
                          className="agent-defs-btn agent-defs-btn--danger"
                          onClick={() => handleDelete(item.db_id!)}
                        >
                          Delete
                        </button>
                      )}
                      {!isDb && (
                        <>
                          <button
                            className="agent-defs-btn"
                            onClick={() => handleImport(d.name)}
                            disabled={importingName === d.name}
                            title="Copy this file-based definition into the DB for customization"
                          >
                            {importingName === d.name ? 'Importing...' : 'Import to DB'}
                          </button>
                          {importResult?.name === d.name && (
                            <span className={`agent-def-import-result ${importResult.ok ? 'agent-def-import-result--ok' : 'agent-def-import-result--err'}`}>
                              {importResult.ok ? 'Imported successfully' : 'Import failed'}
                            </span>
                          )}
                        </>
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </main>
  )
}

// =============================================================================
// Sub-components
// =============================================================================

function PropRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="agent-def-prop-row">
      <span className="agent-def-prop-label">{label}</span>
      <span className="agent-def-prop-value">{value}</span>
    </div>
  )
}

function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  )
}
