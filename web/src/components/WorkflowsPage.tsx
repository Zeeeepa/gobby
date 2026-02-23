import { useState, useEffect, useCallback } from 'react'
import { TabBar } from './TabBar'
import { RulesTab } from './RulesTab'
import { AgentsTab } from './AgentsTab'
import { PipelinesTab } from './PipelinesTab'
import { CodeMirrorEditor } from './CodeMirrorEditor'
import './WorkflowsPage.css'

type ActiveTab = 'pipelines' | 'agents' | 'rules'

const TABS = [
  { id: 'pipelines', label: 'Pipelines' },
  { id: 'agents', label: 'Agents' },
  { id: 'rules', label: 'Rules' },
]

export function WorkflowsPage({ projectId }: { projectId?: string }) {
  const [activeTab, setActiveTab] = useState<ActiveTab>('pipelines')
  const [searchText, setSearchText] = useState('')
  const [sourceFilter, setSourceFilter] = useState<'installed' | 'project' | 'templates' | 'deleted'>('installed')
  const [devMode, setDevMode] = useState(false)
  const [showRuleCreateModal, setShowRuleCreateModal] = useState(false)
  const [showAgentCreateForm, setShowAgentCreateForm] = useState(false)
  const [showPipelineCreateDropdown, setShowPipelineCreateDropdown] = useState(false)
  const [refreshKey, setRefreshKey] = useState(0)
  const [refreshing, setRefreshing] = useState(false)
  const [hideGobby, setHideGobby] = useState(false)

  // Fetch dev_mode from admin status
  useEffect(() => {
    fetch('/admin/status')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.dev_mode) setDevMode(true)
      })
      .catch(() => {})
  }, [])

  const handleRefresh = useCallback(async () => {
    setRefreshing(true)
    setRefreshKey(k => k + 1)
    setTimeout(() => setRefreshing(false), 600)
  }, [])

  return (
    <main className="workflows-page">
      {/* Title row */}
      <div className="workflows-toolbar">
        <div className="workflows-toolbar-left">
          <h2 className="workflows-toolbar-title">Workflows</h2>
        </div>
        <div className="workflows-toolbar-right">
          {activeTab === 'pipelines' && (
            <div className="workflows-new-wrapper">
              <button
                type="button"
                className="workflows-new-btn"
                onClick={() => setShowPipelineCreateDropdown(!showPipelineCreateDropdown)}
              >
                + Pipeline
              </button>
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

      {/* Filter bar */}
      <div className="workflows-filter-row">
        <input
          className="workflows-search"
          type="text"
          placeholder={`Search ${activeTab}...`}
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
        />
        <div className="rules-enforcement-toggle" onClick={() => setHideGobby(!hideGobby)}>
          <div className={`workflows-toggle-track ${hideGobby ? 'workflows-toggle-track--on' : ''}`}>
            <div className="workflows-toggle-knob" />
          </div>
          <span>Hide Built-in</span>
        </div>
        <select
          className="workflows-source-select"
          value={sourceFilter}
          onChange={e => setSourceFilter(e.target.value as 'installed' | 'project' | 'templates' | 'deleted')}
        >
          <option value="installed">Installed</option>
          <option value="project">Installed (Project)</option>
          <option value="templates">Templates</option>
          <option value="deleted">Deleted</option>
        </select>
        <button
          type="button"
          className={`workflows-toolbar-btn ${refreshing ? 'workflows-toolbar-btn--spinning' : ''}`}
          onClick={handleRefresh}
          title="Refresh"
        >
          &#x21bb;
        </button>
      </div>

      {/* Tab bar */}
      <TabBar
        tabs={TABS}
        activeTab={activeTab}
        onTabChange={(id) => setActiveTab(id as ActiveTab)}
      />

      {/* Tab content */}
      {activeTab === 'pipelines' && (
        <PipelinesTab
          searchText={searchText}
          sourceFilter={sourceFilter}
          devMode={devMode}
          showCreateDropdown={showPipelineCreateDropdown}
          onCloseCreateDropdown={() => setShowPipelineCreateDropdown(false)}
          refreshKey={refreshKey}
          projectId={projectId}
          hideGobby={hideGobby}
        />
      )}

      {activeTab === 'agents' && (
        <AgentsTab
          searchText={searchText}
          sourceFilter={sourceFilter}
          devMode={devMode}
          showCreateForm={showAgentCreateForm}
          onToggleCreateForm={setShowAgentCreateForm}
          refreshKey={refreshKey}
          projectId={projectId}
          hideGobby={hideGobby}
        />
      )}

      {activeTab === 'rules' && (
        <RulesTab
          searchText={searchText}
          sourceFilter={sourceFilter}
          devMode={devMode}
          showCreateModal={showRuleCreateModal}
          onCloseCreateModal={() => setShowRuleCreateModal(false)}
          refreshKey={refreshKey}
          projectId={projectId}
          hideGobby={hideGobby}
        />
      )}
    </main>
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
