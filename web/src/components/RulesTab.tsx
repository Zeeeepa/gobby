import { useState, useCallback, useMemo } from 'react'
import { useRules } from '../hooks/useRules'
import type { RuleSummary, RuleDetail } from '../hooks/useRules'

export function RulesTab() {
  const {
    rules,
    groups,
    isLoading,
    ruleCount,
    enabledCount,
    eventTypes,
    sources,
    fetchRules,
    toggleRule,
    fetchRuleDetail,
  } = useRules()

  const [searchText, setSearchText] = useState('')
  const [eventFilter, setEventFilter] = useState<string | null>(null)
  const [groupFilter, setGroupFilter] = useState<string | null>(null)
  const [sourceFilter, setSourceFilter] = useState<string | null>(null)
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set())
  const [expandedRule, setExpandedRule] = useState<string | null>(null)
  const [ruleDetail, setRuleDetail] = useState<RuleDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // Filter rules
  const filteredRules = useMemo(() => {
    let result = rules

    if (eventFilter) {
      result = result.filter(r => r.event === eventFilter)
    }
    if (groupFilter) {
      result = result.filter(r => r.group === groupFilter)
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
        (r.group && r.group.toLowerCase().includes(q))
      )
    }

    return result
  }, [rules, eventFilter, groupFilter, sourceFilter, searchText])

  // Group filtered rules by group field
  const groupedRules = useMemo(() => {
    const map = new Map<string, RuleSummary[]>()
    for (const rule of filteredRules) {
      const group = rule.group || 'ungrouped'
      const list = map.get(group) || []
      list.push(rule)
      map.set(group, list)
    }
    // Sort groups: named groups alphabetically, ungrouped last
    const entries = Array.from(map.entries()).sort(([a], [b]) => {
      if (a === 'ungrouped') return 1
      if (b === 'ungrouped') return -1
      return a.localeCompare(b)
    })
    return entries
  }, [filteredRules])

  const toggleGroupCollapse = useCallback((group: string) => {
    setCollapsedGroups(prev => {
      const next = new Set(prev)
      if (next.has(group)) next.delete(group)
      else next.add(group)
      return next
    })
  }, [])

  const handleToggleGroupAll = useCallback(async (groupRules: RuleSummary[], enable: boolean) => {
    for (const rule of groupRules) {
      if (rule.enabled !== enable) {
        await toggleRule(rule.name, enable)
      }
    }
  }, [toggleRule])

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

  const clearFilters = useCallback(() => {
    setEventFilter(null)
    setGroupFilter(null)
    setSourceFilter(null)
    setSearchText('')
  }, [])

  const hasFilters = eventFilter || groupFilter || sourceFilter || searchText.trim()

  return (
    <div className="rules-tab">
      {/* Stats bar */}
      <div className="rules-stats">
        <span className="rules-stat">{ruleCount} rules</span>
        <span className="rules-stat-sep">&middot;</span>
        <span className="rules-stat">{enabledCount} enabled</span>
        <span className="rules-stat-sep">&middot;</span>
        <span className="rules-stat">{groups.length} groups</span>
      </div>

      {/* Filter bar */}
      <div className="rules-filter-bar">
        <input
          className="rules-search"
          type="text"
          placeholder="Search rules..."
          value={searchText}
          onChange={e => setSearchText(e.target.value)}
        />
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
          {groups.map(g => (
            <button
              type="button"
              key={g}
              className={`workflows-filter-chip ${groupFilter === g ? 'workflows-filter-chip--active' : ''}`}
              onClick={() => setGroupFilter(groupFilter === g ? null : g)}
            >
              {g}
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
        <button
          type="button"
          className="workflows-toolbar-btn"
          onClick={() => fetchRules()}
          title="Refresh"
          disabled={isLoading}
        >
          &#x21bb;
        </button>
      </div>

      {/* Content */}
      <div className="rules-content">
        {isLoading ? (
          <div className="workflows-loading">Loading rules...</div>
        ) : filteredRules.length === 0 ? (
          <div className="workflows-empty">No rules match the current filters.</div>
        ) : (
          <div className="rules-groups">
            {groupedRules.map(([group, groupRules]) => {
              const collapsed = collapsedGroups.has(group)
              const allEnabled = groupRules.every(r => r.enabled)
              const noneEnabled = groupRules.every(r => !r.enabled)

              return (
                <div className="rules-group" key={group}>
                  <div className="rules-group-header">
                    <button
                      type="button"
                      className="rules-group-toggle"
                      onClick={() => toggleGroupCollapse(group)}
                    >
                      <span className={`rules-group-chevron ${collapsed ? '' : 'rules-group-chevron--open'}`}>
                        &#x25B6;
                      </span>
                      <span className="rules-group-name">{group}</span>
                      <span className="rules-group-count">{groupRules.length}</span>
                    </button>
                    <div className="rules-group-actions">
                      <button
                        type="button"
                        className={`rules-group-enable-btn ${allEnabled ? 'rules-group-enable-btn--active' : ''}`}
                        onClick={() => handleToggleGroupAll(groupRules, !allEnabled)}
                        title={allEnabled ? 'Disable all in group' : noneEnabled ? 'Enable all in group' : 'Enable all in group'}
                      >
                        {allEnabled ? 'All on' : noneEnabled ? 'All off' : 'Mixed'}
                      </button>
                    </div>
                  </div>
                  {!collapsed && (
                    <div className="rules-group-cards">
                      {groupRules.map(rule => (
                        <RuleCard
                          key={rule.id}
                          rule={rule}
                          expanded={expandedRule === rule.name}
                          detail={expandedRule === rule.name ? ruleDetail : null}
                          detailLoading={expandedRule === rule.name && detailLoading}
                          onToggle={() => handleToggle(rule)}
                          onExpand={() => handleExpandRule(rule)}
                        />
                      ))}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

function RuleCard({ rule, expanded, detail, detailLoading, onToggle, onExpand }: {
  rule: RuleSummary
  expanded: boolean
  detail: RuleDetail | null
  detailLoading: boolean
  onToggle: () => void
  onExpand: () => void
}) {
  return (
    <div className={`rules-card ${expanded ? 'rules-card--expanded' : ''}`}>
      <div className="rules-card-main" onClick={onExpand}>
        <div className="rules-card-header">
          <span className="rules-card-name">{rule.name}</span>
          <div className="rules-card-badges">
            {rule.event && (
              <span className="rules-card-event">{rule.event}</span>
            )}
            <span className="rules-card-priority">P{rule.priority}</span>
            {rule.source && (
              <span className="rules-card-source">{rule.source}</span>
            )}
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
