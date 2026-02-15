import { useState, useCallback, useMemo } from 'react'
import { useWorkflows } from '../hooks/useWorkflows'
import type { WorkflowDetail } from '../hooks/useWorkflows'
import { WorkflowBuilder, type WorkflowSettings, type WorkflowVariable, type WorkflowRule } from './WorkflowBuilder'
import { definitionToFlow, flowToDefinition, type FlowNode } from './workflowSerialization'
import type { Node, Edge } from '@xyflow/react'
import './WorkflowsPage.css'

type OverviewFilter = 'total' | 'workflows' | 'pipelines' | 'active' | null
type TypeFilter = 'workflow' | 'pipeline' | null
type SourceFilter = string | null
type EnabledFilter = boolean | null

const SCAFFOLD_WORKFLOW = JSON.stringify(
  {
    name: '',
    description: '',
    version: '1.0',
    steps: [{ name: 'work', allowed_tools: 'all' }],
  },
  null,
  2,
)

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
    workflowCount,
    pipelineCount,
    activeCount,
    fetchWorkflows,
    createWorkflow,
    updateWorkflow,
    deleteWorkflow,
    duplicateWorkflow,
    toggleEnabled,
    importYaml,
    exportYaml,
  } = useWorkflows()

  const [searchText, setSearchText] = useState('')
  const [overviewFilter, setOverviewFilter] = useState<OverviewFilter>(null)
  const [typeFilter, setTypeFilter] = useState<TypeFilter>(null)
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>(null)
  const [enabledFilter, setEnabledFilter] = useState<EnabledFilter>(null)
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [createType, setCreateType] = useState<'workflow' | 'pipeline'>('workflow')
  const [showImportModal, setShowImportModal] = useState(false)
  const [editingWorkflow, setEditingWorkflow] = useState<WorkflowDetail | null>(null)

  // Unique sources for filter chips
  const sources = useMemo(() => {
    const set = new Set<string>()
    workflows.forEach(w => set.add(w.source))
    return Array.from(set).sort()
  }, [workflows])

  // Filtering logic
  const filteredWorkflows = useMemo(() => {
    let result = workflows

    // Overview filter
    if (overviewFilter === 'workflows') {
      result = result.filter(w => w.workflow_type === 'workflow')
    } else if (overviewFilter === 'pipelines') {
      result = result.filter(w => w.workflow_type === 'pipeline')
    } else if (overviewFilter === 'active') {
      result = result.filter(w => w.enabled)
    }

    // Type chip filter
    if (typeFilter) {
      result = result.filter(w => w.workflow_type === typeFilter)
    }

    // Source chip filter
    if (sourceFilter) {
      result = result.filter(w => w.source === sourceFilter)
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
  }, [workflows, overviewFilter, typeFilter, sourceFilter, enabledFilter, searchText])

  const handleDelete = useCallback(async (wf: WorkflowDetail) => {
    if (!window.confirm(`Delete "${wf.name}"?`)) return
    await deleteWorkflow(wf.id)
  }, [deleteWorkflow])

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

  const handleToggleOverview = useCallback((filter: OverviewFilter) => {
    setOverviewFilter(prev => prev === filter ? null : filter)
  }, [])

  const stepCount = useCallback((wf: WorkflowDetail) => {
    try {
      const data = JSON.parse(wf.definition_json)
      return (data.steps || []).length
    } catch {
      return 0
    }
  }, [])

  const handleSave = useCallback(async (nodes: Node[], edges: Edge[], name: string) => {
    if (!editingWorkflow) return
    const isPipeline = editingWorkflow.workflow_type === 'pipeline'
    const { definition, canvasJson } = flowToDefinition(nodes as FlowNode[], edges, isPipeline)
    // Merge non-canvas fields from original definition
    try {
      const origDef = JSON.parse(editingWorkflow.definition_json)
      // Preserve top-level fields not managed by the canvas
      for (const key of ['name', 'description', 'version', 'type', 'enabled', 'priority', 'sources', 'settings', 'variables', 'session_variables', 'imports', 'inputs', 'outputs', 'webhooks', 'expose_as_tool']) {
        if (key in origDef && !(key in definition)) {
          definition[key] = origDef[key]
        }
      }
    } catch {
      // ignore parse errors
    }
    definition.name = name
    await updateWorkflow(editingWorkflow.id, {
      name,
      definition_json: JSON.stringify(definition),
      canvas_json: canvasJson,
    })
    // Update local editing state with new data
    setEditingWorkflow((prev) => prev ? {
      ...prev,
      name,
      definition_json: JSON.stringify(definition),
      canvas_json: canvasJson,
    } : null)
  }, [editingWorkflow, updateWorkflow])

  const handleSettingsSave = useCallback(async (settings: WorkflowSettings) => {
    if (!editingWorkflow) return
    // Update definition_json with variables, rules, exit_condition
    let defJson = editingWorkflow.definition_json
    try {
      const def = JSON.parse(defJson)
      // Variables -> object
      if (settings.variables.length > 0) {
        const vars: Record<string, string> = {}
        for (const v of settings.variables) vars[v.key] = v.value
        def.variables = vars
      } else {
        delete def.variables
      }
      // Rules
      if (settings.rules.length > 0) {
        def.rules = settings.rules.map((r) => ({
          name: r.name,
          when: r.when,
          action: r.action,
          message: r.message || undefined,
        }))
      } else {
        delete def.rules
      }
      // Exit condition
      if (settings.exitCondition) {
        def.exit_condition = settings.exitCondition
      } else {
        delete def.exit_condition
      }
      defJson = JSON.stringify(def)
    } catch {
      // ignore parse errors
    }
    await updateWorkflow(editingWorkflow.id, {
      name: settings.name,
      description: settings.description,
      enabled: settings.enabled,
      sources: settings.sources,
      definition_json: defJson,
    })
    setEditingWorkflow((prev) => prev ? {
      ...prev,
      name: settings.name,
      description: settings.description,
      enabled: settings.enabled,
      priority: settings.priority,
      sources: settings.sources,
      definition_json: defJson,
    } : null)
  }, [editingWorkflow, updateWorkflow])

  if (editingWorkflow) {
    const wfType = (editingWorkflow.workflow_type as 'workflow' | 'pipeline') || 'workflow'
    let initDef: Record<string, unknown> = {}
    try {
      initDef = JSON.parse(editingWorkflow.definition_json)
    } catch {
      // empty def fallback
    }
    const { nodes: initNodes, edges: initEdges } = definitionToFlow(initDef, editingWorkflow.canvas_json)

    // Extract variables, rules, exit_condition from definition
    const defVariables: WorkflowVariable[] = initDef.variables
      ? Object.entries(initDef.variables as Record<string, string>).map(([key, value]) => ({ key, value: String(value) }))
      : []
    const defRules: WorkflowRule[] = Array.isArray(initDef.rules)
      ? (initDef.rules as Record<string, unknown>[]).map((r) => ({
          name: (r.name as string) ?? '',
          when: (r.when as string) ?? '',
          action: (r.action as string) ?? 'block',
          message: (r.message as string) ?? '',
        }))
      : []
    const defExitCondition = (initDef.exit_condition as string) ?? ''

    return (
      <WorkflowBuilder
        workflowId={editingWorkflow.id}
        workflowName={editingWorkflow.name}
        workflowType={wfType}
        description={editingWorkflow.description ?? ''}
        enabled={editingWorkflow.enabled}
        priority={editingWorkflow.priority}
        sources={editingWorkflow.sources}
        variables={defVariables}
        rules={defRules}
        exitCondition={defExitCondition}
        initialNodes={initNodes}
        initialEdges={initEdges}
        onBack={() => { setEditingWorkflow(null); fetchWorkflows() }}
        onSave={handleSave}
        onExport={() => handleExport(editingWorkflow)}
        onSettingsSave={handleSettingsSave}
      />
    )
  }

  return (
    <main className="workflows-page">
      {/* Toolbar */}
      <div className="workflows-toolbar">
        <div className="workflows-toolbar-left">
          <h2 className="workflows-toolbar-title">Workflows</h2>
          <span className="workflows-toolbar-count">{workflows.length}</span>
        </div>
        <div className="workflows-toolbar-right">
          <input
            className="workflows-search"
            type="text"
            placeholder="Search workflows..."
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
          />
          <button
            type="button"
            className="workflows-toolbar-btn"
            onClick={() => fetchWorkflows()}
            title="Refresh"
            disabled={isLoading}
          >
            &#x21bb;
          </button>
          <button
            type="button"
            className="workflows-toolbar-btn"
            onClick={() => setShowImportModal(true)}
          >
            Import
          </button>
          <button
            type="button"
            className="workflows-new-btn"
            onClick={() => { setCreateType('workflow'); setShowCreateModal(true) }}
          >
            + Workflow
          </button>
          <button
            type="button"
            className="workflows-new-btn"
            onClick={() => { setCreateType('pipeline'); setShowCreateModal(true) }}
          >
            + Pipeline
          </button>
        </div>
      </div>

      {/* Overview cards */}
      <div className="workflows-overview">
        <div
          className={`workflows-overview-card ${overviewFilter === 'total' ? 'workflows-overview-card--active' : ''}`}
          onClick={() => handleToggleOverview('total')}
        >
          <div className="workflows-overview-value">{workflows.length}</div>
          <div className="workflows-overview-label">Total</div>
        </div>
        <div
          className={`workflows-overview-card ${overviewFilter === 'workflows' ? 'workflows-overview-card--active' : ''}`}
          onClick={() => handleToggleOverview('workflows')}
        >
          <div className="workflows-overview-value">{workflowCount}</div>
          <div className="workflows-overview-label">Workflows</div>
        </div>
        <div
          className={`workflows-overview-card ${overviewFilter === 'pipelines' ? 'workflows-overview-card--active' : ''}`}
          onClick={() => handleToggleOverview('pipelines')}
        >
          <div className="workflows-overview-value">{pipelineCount}</div>
          <div className="workflows-overview-label">Pipelines</div>
        </div>
        <div
          className={`workflows-overview-card ${overviewFilter === 'active' ? 'workflows-overview-card--active' : ''}`}
          onClick={() => handleToggleOverview('active')}
        >
          <div className="workflows-overview-value">{activeCount}</div>
          <div className="workflows-overview-label">Active</div>
        </div>
      </div>

      {/* Filter chips */}
      <div className="workflows-filter-bar">
        <div className="workflows-filter-chips">
          {/* Type filters */}
          <button
            type="button"
            className={`workflows-filter-chip ${typeFilter === 'workflow' ? 'workflows-filter-chip--active' : ''}`}
            onClick={() => setTypeFilter(typeFilter === 'workflow' ? null : 'workflow')}
          >
            workflow
          </button>
          <button
            type="button"
            className={`workflows-filter-chip ${typeFilter === 'pipeline' ? 'workflows-filter-chip--active' : ''}`}
            onClick={() => setTypeFilter(typeFilter === 'pipeline' ? null : 'pipeline')}
          >
            pipeline
          </button>

          {/* Source filters */}
          {sources.map(s => (
            <button
              type="button"
              key={s}
              className={`workflows-filter-chip ${sourceFilter === s ? 'workflows-filter-chip--active' : ''}`}
              onClick={() => setSourceFilter(sourceFilter === s ? null : s)}
            >
              {s}
            </button>
          ))}

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
      </div>

      {/* Card grid */}
      <div className="workflows-content">
        {isLoading ? (
          <div className="workflows-loading">Loading...</div>
        ) : filteredWorkflows.length === 0 ? (
          <div className="workflows-empty">No workflows match the current filters.</div>
        ) : (
          <div className="workflows-grid">
            {filteredWorkflows.map(wf => (
              <div className="workflows-card" key={wf.id}>
                <div className="workflows-card-header">
                  <span className="workflows-card-name">{wf.name}</span>
                  <span className={`workflows-card-type workflows-card-type--${wf.workflow_type}`}>
                    {wf.workflow_type}
                  </span>
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
                    <button
                      type="button"
                      className="workflows-action-btn"
                      onClick={() => setEditingWorkflow(wf)}
                      title="Edit in visual builder"
                    >
                      Edit
                    </button>
                    <button
                      type="button"
                      className="workflows-action-btn"
                      onClick={() => handleDuplicate(wf)}
                      title="Duplicate"
                    >
                      Dup
                    </button>
                    <button
                      type="button"
                      className="workflows-action-btn"
                      onClick={() => handleExport(wf)}
                      title="Export YAML"
                    >
                      YAML
                    </button>
                    <button
                      type="button"
                      className="workflows-action-btn workflows-action-btn--danger"
                      onClick={() => handleDelete(wf)}
                      title="Delete"
                    >
                      Del
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Create modal */}
      {showCreateModal && (
        <CreateModal
          type={createType}
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
    </main>
  )
}

function CreateModal({ type, onClose, onCreate }: {
  type: 'workflow' | 'pipeline'
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
  const scaffold = type === 'pipeline' ? SCAFFOLD_PIPELINE : SCAFFOLD_WORKFLOW
  const [definitionJson, setDefinitionJson] = useState(scaffold)
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
        workflow_type: type,
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
        <h3>New {type === 'pipeline' ? 'Pipeline' : 'Workflow'}</h3>
        <div className="workflows-modal-field">
          <label>Name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder={`my-${type}`}
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
