import { useState, useCallback, useMemo } from 'react'
import { useRules } from '../hooks/useRules'
import type { RuleSummary, RuleDetail } from '../hooks/useRules'

interface RulesTabProps {
  searchText: string
  showDeleted: boolean
  showCreateModal: boolean
  onCloseCreateModal: () => void
}

export function RulesTab({ searchText, showDeleted, showCreateModal, onCloseCreateModal }: RulesTabProps) {
  const {
    rules,
    isLoading,
    eventTypes,
    sources,
    toggleRule,
    fetchRuleDetail,
    createRule,
    deleteRule,
  } = useRules()

  const [eventFilter, setEventFilter] = useState<string | null>(null)
  const [sourceFilter, setSourceFilter] = useState<string | null>(null)
  const [expandedRule, setExpandedRule] = useState<string | null>(null)
  const [ruleDetail, setRuleDetail] = useState<RuleDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // Filter rules
  const filteredRules = useMemo(() => {
    let result = rules

    if (!showDeleted) {
      result = result.filter(r => !(r as RuleSummary & { deleted_at?: string | null }).deleted_at)
    }

    if (eventFilter) {
      result = result.filter(r => r.event === eventFilter)
    }
    if (sourceFilter) {
      result = result.filter(r => r.source === sourceFilter)
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
  }, [rules, eventFilter, sourceFilter, searchText, showDeleted])

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
    const isBundled = rule.source === 'bundled' || rule.source === 'built-in'
    const msg = isBundled
      ? `"${rule.name}" is a bundled rule. Force-delete it? It will be re-created on next sync.`
      : `Delete rule "${rule.name}"?`
    if (!window.confirm(msg)) return
    await deleteRule(rule.name, isBundled)
  }, [deleteRule])

  const handleCreate = useCallback(async (name: string, definitionJson: string) => {
    const definition = JSON.parse(definitionJson)
    const result = await createRule(name, definition)
    if (result) {
      onCloseCreateModal()
    }
    return result
  }, [createRule, onCloseCreateModal])

  const clearFilters = useCallback(() => {
    setEventFilter(null)
    setSourceFilter(null)
  }, [])

  const hasFilters = eventFilter || sourceFilter

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
          {sources.map(s => (
            <button
              type="button"
              key={`src-${s}`}
              className={`workflows-filter-chip ${sourceFilter === s ? 'workflows-filter-chip--active' : ''}`}
              onClick={() => setSourceFilter(sourceFilter === s ? null : s)}
            >
              {s}
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
                expanded={expandedRule === rule.name}
                detail={expandedRule === rule.name ? ruleDetail : null}
                detailLoading={expandedRule === rule.name && detailLoading}
                onToggle={() => handleToggle(rule)}
                onExpand={() => handleExpandRule(rule)}
                onDelete={() => handleDelete(rule)}
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

function RuleCard({ rule, expanded, detail, detailLoading, onToggle, onExpand, onDelete }: {
  rule: RuleSummary
  expanded: boolean
  detail: RuleDetail | null
  detailLoading: boolean
  onToggle: () => void
  onExpand: () => void
  onDelete: () => void
}) {
  const effectType = getEffectType(rule.effect)

  return (
    <div className={`rules-card ${expanded ? 'rules-card--expanded' : ''}`}>
      <div className="rules-card-main" onClick={onExpand}>
        <div className="rules-card-header">
          <span className="rules-card-name">{rule.name}</span>
          <div className="rules-card-badges">
            {rule.event && (
              <span className="rules-card-event">{rule.event}</span>
            )}
            {effectType && (
              <span className={`rules-card-effect rules-card-effect--${effectType}`}>{effectType}</span>
            )}
            <span className="rules-card-priority">P{rule.priority}</span>
          </div>
        </div>

        {rule.description && (
          <div className="rules-card-desc">{rule.description}</div>
        )}

        {rule.when && (
          <div className="rules-card-when">
            <span className="rules-card-when-label">when</span>
            <code className="rules-card-when-value">{rule.when}</code>
          </div>
        )}

        {rule.tags && rule.tags.length > 0 && (
          <div className="rules-card-tags">
            {rule.tags.map(tag => (
              <span className="rules-card-tag" key={tag}>{tag}</span>
            ))}
          </div>
        )}
      </div>

      <div className="rules-card-footer">
        <div
          className="workflows-toggle"
          onClick={e => { e.stopPropagation(); onToggle() }}
        >
          <div className={`workflows-toggle-track ${rule.enabled ? 'workflows-toggle-track--on' : ''}`}>
            <div className="workflows-toggle-knob" />
          </div>
          <span>{rule.enabled ? 'On' : 'Off'}</span>
        </div>
        <button
          type="button"
          className="workflows-action-icon workflows-action-icon--danger"
          onClick={e => { e.stopPropagation(); onDelete() }}
          title="Delete rule"
          aria-label="Delete rule"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M2.5 4.5h11M5.5 4.5V3a1 1 0 0 1 1-1h3a1 1 0 0 1 1 1v1.5M6.5 7v4.5M9.5 7v4.5" />
            <path d="M3.5 4.5 4 13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1l.5-8.5" />
          </svg>
        </button>
      </div>

      {expanded && (
        <div className="rules-card-detail">
          {detailLoading ? (
            <div className="rules-detail-loading">Loading...</div>
          ) : detail ? (
            <>
              {detail.effect && (
                <div className="rules-detail-section">
                  <span className="rules-detail-label">Effect</span>
                  <pre className="rules-detail-code">{JSON.stringify(detail.effect, null, 2)}</pre>
                </div>
              )}
              {detail.match && (
                <div className="rules-detail-section">
                  <span className="rules-detail-label">Match</span>
                  <pre className="rules-detail-code">{JSON.stringify(detail.match, null, 2)}</pre>
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
