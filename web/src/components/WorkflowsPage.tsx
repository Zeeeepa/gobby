import { useState, useCallback, useMemo, useEffect } from 'react'
import * as yaml from 'js-yaml'
import { useWorkflows } from '../hooks/useWorkflows'
import type { WorkflowDetail } from '../hooks/useWorkflows'
import { PipelineEditor } from './PipelineEditor'
import { CodeMirrorEditor } from './CodeMirrorEditor'
import { TabBar } from './TabBar'
import { RulesTab } from './RulesTab'
import { AgentDefinitionsPage } from './AgentDefinitionsPage'
import './WorkflowsPage.css'

type ActiveTab = 'pipelines' | 'agents' | 'rules'
type EnabledFilter = boolean | null

const TABS = [
  { id: 'pipelines', label: 'Pipelines' },
  { id: 'agents', label: 'Agents' },
  { id: 'rules', label: 'Rules' },
]

const SCAFFOLD_PIPELINE_YAML = `name: new-pipeline
type: pipeline
description: ""
steps:
  - id: step-1
    exec: echo hello
`

export function WorkflowsPage() {
  const {
    workflows,
    isLoading,
    fetchWorkflows,
    createWorkflow,
    updateWorkflow,
    deleteWorkflow,
    duplicateWorkflow,
    toggleEnabled,
    importYaml,
    exportYaml,
    restoreWorkflow,
    installFromTemplate,
    installAllTemplates,
  } = useWorkflows()

  const [activeTab, setActiveTab] = useState<ActiveTab>('pipelines')
  const [searchText, setSearchText] = useState('')
  const [enabledFilter, setEnabledFilter] = useState<EnabledFilter>(null)
  const [showNewDropdown, setShowNewDropdown] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [editingWorkflow, setEditingWorkflow] = useState<WorkflowDetail | null>(null)
  const [yamlEditorWf, setYamlEditorWf] = useState<WorkflowDetail | null>(null)
  const [yamlContent, setYamlContent] = useState('')
  const [yamlLoading, setYamlLoading] = useState(false)
  const [sourceFilter, setSourceFilter] = useState<'installed' | 'templates' | 'deleted'>('installed')
  const [devMode, setDevMode] = useState(false)
  const [showRuleCreateModal, setShowRuleCreateModal] = useState(false)
  const [showAgentCreateForm, setShowAgentCreateForm] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [refreshing, setRefreshing] = useState(false)

  // Fetch dev_mode from admin status
  useEffect(() => {
    fetch('/admin/status')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.dev_mode) setDevMode(true)
      })
      .catch(() => {})
  }, [])

  // Filtering logic
  const filteredWorkflows = useMemo(() => {
    let result = workflows

    // Tab-level type filter
    if (activeTab === 'pipelines') {
      result = result.filter(w => w.workflow_type === 'pipeline')
    }

    // Source filter (exclusive)
    if (sourceFilter === 'installed') {
      result = result.filter(w => w.source === 'installed' && !w.deleted_at)
    } else if (sourceFilter === 'templates') {
      result = result.filter(w => w.source === 'template' && !w.deleted_at)
    } else if (sourceFilter === 'deleted') {
      result = result.filter(w => !!w.deleted_at)
    }

    // Enabled filter
    if (enabledFilter !== null) {
      result = result.filter(w => w.enabled === enabledFilter)
    }

    // Search filter
    if (searchText.trim()) {
      const q = searchText.toLowerCase()
      result = result.filter(w =>
        w.name.toLowerCase().includes(q) ||
        (w.description && w.description.toLowerCase().includes(q)) ||
        (w.tags && w.tags.some(t => t.toLowerCase().includes(q)))
      )
    }

    return result
  }, [workflows, activeTab, enabledFilter, searchText, sourceFilter])

  // Always fetch with include_deleted so the filter can work
  useEffect(() => {
    fetchWorkflows({ include_deleted: true })
  }, [fetchWorkflows])

  const handleDelete = useCallback(async (wf: WorkflowDetail) => {
    if (!window.confirm(`Delete "${wf.name}"?`)) return
    try {
      await deleteWorkflow(wf.id)
    } finally {
      fetchWorkflows({ include_deleted: true })
    }
  }, [deleteWorkflow, fetchWorkflows])

  const handleRestore = useCallback(async (wf: WorkflowDetail) => {
    try {
      await restoreWorkflow(wf.id)
    } finally {
      fetchWorkflows({ include_deleted: true })
    }
  }, [restoreWorkflow, fetchWorkflows])

  const handleDuplicate = useCallback(async (wf: WorkflowDetail) => {
    const newName = window.prompt('New name:', `${wf.name}-copy`)
    if (!newName) return
    await duplicateWorkflow(wf.id, newName)
  }, [duplicateWorkflow])

  const handleExport = useCallback(async (wf: WorkflowDetail) => {
    const yaml = await exportYaml(wf.id)
    if (yaml) {
      const blob = new Blob([yaml], { type: 'application/x-yaml' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${wf.name}.yaml`
      a.click()
      URL.revokeObjectURL(url)
    }
  }, [exportYaml])

  const handleYamlEdit = useCallback(async (wf: WorkflowDetail) => {
    setYamlLoading(true)
    setYamlEditorWf(wf)
    try {
      const yamlStr = await exportYaml(wf.id)
      setYamlContent(yamlStr || '')
    } catch (e) {
      console.error('Failed to export YAML:', e)
      setYamlContent('')
      window.alert(`Failed to export workflow YAML: ${e instanceof Error ? e.message : String(e)}`)
      setYamlEditorWf(null)
      return
    } finally {
      setYamlLoading(false)
    }
  }, [exportYaml])

  const handleYamlSave = useCallback(async () => {
    if (!yamlEditorWf) return
    let parsed: Record<string, unknown>
    try {
      parsed = yaml.load(yamlContent, { schema: yaml.JSON_SCHEMA }) as Record<string, unknown>
    } catch (e) {
      throw new Error(`Invalid YAML: ${e instanceof Error ? e.message : String(e)}`)
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Invalid YAML: expected an object')
    if (parsed.name !== undefined && typeof parsed.name !== 'string') throw new Error('Invalid YAML: "name" must be a string')
    if (typeof parsed.name === 'string' && !parsed.name.trim()) throw new Error('Invalid YAML: "name" must not be empty')
    if (parsed.description !== undefined && typeof parsed.description !== 'string') throw new Error('Invalid YAML: "description" must be a string')
    if (parsed.steps !== undefined && !Array.isArray(parsed.steps)) throw new Error('Invalid YAML: "steps" must be an array')
    await updateWorkflow(yamlEditorWf.id, {
      name: (parsed.name as string) || yamlEditorWf.name,
      description: (parsed.description as string) || undefined,
      definition_json: JSON.stringify(parsed),
    })
    setYamlEditorWf(null)
  }, [yamlEditorWf, yamlContent, updateWorkflow])

  const stepCount = useCallback((wf: WorkflowDetail) => {
    try {
      const data = JSON.parse(wf.definition_json)
      return (data.steps || []).length
    } catch {
      return 0
    }
  }, [])

  if (editingWorkflow) {
    return (
      <PipelineEditor
        pipeline={editingWorkflow}
        onBack={() => { setEditingWorkflow(null); fetchWorkflows() }}
        updateWorkflow={updateWorkflow}
        onExport={() => handleExport(editingWorkflow)}
      />
    )
  }

  return (
    <main className="workflows-page">
      {/* Toolbar */}
      <div className="workflows-toolbar">
        <div className="workflows-toolbar-left">
          <h2 className="workflows-toolbar-title">Workflows</h2>
        </div>
        <div className="workflows-toolbar-right">
          <input
            className="workflows-search"
            type="text"
            placeholder={`Search ${activeTab}...`}
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
          />
          <select
            className="workflows-source-select"
            value={sourceFilter}
            onChange={e => setSourceFilter(e.target.value as 'installed' | 'templates' | 'deleted')}
          >
            <option value="installed">Installed</option>
            <option value="templates">Templates</option>
            <option value="deleted">Deleted</option>
          </select>
          <button
            type="button"
            className={`workflows-toolbar-btn ${refreshing ? 'workflows-toolbar-btn--spinning' : ''}`}
            onClick={async () => {
              setRefreshing(true)
              if (activeTab === 'rules') {
                setRefreshKey(k => k + 1)
              } else {
                await fetchWorkflows({ include_deleted: true })
              }
              setTimeout(() => setRefreshing(false), 600)
            }}
            title="Refresh"
            disabled={isLoading}
          >
            &#x21bb;
          </button>
          {activeTab === 'pipelines' && (
            <div className="workflows-new-wrapper">
              <button
                type="button"
                className="workflows-new-btn"
                onClick={() => setShowNewDropdown(!showNewDropdown)}
              >
                + Pipeline
              </button>
              {showNewDropdown && (
                <div className="workflows-new-dropdown">
                  <button
                    type="button"
                    className="workflows-new-dropdown-item"
                    onClick={async () => {
                      setShowNewDropdown(false)
                      const scaffoldDef = { name: 'new-pipeline', type: 'pipeline', description: '', steps: [{ id: 'step-1', exec: 'echo hello' }] }
                      const result = await createWorkflow({
                        name: 'new-pipeline',
                        definition_json: JSON.stringify(scaffoldDef),
                        workflow_type: 'pipeline',
                      })
                      if (result) setEditingWorkflow(result)
                    }}
                  >
                    Builder
                  </button>
                  <button
                    type="button"
                    className="workflows-new-dropdown-item"
                    onClick={() => {
                      setShowNewDropdown(false)
                      setShowImportModal(true)
                    }}
                  >
                    YAML
                  </button>
                </div>
              )}
            </div>
          )}
          {activeTab === 'agents' && (
            <button
              type="button"
              className="workflows-new-btn"
              onClick={() => setShowAgentCreateForm(prev => !prev)}
            >
              + Agent
            </button>
          )}
          {activeTab === 'rules' && (
            <button
              type="button"
              className="workflows-new-btn"
              onClick={() => setShowRuleCreateModal(true)}
            >
              + Rule
            </button>
          )}
        </div>
      </div>

      {/* Tab bar */}
      <TabBar
        tabs={TABS}
        activeTab={activeTab}
        onTabChange={(id) => setActiveTab(id as ActiveTab)}
      />

      {/* Rules tab */}
      {activeTab === 'rules' && (
        <RulesTab
          searchText={searchText}
          sourceFilter={sourceFilter}
          devMode={devMode}
          showCreateModal={showRuleCreateModal}
          onCloseCreateModal={() => setShowRuleCreateModal(false)}
          refreshKey={refreshKey}
        />
      )}

      {/* Pipelines tab */}
      {activeTab === 'pipelines' && (
        <>
          {/* Filter chips */}
          <div className="workflows-filter-bar">
            <div className="workflows-filter-chips">
              {/* Enabled filters */}
              <button
                type="button"
                className={`workflows-filter-chip ${enabledFilter === true ? 'workflows-filter-chip--active' : ''}`}
                onClick={() => setEnabledFilter(enabledFilter === true ? null : true)}
              >
                enabled
              </button>
              <button
                type="button"
                className={`workflows-filter-chip ${enabledFilter === false ? 'workflows-filter-chip--active' : ''}`}
                onClick={() => setEnabledFilter(enabledFilter === false ? null : false)}
              >
                disabled
              </button>
            </div>
            {sourceFilter === 'templates' && (
              <button
                type="button"
                className="workflows-toolbar-btn"
                onClick={() => installAllTemplates('pipeline')}
              >
                Install All
              </button>
            )}
          </div>

          {/* Card grid */}
          <div className="workflows-content">
            {isLoading ? (
              <div className="workflows-loading">Loading...</div>
            ) : filteredWorkflows.length === 0 ? (
              <div className="workflows-empty">No {activeTab} match the current filters.</div>
            ) : (
              <div className="workflows-grid">
                {filteredWorkflows.map(wf => {
                  const isTemplate = wf.source === 'template'
                  const cardClass = [
                    'workflows-card',
                    wf.deleted_at ? 'workflows-card--deleted' : '',
                    isTemplate ? 'workflows-card--template' : '',
                  ].filter(Boolean).join(' ')

                  return (
                    <div className={cardClass} key={wf.id}>
                      <div className="workflows-card-header">
                        <span className={`workflows-card-name${wf.deleted_at ? ' workflows-card-name--deleted' : ''}`}>{wf.name}</span>
                        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                          <span className={`workflows-card-type workflows-card-type--${wf.workflow_type}`}>
                            {wf.workflow_type}
                          </span>
                        </div>
                      </div>

                      {wf.description && (
                        <div className="workflows-card-desc">{wf.description}</div>
                      )}

                      <div className="workflows-card-badges">
                        <span className="workflows-card-badge workflows-card-badge--source">
                          {wf.source}
                        </span>
                        <span className="workflows-card-badge workflows-card-badge--priority">
                          P{wf.priority}
                        </span>
                        <span className="workflows-card-badge">
                          {stepCount(wf)} step{stepCount(wf) !== 1 ? 's' : ''}
                        </span>
                        <span className="workflows-card-badge">v{wf.version}</span>
                        {wf.tags && wf.tags.map(tag => (
                          <span className="workflows-card-badge" key={tag}>{tag}</span>
                        ))}
                      </div>

                      <div className="workflows-card-footer">
                        {wf.deleted_at ? (
                          <div className="workflows-card-actions">
                            <button
                              type="button"
                              className="workflows-action-btn workflows-action-btn--restore"
                              onClick={() => handleRestore(wf)}
                              title="Restore this workflow"
                            >
                              Restore
                            </button>
                          </div>
                        ) : isTemplate ? (
                          <>
                            <div />
                            <div className="workflows-card-actions">
                              {devMode ? (
                                <>
                                  <button type="button" className="workflows-action-btn" onClick={() => handleYamlEdit(wf)} title="Edit as YAML">YAML</button>
                                  <button type="button" className="workflows-action-btn" onClick={() => setEditingWorkflow(wf)} title="Edit pipeline steps">Edit</button>
                                  <button type="button" className="workflows-action-icon" onClick={() => handleDuplicate(wf)} title="Duplicate" aria-label="Duplicate workflow">
                                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="5.5" y="5.5" width="9" height="9" rx="1.5" /><path d="M10.5 5.5V2.5a1 1 0 0 0-1-1h-7a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h3" /></svg>
                                  </button>
                                  <button type="button" className="workflows-action-icon" onClick={() => handleExport(wf)} title="Download YAML" aria-label="Download workflow as YAML">
                                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v9m0 0L5 8m3 3 3-3M2.5 12.5v1a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-1" /></svg>
                                  </button>
                                  <button type="button" className="workflows-action-icon workflows-action-icon--danger" onClick={() => handleDelete(wf)} title="Delete" aria-label="Delete workflow">
                                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2.5 4.5h11M5.5 4.5V3a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v1.5M6.5 7v4.5M9.5 7v4.5" /><path d="M3.5 4.5 4 13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l.5-8.5" /></svg>
                                  </button>
                                </>
                              ) : (
                                <>
                                  <button type="button" className="workflows-action-btn" onClick={() => installFromTemplate(wf.id)} title="Create an installed copy">Install</button>
                                  <button type="button" className="workflows-action-icon" onClick={() => handleExport(wf)} title="Download YAML" aria-label="Download workflow as YAML">
                                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v9m0 0L5 8m3 3 3-3M2.5 12.5v1a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-1" /></svg>
                                  </button>
                                </>
                              )}
                            </div>
                          </>
                        ) : (
                          <>
                            <div
                              className="workflows-toggle"
                              onClick={() => toggleEnabled(wf.id)}
                            >
                              <div className={`workflows-toggle-track ${wf.enabled ? 'workflows-toggle-track--on' : ''}`}>
                                <div className="workflows-toggle-knob" />
                              </div>
                              <span>{wf.enabled ? 'On' : 'Off'}</span>
                            </div>

                            <div className="workflows-card-actions">
                              <button type="button" className="workflows-action-btn" onClick={() => handleYamlEdit(wf)} title="Edit as YAML">YAML</button>
                              {wf.workflow_type === 'pipeline' && (
                                <button type="button" className="workflows-action-btn" onClick={() => setEditingWorkflow(wf)} title="Edit pipeline steps">Edit</button>
                              )}
                              <button type="button" className="workflows-action-icon" onClick={() => handleDuplicate(wf)} title="Duplicate" aria-label="Duplicate workflow">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="5.5" y="5.5" width="9" height="9" rx="1.5" /><path d="M10.5 5.5V2.5a1 1 0 0 0-1-1h-7a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h3" /></svg>
                              </button>
                              <button type="button" className="workflows-action-icon" onClick={() => handleExport(wf)} title="Download YAML" aria-label="Download workflow as YAML">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v9m0 0L5 8m3 3 3-3M2.5 12.5v1a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-1" /></svg>
                              </button>
                              <button type="button" className="workflows-action-icon workflows-action-icon--danger" onClick={() => handleDelete(wf)} title="Delete" aria-label="Delete workflow">
                                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2.5 4.5h11M5.5 4.5V3a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v1.5M6.5 7v4.5M9.5 7v4.5" /><path d="M3.5 4.5 4 13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l.5-8.5" /></svg>
                              </button>
                            </div>
                          </>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </>
      )}

      {/* Agents tab */}
      {activeTab === 'agents' && (
        <AgentDefinitionsPage
          searchText={searchText}
          sourceFilter={sourceFilter}
          devMode={devMode}
          showCreateForm={showAgentCreateForm}
          onToggleCreateForm={setShowAgentCreateForm}
        />
      )}

      {/* New pipeline from YAML modal */}
      {showImportModal && (
        <NewPipelineYamlModal
          onClose={() => setShowImportModal(false)}
          onImport={importYaml}
        />
      )}

      {/* YAML editor modal */}
      {yamlEditorWf && (
        <YamlEditorModal
          workflowName={yamlEditorWf.name}
          yamlContent={yamlContent}
          loading={yamlLoading}
          onChange={setYamlContent}
          onSave={handleYamlSave}
          onClose={() => setYamlEditorWf(null)}
        />
      )}
    </main>
  )
}

function NewPipelineYamlModal({ onClose, onImport }: {
  onClose: () => void
  onImport: (yaml: string) => Promise<WorkflowDetail | null>
}) {
  const [content, setContent] = useState(SCAFFOLD_PIPELINE_YAML)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isDirty, setIsDirty] = useState(false)

  const wrappedOnChange = useCallback((c: string) => { setIsDirty(true); setContent(c) }, [])

  const handleSubmit = async () => {
    if (!content.trim()) return
    setError(null)
    setSubmitting(true)
    try {
      const result = await onImport(content)
      if (result) onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to create pipeline')
    } finally {
      setSubmitting(false)
    }
  }

  const handleClose = () => {
    if (isDirty && !window.confirm('You have unsaved changes. Discard them?')) return
    onClose()
  }

  return (
    <div className="workflows-modal-overlay" onClick={handleClose}>
      <div className="workflows-yaml-modal" onClick={e => e.stopPropagation()}>
        <div className="workflows-yaml-header">
          <h3>New Pipeline — YAML</h3>
          <div className="workflows-yaml-header-actions">
            {error && <span className="workflows-yaml-error">{error}</span>}
            <button type="button" className="workflows-modal-cancel" onClick={handleClose}>Cancel</button>
            <button
              type="button"
              className="workflows-modal-submit"
              onClick={handleSubmit}
              disabled={!content.trim() || submitting}
            >
              {submitting ? 'Creating...' : 'Create'}
            </button>
          </div>
        </div>
        <div className="workflows-yaml-editor">
          <CodeMirrorEditor
            content={content}
            language="yaml"
            onChange={wrappedOnChange}
            onSave={handleSubmit}
          />
        </div>
      </div>
    </div>
  )
}

export function YamlEditorModal({ workflowName, yamlContent, loading, onChange, onSave, onClose }: {
  workflowName: string
  yamlContent: string
  loading: boolean
  onChange: (content: string) => void
  onSave: () => Promise<void>
  onClose: () => void
}) {
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [isDirty, setIsDirty] = useState(false)
  const wrappedOnChange = useCallback((content: string) => { setIsDirty(true); onChange(content) }, [onChange])

  const handleSave = async () => {
    setError(null)
    setSaving(true)
    try {
      await onSave()
      setIsDirty(false)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invalid YAML')
    } finally {
      setSaving(false)
    }
  }

  const handleClose = () => {
    if (isDirty && !window.confirm('You have unsaved changes. Discard them?')) return
    onClose()
  }

  return (
    <div className="workflows-modal-overlay" onClick={handleClose}>
      <div className="workflows-yaml-modal" onClick={e => e.stopPropagation()}>
        <div className="workflows-yaml-header">
          <h3>Edit YAML — {workflowName}</h3>
          <div className="workflows-yaml-header-actions">
            {error && <span className="workflows-yaml-error">{error}</span>}
            <button type="button" className="workflows-modal-cancel" onClick={handleClose}>Cancel</button>
            <button
              type="button"
              className="workflows-modal-submit"
              onClick={handleSave}
              disabled={saving || loading}
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        </div>
        <div className="workflows-yaml-editor">
          {loading ? (
            <div className="workflows-loading">Loading YAML...</div>
          ) : (
            <CodeMirrorEditor
              content={yamlContent}
              language="yaml"
              onChange={wrappedOnChange}
              onSave={handleSave}
            />
          )}
        </div>
      </div>
    </div>
  )
}

