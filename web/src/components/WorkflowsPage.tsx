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

const SCAFFOLD_PIPELINE = JSON.stringify(
  {
    name: '',
    type: 'pipeline',
    description: '',
    steps: [{ id: 'step-1', exec: 'echo hello' }],
  },
  null,
  2,
)

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
    useAsTemplate,
    useAllBundledAsTemplates,
  } = useWorkflows()

  const [activeTab, setActiveTab] = useState<ActiveTab>('pipelines')
  const [searchText, setSearchText] = useState('')
  const [enabledFilter, setEnabledFilter] = useState<EnabledFilter>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [editingWorkflow, setEditingWorkflow] = useState<WorkflowDetail | null>(null)
  const [yamlEditorWf, setYamlEditorWf] = useState<WorkflowDetail | null>(null)
  const [yamlContent, setYamlContent] = useState('')
  const [yamlLoading, setYamlLoading] = useState(false)
  const [showDeleted, setShowDeleted] = useState(false)
  const [showBundled, setShowBundled] = useState(false)
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

    // Hide bundled items unless toggled on
    if (!showBundled) {
      result = result.filter(w => w.source !== 'bundled')
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
  }, [workflows, activeTab, enabledFilter, searchText, showBundled])

  // Re-fetch when showDeleted changes
  useEffect(() => {
    fetchWorkflows({ include_deleted: showDeleted })
  }, [fetchWorkflows, showDeleted])

  const handleDelete = useCallback(async (wf: WorkflowDetail) => {
    if (!window.confirm(`Delete "${wf.name}"?`)) return
    try {
      await deleteWorkflow(wf.id)
    } finally {
      fetchWorkflows({ include_deleted: showDeleted })
    }
  }, [deleteWorkflow, fetchWorkflows, showDeleted])

  const handleRestore = useCallback(async (wf: WorkflowDetail) => {
    try {
      await restoreWorkflow(wf.id)
    } finally {
      fetchWorkflows({ include_deleted: showDeleted })
    }
  }, [restoreWorkflow, fetchWorkflows, showDeleted])

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
          <label className="workflows-show-deleted">
            <input
              type="checkbox"
              checked={showBundled}
              onChange={e => setShowBundled(e.target.checked)}
            />
            Bundled
          </label>
          <label className="workflows-show-deleted">
            <input
              type="checkbox"
              checked={showDeleted}
              onChange={e => setShowDeleted(e.target.checked)}
            />
            Deleted
          </label>
          <button
            type="button"
            className={`workflows-toolbar-btn ${refreshing ? 'workflows-toolbar-btn--spinning' : ''}`}
            onClick={async () => {
              setRefreshing(true)
              if (activeTab === 'rules') {
                setRefreshKey(k => k + 1)
              } else {
                await fetchWorkflows({ include_deleted: showDeleted })
              }
              setTimeout(() => setRefreshing(false), 600)
            }}
            title="Refresh"
            disabled={isLoading}
          >
            &#x21bb;
          </button>
          {activeTab === 'pipelines' && (
            <button
              type="button"
              className="workflows-new-btn"
              onClick={() => setShowCreateModal(true)}
            >
              + Pipeline
            </button>
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
          showDeleted={showDeleted}
          showBundled={showBundled}
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
            {showBundled && (
              <button
                type="button"
                className="workflows-toolbar-btn"
                onClick={() => useAllBundledAsTemplates('pipeline')}
              >
                Use All as Templates
              </button>
            )}
            <button
              type="button"
              className="workflows-toolbar-btn"
              onClick={() => setShowImportModal(true)}
            >
              Import
            </button>
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
                  const isBundled = wf.source === 'bundled'
                  const cardClass = [
                    'workflows-card',
                    wf.deleted_at ? 'workflows-card--deleted' : '',
                    isBundled ? 'workflows-card--bundled' : '',
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
                        ) : isBundled ? (
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
                                  <button type="button" className="workflows-action-btn" onClick={() => useAsTemplate(wf.id)} title="Create a custom copy">Use as Template</button>
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
          showDeleted={showDeleted}
          showBundled={showBundled}
          devMode={devMode}
          showCreateForm={showAgentCreateForm}
          onToggleCreateForm={setShowAgentCreateForm}
        />
      )}

      {/* Create modal */}
      {showCreateModal && (
        <CreateModal
          onClose={() => setShowCreateModal(false)}
          onCreate={createWorkflow}
        />
      )}

      {/* Import modal */}
      {showImportModal && (
        <ImportModal
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

function CreateModal({ onClose, onCreate }: {
  onClose: () => void
  onCreate: (params: {
    name: string
    definition_json: string
    workflow_type?: string
    description?: string
    priority?: number
  }) => Promise<WorkflowDetail | null>
}) {
  const [name, setName] = useState('')
  const [description, setDescription] = useState('')
  const [definitionJson, setDefinitionJson] = useState(SCAFFOLD_PIPELINE)
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    if (!name.trim()) return
    setSubmitting(true)
    // Inject name into definition JSON
    try {
      const data = JSON.parse(definitionJson)
      data.name = name.trim()
      if (description.trim()) data.description = description.trim()
      await onCreate({
        name: name.trim(),
        definition_json: JSON.stringify(data),
        workflow_type: 'pipeline',
        description: description.trim() || undefined,
      })
      onClose()
    } catch {
      // Invalid JSON - keep modal open
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="workflows-modal-overlay" onClick={onClose}>
      <div className="workflows-modal" onClick={e => e.stopPropagation()}>
        <h3>New Pipeline</h3>
        <div className="workflows-modal-field">
          <label>Name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="my-pipeline"
            autoFocus
          />
        </div>
        <div className="workflows-modal-field">
          <label>Description</label>
          <input
            type="text"
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Optional description"
          />
        </div>
        <div className="workflows-modal-field">
          <label>Definition JSON</label>
          <textarea
            value={definitionJson}
            onChange={e => setDefinitionJson(e.target.value)}
            rows={10}
          />
        </div>
        <div className="workflows-modal-actions">
          <button type="button" className="workflows-modal-cancel" onClick={onClose}>Cancel</button>
          <button
            type="button"
            className="workflows-modal-submit"
            onClick={handleSubmit}
            disabled={!name.trim() || submitting}
          >
            {submitting ? 'Creating...' : 'Create'}
          </button>
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

function ImportModal({ onClose, onImport }: {
  onClose: () => void
  onImport: (yaml: string) => Promise<WorkflowDetail | null>
}) {
  const [yamlContent, setYamlContent] = useState('')
  const [submitting, setSubmitting] = useState(false)

  const handleSubmit = async () => {
    if (!yamlContent.trim()) return
    setSubmitting(true)
    const result = await onImport(yamlContent)
    setSubmitting(false)
    if (result) onClose()
  }

  return (
    <div className="workflows-modal-overlay" onClick={onClose}>
      <div className="workflows-modal" onClick={e => e.stopPropagation()}>
        <h3>Import Workflow YAML</h3>
        <div className="workflows-modal-field">
          <label>YAML Content</label>
          <textarea
            value={yamlContent}
            onChange={e => setYamlContent(e.target.value)}
            rows={15}
            placeholder="Paste workflow YAML here..."
            autoFocus
          />
        </div>
        <div className="workflows-modal-actions">
          <button type="button" className="workflows-modal-cancel" onClick={onClose}>Cancel</button>
          <button
            type="button"
            className="workflows-modal-submit"
            onClick={handleSubmit}
            disabled={!yamlContent.trim() || submitting}
          >
            {submitting ? 'Importing...' : 'Import'}
          </button>
        </div>
      </div>
    </div>
  )
}
