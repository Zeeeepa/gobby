import { useState, useCallback, useMemo, useEffect, useRef } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import * as yaml from 'js-yaml'
import { useRules } from '../hooks/useRules'
import type { RuleSummary, RuleDetail } from '../hooks/useRules'
import { YamlEditorModal } from './WorkflowsPage'

const codeTheme = {
  ...oneDark,
  'pre[class*="language-"]': {
    ...oneDark['pre[class*="language-"]'],
    background: '#0d0d0d',
    margin: '0',
    padding: '0.75rem',
    fontSize: '11px',
  },
  'code[class*="language-"]': {
    ...oneDark['code[class*="language-"]'],
    background: 'transparent',
    fontFamily: "'SF Mono', 'Fira Code', 'JetBrains Mono', monospace",
  },
}

function RuleCodeBlock({ language, code }: { language: string; code: string }) {
  const [copied, setCopied] = useState(false)
  const timeoutRef = useRef<number | null>(null)

  useEffect(() => {
    return () => { if (timeoutRef.current) clearTimeout(timeoutRef.current) }
  }, [])

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(code)
      setCopied(true)
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
      timeoutRef.current = window.setTimeout(() => setCopied(false), 2000)
    } catch { /* ignore */ }
  }, [code])

  return (
    <div style={{ border: '1px solid var(--border)', borderRadius: 6, overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', background: 'var(--bg-tertiary)', padding: '4px 10px', fontSize: 10 }}>
        <span style={{ color: 'var(--text-muted)', fontFamily: 'monospace' }}>{language}</span>
        <button
          type="button"
          onClick={handleCopy}
          style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'var(--text-secondary)', padding: '2px 4px', display: 'flex', alignItems: 'center' }}
          title="Copy"
        >
          {copied ? (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
          ) : (
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2" /><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" /></svg>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        style={codeTheme}
        language={language}
        PreTag="div"
        showLineNumbers
        lineNumberStyle={{ minWidth: '2em', paddingRight: '0.75em', textAlign: 'right', userSelect: 'none', color: '#555' }}
        customStyle={{ margin: 0, borderRadius: 0 }}
      >
        {code}
      </SyntaxHighlighter>
    </div>
  )
}

interface RulesTabProps {
  searchText: string
  sourceFilter: 'installed' | 'templates' | 'deleted'
  devMode: boolean
  showCreateModal: boolean
  onCloseCreateModal: () => void
  refreshKey?: number
}

export function RulesTab({ searchText, sourceFilter, devMode, showCreateModal, onCloseCreateModal, refreshKey = 0 }: RulesTabProps) {
  const {
    rules,
    isLoading,
    eventTypes,
    enforcementEnabled,
    toggleRule,
    fetchRuleDetail,
    createRule,
    updateRule,
    deleteRule,
    useAsTemplate,
    setEnforcement,
    fetchRules,
  } = useRules()

  // Re-fetch when refreshKey changes (skip initial render)
  const initialRef = useRef(true)
  useEffect(() => {
    if (initialRef.current) {
      initialRef.current = false
      return
    }
    fetchRules()
  }, [refreshKey, fetchRules])

  const [eventFilter, setEventFilter] = useState<string | null>(null)
  const [expandedRule, setExpandedRule] = useState<string | null>(null)
  const [ruleDetail, setRuleDetail] = useState<RuleDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // YAML editor state
  const [yamlRule, setYamlRule] = useState<RuleSummary | null>(null)
  const [yamlContent, setYamlContent] = useState('')
  const [yamlLoading, setYamlLoading] = useState(false)

  // Filter rules
  const filteredRules = useMemo(() => {
    let result = rules

    // Source filter (exclusive)
    if (sourceFilter === 'installed') {
      result = result.filter(r => r.source === 'installed' && !(r as RuleSummary & { deleted_at?: string | null }).deleted_at)
    } else if (sourceFilter === 'templates') {
      result = result.filter(r => r.source === 'template' && !(r as RuleSummary & { deleted_at?: string | null }).deleted_at)
    } else if (sourceFilter === 'deleted') {
      result = result.filter(r => !!(r as RuleSummary & { deleted_at?: string | null }).deleted_at)
    }

    if (eventFilter) {
      result = result.filter(r => r.event === eventFilter)
    }
    if (searchText.trim()) {
      const q = searchText.toLowerCase()
      result = result.filter(r =>
        r.name.toLowerCase().includes(q) ||
        (r.description && r.description.toLowerCase().includes(q)) ||
        (r.event && r.event.toLowerCase().includes(q)) ||
        (r.tags && r.tags.some(t => t.toLowerCase().includes(q)))
      )
    }

    return result
  }, [rules, eventFilter, searchText, sourceFilter])

  const handleExpandRule = useCallback(async (rule: RuleSummary) => {
    if (expandedRule === rule.name) {
      setExpandedRule(null)
      setRuleDetail(null)
      return
    }
    setExpandedRule(rule.name)
    setDetailLoading(true)
    const detail = await fetchRuleDetail(rule.name)
    setRuleDetail(detail)
    setDetailLoading(false)
  }, [expandedRule, fetchRuleDetail])

  const handleToggle = useCallback(async (rule: RuleSummary) => {
    await toggleRule(rule.name, !rule.enabled)
  }, [toggleRule])

  const handleDelete = useCallback(async (rule: RuleSummary) => {
    const isTemplate = rule.source === 'template' || rule.source === 'built-in'
    const msg = isTemplate
      ? `"${rule.name}" is a template rule. Force-delete it? It will be re-created on next sync.`
      : `Delete rule "${rule.name}"?`
    if (!window.confirm(msg)) return
    await deleteRule(rule.name, isTemplate)
  }, [deleteRule])

  const handleCreate = useCallback(async (name: string, definitionJson: string) => {
    const definition = JSON.parse(definitionJson)
    const result = await createRule(name, definition)
    if (result) {
      onCloseCreateModal()
    }
    return result
  }, [createRule, onCloseCreateModal])

  const handleYamlEdit = useCallback(async (rule: RuleSummary) => {
    setYamlLoading(true)
    setYamlRule(rule)
    try {
      const detail = await fetchRuleDetail(rule.name)
      if (detail) {
        const obj: Record<string, unknown> = {
          name: detail.name,
          event: detail.event,
          priority: detail.priority,
        }
        if (detail.description) obj.description = detail.description
        if (detail.when) obj.when = detail.when
        if (detail.match) obj.match = detail.match
        if (detail.effect) obj.effect = detail.effect
        if (detail.tags && detail.tags.length > 0) obj.tags = detail.tags
        if (detail.group) obj.group = detail.group
        obj.enabled = detail.enabled
        setYamlContent(yaml.dump(obj, { lineWidth: 120, noRefs: true }))
      } else {
        setYamlContent('')
        window.alert('Failed to load rule details')
        setYamlRule(null)
      }
    } catch (e) {
      console.error('Failed to export rule YAML:', e)
      setYamlContent('')
      setYamlRule(null)
    } finally {
      setYamlLoading(false)
    }
  }, [fetchRuleDetail])

  const handleYamlSave = useCallback(async () => {
    if (!yamlRule) return
    let parsed: Record<string, unknown>
    try {
      parsed = yaml.load(yamlContent, { schema: yaml.JSON_SCHEMA }) as Record<string, unknown>
    } catch (e) {
      throw new Error(`Invalid YAML: ${e instanceof Error ? e.message : String(e)}`)
    }
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      throw new Error('Invalid YAML: expected an object')
    }
    await updateRule(yamlRule.name, parsed)
    setYamlRule(null)
  }, [yamlRule, yamlContent, updateRule])

  const handleDuplicate = useCallback(async (rule: RuleSummary) => {
    const newName = window.prompt('New rule name:', `${rule.name}-copy`)
    if (!newName) return
    const detail = await fetchRuleDetail(rule.name)
    if (!detail) return
    const definition: Record<string, unknown> = {}
    if (detail.event) definition.event = detail.event
    if (detail.description) definition.description = detail.description
    if (detail.when) definition.when = detail.when
    if (detail.match) definition.match = detail.match
    if (detail.effect) definition.effect = detail.effect
    if (detail.tags && detail.tags.length > 0) definition.tags = detail.tags
    if (detail.group) definition.group = detail.group
    definition.priority = detail.priority
    definition.enabled = detail.enabled
    await createRule(newName, definition)
  }, [fetchRuleDetail, createRule])

  const handleDownload = useCallback(async (rule: RuleSummary) => {
    const detail = await fetchRuleDetail(rule.name)
    if (!detail) return
    const obj: Record<string, unknown> = {
      name: detail.name,
      event: detail.event,
      priority: detail.priority,
    }
    if (detail.description) obj.description = detail.description
    if (detail.when) obj.when = detail.when
    if (detail.match) obj.match = detail.match
    if (detail.effect) obj.effect = detail.effect
    if (detail.tags && detail.tags.length > 0) obj.tags = detail.tags
    if (detail.group) obj.group = detail.group
    obj.enabled = detail.enabled
    const yamlStr = yaml.dump(obj, { lineWidth: 120, noRefs: true })
    const blob = new Blob([yamlStr], { type: 'application/x-yaml' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${rule.name}.yaml`
    a.click()
    URL.revokeObjectURL(url)
  }, [fetchRuleDetail])

  const handleUseAllAsTemplates = useCallback(async () => {
    try {
      const response = await fetch('/api/workflows/use-all-bundled-as-templates?workflow_type=rule', {
        method: 'POST',
      })
      if (response.ok) {
        // Rules hook refreshes via fetchRules which comes from the /api/rules endpoint
        // We need to trigger a page-level refresh - calling fetchRules won't see workflow_definitions changes
        // since rules come from the rule engine. Reload the rules.
        window.location.reload()
      }
    } catch (e) {
      console.error('Failed to use all bundled rules as templates:', e)
    }
  }, [])

  const clearFilters = useCallback(() => {
    setEventFilter(null)
  }, [])

  const hasFilters = !!eventFilter

  return (
    <div className="rules-tab">
      {/* Filter chips */}
      <div className="workflows-filter-bar">
        <div className="rules-filter-chips">
          {eventTypes.map(ev => (
            <button
              type="button"
              key={ev}
              className={`workflows-filter-chip ${eventFilter === ev ? 'workflows-filter-chip--active' : ''}`}
              onClick={() => setEventFilter(eventFilter === ev ? null : ev)}
            >
              {ev}
            </button>
          ))}
          {hasFilters && (
            <button
              type="button"
              className="workflows-filter-chip rules-filter-clear"
              onClick={clearFilters}
            >
              Clear
            </button>
          )}
        </div>
        <div className="rules-enforcement-toggle" onClick={() => setEnforcement(!enforcementEnabled)}>
          <div className={`workflows-toggle-track ${enforcementEnabled ? 'workflows-toggle-track--on' : ''}`}>
            <div className="workflows-toggle-knob" />
          </div>
          <span>{enforcementEnabled ? 'Rules Active' : 'Rules Paused'}</span>
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

      {/* Card grid */}
      <div className="workflows-content">
        {isLoading ? (
          <div className="workflows-loading">Loading rules...</div>
        ) : filteredRules.length === 0 ? (
          <div className="workflows-empty">No rules match the current filters.</div>
        ) : (
          <div className="workflows-grid">
            {filteredRules.map(rule => (
              <RuleCard
                key={rule.id}
                rule={rule}
                devMode={devMode}
                expanded={expandedRule === rule.name}
                detail={expandedRule === rule.name ? ruleDetail : null}
                detailLoading={expandedRule === rule.name && detailLoading}
                onToggle={() => handleToggle(rule)}
                onExpand={() => handleExpandRule(rule)}
                onDelete={() => handleDelete(rule)}
                onYamlEdit={() => handleYamlEdit(rule)}
                onDuplicate={() => handleDuplicate(rule)}
                onDownload={() => handleDownload(rule)}
                onUseAsTemplate={() => useAsTemplate(rule.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Create modal */}
      {showCreateModal && (
        <RuleCreateModal
          onClose={onCloseCreateModal}
          onCreate={handleCreate}
        />
      )}

      {/* YAML editor modal */}
      {yamlRule && (
        <YamlEditorModal
          workflowName={yamlRule.name}
          yamlContent={yamlContent}
          loading={yamlLoading}
          onChange={setYamlContent}
          onSave={handleYamlSave}
          onClose={() => setYamlRule(null)}
        />
      )}
    </div>
  )
}

function getEffectType(effect: Record<string, unknown> | null): string | null {
  if (!effect) return null
  const type = effect.type
  if (typeof type === 'string') return type
  // Infer from keys
  if ('block' in effect || effect.type === 'block') return 'block'
  if ('set_variable' in effect || 'variable' in effect) return 'set_variable'
  if ('inject_context' in effect || 'context' in effect) return 'inject_context'
  if ('mcp_call' in effect || 'tool' in effect) return 'mcp_call'
  return null
}

function RuleCard({ rule, devMode, expanded, detail, detailLoading, onToggle, onExpand, onDelete, onYamlEdit, onDuplicate, onDownload, onUseAsTemplate }: {
  rule: RuleSummary
  devMode: boolean
  expanded: boolean
  detail: RuleDetail | null
  detailLoading: boolean
  onToggle: () => void
  onExpand: () => void
  onDelete: () => void
  onYamlEdit: () => void
  onDuplicate: () => void
  onDownload: () => void
  onUseAsTemplate: () => void
}) {
  const effectType = getEffectType(rule.effect)
  const isTemplate = rule.source === 'template'
  const isDeleted = !!(rule as RuleSummary & { deleted_at?: string | null }).deleted_at

  return (
    <div className={`rules-card ${expanded ? 'rules-card--expanded' : ''}${isTemplate ? ' workflows-card--template' : ''}${isDeleted ? ' rules-card--deleted' : ''}`}>
      <div className="rules-card-main" onClick={onExpand}>
        <div className="rules-card-header">
          <span className="rules-card-name">{rule.name}</span>
          <span className="workflows-card-type workflows-card-type--rule">rule</span>
        </div>

        {rule.description && (
          <div className="rules-card-desc">{rule.description}</div>
        )}

        <div className="workflows-card-badges" style={{ marginTop: 6 }}>
          {rule.tags && rule.tags.length > 0 && rule.tags.map(tag => (
            <span className="rules-card-tag" key={tag}>{tag}</span>
          ))}
          {rule.event && (
            <span className="rules-card-event">{rule.event}</span>
          )}
          {effectType && (
            <span className={`rules-card-effect rules-card-effect--${effectType}`}>{effectType}</span>
          )}
          <span className="rules-card-priority">P{rule.priority}</span>
        </div>
      </div>

      <div className="workflows-card-footer">
        {(isTemplate || isDeleted) ? (
          <>
            <div />
            <div className="workflows-card-actions">
              {devMode ? (
                <>
                  <button type="button" className="workflows-action-btn" onClick={e => { e.stopPropagation(); onYamlEdit() }} title="Edit as YAML">YAML</button>
                  <button type="button" className="workflows-action-icon" onClick={e => { e.stopPropagation(); onDuplicate() }} title="Duplicate" aria-label="Duplicate rule">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="5.5" y="5.5" width="9" height="9" rx="1.5" /><path d="M10.5 5.5V2.5a1 1 0 0 0-1-1h-7a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h3" /></svg>
                  </button>
                  <button type="button" className="workflows-action-icon" onClick={e => { e.stopPropagation(); onDownload() }} title="Download YAML" aria-label="Download rule as YAML">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v9m0 0L5 8m3 3 3-3M2.5 12.5v1a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-1" /></svg>
                  </button>
                  <button type="button" className="workflows-action-icon workflows-action-icon--danger" onClick={e => { e.stopPropagation(); onDelete() }} title="Delete rule" aria-label="Delete rule">
                    <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2.5 4.5h11M5.5 4.5V3a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v1.5M6.5 7v4.5M9.5 7v4.5" /><path d="M3.5 4.5 4 13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l.5-8.5" /></svg>
                  </button>
                </>
              ) : (
                <>
                  {isTemplate && (
                    <button type="button" className="workflows-action-btn" onClick={e => { e.stopPropagation(); onUseAsTemplate() }} title="Create a custom copy">Use as Template</button>
                  )}
                  <button type="button" className="workflows-action-icon" onClick={e => { e.stopPropagation(); onDownload() }} title="Download YAML" aria-label="Download rule as YAML">
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
              onClick={e => { e.stopPropagation(); onToggle() }}
            >
              <div className={`workflows-toggle-track ${rule.enabled ? 'workflows-toggle-track--on' : ''}`}>
                <div className="workflows-toggle-knob" />
              </div>
              <span>{rule.enabled ? 'On' : 'Off'}</span>
            </div>

            <div className="workflows-card-actions">
              <button type="button" className="workflows-action-btn" onClick={e => { e.stopPropagation(); onYamlEdit() }} title="Edit as YAML">YAML</button>
              <button type="button" className="workflows-action-icon" onClick={e => { e.stopPropagation(); onDuplicate() }} title="Duplicate" aria-label="Duplicate rule">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><rect x="5.5" y="5.5" width="9" height="9" rx="1.5" /><path d="M10.5 5.5V2.5a1 1 0 0 0-1-1h-7a1 1 0 0 0-1 1v7a1 1 0 0 0 1 1h3" /></svg>
              </button>
              <button type="button" className="workflows-action-icon" onClick={e => { e.stopPropagation(); onDownload() }} title="Download YAML" aria-label="Download rule as YAML">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M8 2v9m0 0L5 8m3 3 3-3M2.5 12.5v1a1 1 0 0 0 1 1h9a1 1 0 0 0 1-1v-1" /></svg>
              </button>
              <button type="button" className="workflows-action-icon workflows-action-icon--danger" onClick={e => { e.stopPropagation(); onDelete() }} title="Delete rule" aria-label="Delete rule">
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"><path d="M2.5 4.5h11M5.5 4.5V3a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v1.5M6.5 7v4.5M9.5 7v4.5" /><path d="M3.5 4.5 4 13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l.5-8.5" /></svg>
              </button>
            </div>
          </>
        )}
      </div>

      {expanded && (
        <div className="rules-card-detail">
          {detailLoading ? (
            <div className="rules-detail-loading">Loading...</div>
          ) : detail ? (
            <>
              {detail.when && (
                <div className="rules-detail-section">
                  <span className="rules-detail-label">When</span>
                  <RuleCodeBlock language="python" code={detail.when} />
                </div>
              )}
              {detail.effect && (
                <div className="rules-detail-section">
                  <span className="rules-detail-label">Effect</span>
                  <RuleCodeBlock language="json" code={JSON.stringify(detail.effect, null, 2)} />
                </div>
              )}
              {detail.match && (
                <div className="rules-detail-section">
                  <span className="rules-detail-label">Match</span>
                  <RuleCodeBlock language="json" code={JSON.stringify(detail.match, null, 2)} />
                </div>
              )}
            </>
          ) : (
            <div className="rules-detail-loading">Failed to load details</div>
          )}
        </div>
      )}
    </div>
  )
}

function RuleCreateModal({ onClose, onCreate }: {
  onClose: () => void
  onCreate: (name: string, definitionJson: string) => Promise<RuleDetail | null>
}) {
  const [name, setName] = useState('')
  const [definitionJson, setDefinitionJson] = useState(JSON.stringify({
    event: 'before_tool',
    effect: { type: 'block', message: 'Blocked by rule' },
  }, null, 2))
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const handleSubmit = async () => {
    if (!name.trim()) return
    setError(null)
    setSubmitting(true)
    try {
      JSON.parse(definitionJson) // validate
      await onCreate(name.trim(), definitionJson)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Invalid JSON')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="workflows-modal-overlay" onClick={onClose}>
      <div className="workflows-modal" onClick={e => e.stopPropagation()}>
        <h3>New Rule</h3>
        <div className="workflows-modal-field">
          <label>Name</label>
          <input
            type="text"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="my-rule"
            autoFocus
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
        {error && <div style={{ color: '#f87171', fontSize: 12, marginBottom: 8 }}>{error}</div>}
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
