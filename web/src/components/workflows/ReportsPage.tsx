import { useState, useMemo, useCallback, useEffect } from 'react'
import { usePipelineExecutions } from '../../hooks/usePipelineExecutions'
import type { PipelineExecutionRecord } from '../../hooks/usePipelineExecutions'
import { useAgentRuns } from '../../hooks/useAgentRuns'
import type { AgentRunRecord, AgentRunDetail } from '../../hooks/useAgentRuns'
import {
  StepDisplay,
  ChevronIcon,
  AlertIcon,
  formatTime,
  formatDuration,
  formatJson,
} from './execution-utils'
import './reports-page.css'

// =============================================================================
// Types
// =============================================================================

type SubTab = 'pipelines' | 'agents'
type StatusFilter = 'all' | 'running' | 'waiting' | 'completed' | 'failed'

function statusMatchesFilter(status: string, filter: StatusFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'running') return status === 'running' || status === 'pending'
  if (filter === 'waiting') return status === 'waiting_approval'
  if (filter === 'completed') return status === 'completed' || status === 'success'
  if (filter === 'failed') return status === 'failed' || status === 'error' || status === 'timeout' || status === 'cancelled' || status === 'interrupted'
  return true
}

function normalizeStatus(status: string): string {
  return status.replace(/_/g, ' ')
}

function formatDateTime(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'running', label: 'Running' },
  { value: 'waiting', label: 'Waiting' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

// =============================================================================
// Status dot
// =============================================================================

function StatusDot({ status }: { status: string }) {
  const colorMap: Record<string, string> = {
    running: '#60a5fa',
    pending: '#888',
    completed: '#4ade80',
    success: '#4ade80',
    failed: '#f87171',
    error: '#f87171',
    timeout: '#fb923c',
    waiting_approval: '#fbbf24',
    cancelled: '#888',
    interrupted: '#c084fc',
  }
  return (
    <span
      className="reports-status-dot"
      style={{ backgroundColor: colorMap[status] || '#888' }}
      title={status}
    />
  )
}

// =============================================================================
// Close icon
// =============================================================================

function CloseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function CronIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}

// =============================================================================
// ReportsPage
// =============================================================================

export function ReportsPage({ projectId }: { projectId?: string }) {
  const [subTab, setSubTab] = useState<SubTab>('pipelines')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [searchText, setSearchText] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [agentDetails, setAgentDetails] = useState<Record<string, AgentRunDetail>>({})
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const {
    executions: pipelineExecutions,
    isLoading: pipelinesLoading,
    approvePipeline,
    rejectPipeline,
  } = usePipelineExecutions(projectId)

  const {
    runs: agentRuns,
    isLoading: agentsLoading,
    cancelRun,
    fetchRunDetail,
  } = useAgentRuns()

  // Compute counts
  const pipelineCounts = useMemo(() => {
    const statuses = pipelineExecutions.map(pe => pe.status)
    return {
      all: statuses.length,
      running: statuses.filter(s => s === 'running' || s === 'pending').length,
      waiting: statuses.filter(s => s === 'waiting_approval').length,
      completed: statuses.filter(s => s === 'completed').length,
      failed: statuses.filter(s => s === 'failed' || s === 'cancelled' || s === 'interrupted').length,
    }
  }, [pipelineExecutions])

  const agentCounts = useMemo(() => {
    const statuses = agentRuns.map(ar => ar.status)
    return {
      all: statuses.length,
      running: statuses.filter(s => s === 'running' || s === 'pending').length,
      waiting: 0,
      completed: statuses.filter(s => s === 'success').length,
      failed: statuses.filter(s => s === 'error' || s === 'timeout' || s === 'cancelled').length,
    }
  }, [agentRuns])

  const counts = subTab === 'pipelines' ? pipelineCounts : agentCounts

  // Filtered + sorted lists
  const filteredPipelines = useMemo(() => {
    let items = pipelineExecutions.filter(pe => statusMatchesFilter(pe.status, statusFilter))
    if (searchText.trim()) {
      const q = searchText.toLowerCase()
      items = items.filter(pe => pe.pipeline_name.toLowerCase().includes(q) || pe.id.toLowerCase().includes(q))
    }
    return items.sort((a, b) => b.created_at.localeCompare(a.created_at))
  }, [pipelineExecutions, statusFilter, searchText])

  const filteredAgents = useMemo(() => {
    let items = agentRuns.filter(ar => statusMatchesFilter(ar.status, statusFilter))
    if (searchText.trim()) {
      const q = searchText.toLowerCase()
      items = items.filter(ar =>
        (ar.workflow_name || '').toLowerCase().includes(q) ||
        (ar.prompt || '').toLowerCase().includes(q) ||
        ar.id.toLowerCase().includes(q)
      )
    }
    return items.sort((a, b) => b.created_at.localeCompare(a.created_at))
  }, [agentRuns, statusFilter, searchText])

  // Clear selection on tab switch
  useEffect(() => { setSelectedId(null) }, [subTab])

  // Fetch agent detail when selected
  const handleSelectAgent = useCallback(async (id: string) => {
    setSelectedId(id)
    if (!agentDetails[id]) {
      const detail = await fetchRunDetail(id)
      if (detail) setAgentDetails(prev => ({ ...prev, [id]: detail }))
    }
  }, [agentDetails, fetchRunDetail])

  const handleApprove = async (token: string) => {
    setActionLoading(token)
    try { await approvePipeline(token) } finally { setActionLoading(null) }
  }

  const handleReject = async (token: string) => {
    setActionLoading(token)
    try { await rejectPipeline(token) } finally { setActionLoading(null) }
  }

  const handleCancel = async (runId: string) => {
    setActionLoading(runId)
    try { await cancelRun(runId) } finally { setActionLoading(null) }
  }

  const isLoading = subTab === 'pipelines' ? pipelinesLoading : agentsLoading
  const isEmpty = subTab === 'pipelines' ? filteredPipelines.length === 0 : filteredAgents.length === 0

  const selectedPipeline = subTab === 'pipelines' ? pipelineExecutions.find(pe => pe.id === selectedId) : null
  const selectedAgent = subTab === 'agents' ? agentRuns.find(ar => ar.id === selectedId) : null

  return (
    <main className="reports-page">
      {/* Toolbar */}
      <div className="reports-toolbar">
        <div className="reports-toolbar-left">
          <h2 className="reports-title">Reports</h2>
          <div className="reports-subtabs">
            <button
              className={`reports-subtab ${subTab === 'pipelines' ? 'active' : ''}`}
              onClick={() => setSubTab('pipelines')}
            >
              Pipeline Executions
            </button>
            <button
              className={`reports-subtab ${subTab === 'agents' ? 'active' : ''}`}
              onClick={() => setSubTab('agents')}
            >
              Agent Runs
            </button>
          </div>
        </div>
        <div className="reports-toolbar-right">
          <input
            type="text"
            className="reports-search"
            placeholder={subTab === 'pipelines' ? 'Search pipelines...' : 'Search agents...'}
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
          />
        </div>
      </div>

      {/* Filter bar */}
      <div className="reports-filter-bar">
        <div className="reports-filter-chips">
          {STATUS_OPTIONS.filter(opt => {
            if (opt.value === 'all') return true
            return counts[opt.value] > 0
          }).map(opt => (
            <button
              key={opt.value}
              className={`reports-stat-chip ${statusFilter === opt.value ? 'active' : ''}`}
              onClick={() => setStatusFilter(statusFilter === opt.value && opt.value !== 'all' ? 'all' : opt.value)}
            >
              {opt.value !== 'all' && <StatusDot status={
                opt.value === 'running' ? 'running' :
                opt.value === 'waiting' ? 'waiting_approval' :
                opt.value === 'completed' ? 'completed' :
                'failed'
              } />}
              {opt.label} ({counts[opt.value]})
            </button>
          ))}
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="reports-loading">Loading...</div>
      ) : isEmpty ? (
        <div className="reports-empty">No {subTab === 'pipelines' ? 'pipeline executions' : 'agent runs'} found</div>
      ) : subTab === 'pipelines' ? (
        <div className="reports-table-container">
          <table className="reports-table">
            <thead>
              <tr>
                <th className="reports-th" style={{ width: 28 }}></th>
                <th className="reports-th">Name</th>
                <th className="reports-th" style={{ width: 120 }}>ID</th>
                <th className="reports-th" style={{ width: 140 }}>Time</th>
                <th className="reports-th" style={{ width: 80 }}>Duration</th>
                <th className="reports-th" style={{ width: 100 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredPipelines.map(pe => (
                <tr
                  key={pe.id}
                  className={`reports-row ${selectedId === pe.id ? 'reports-row--selected' : ''}`}
                  onClick={() => setSelectedId(pe.id)}
                >
                  <td className="reports-cell"><StatusDot status={pe.status} /></td>
                  <td className="reports-cell reports-cell--name">{pe.pipeline_name}</td>
                  <td className="reports-cell reports-cell--id">{pe.id.slice(0, 12)}</td>
                  <td className="reports-cell reports-cell--time">{formatDateTime(pe.created_at)}</td>
                  <td className="reports-cell reports-cell--duration">
                    {pe.completed_at ? formatDuration(pe.created_at, pe.completed_at) : pe.status === 'running' ? '...' : '—'}
                  </td>
                  <td className="reports-cell reports-cell--status-text">{normalizeStatus(pe.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="reports-table-container">
          <table className="reports-table">
            <thead>
              <tr>
                <th className="reports-th" style={{ width: 28 }}></th>
                <th className="reports-th">Name</th>
                <th className="reports-th" style={{ width: 80 }}>Provider</th>
                <th className="reports-th" style={{ width: 120 }}>ID</th>
                <th className="reports-th" style={{ width: 140 }}>Time</th>
                <th className="reports-th" style={{ width: 80 }}>Duration</th>
                <th className="reports-th" style={{ width: 70 }}>Turns</th>
                <th className="reports-th" style={{ width: 100 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {filteredAgents.map(ar => (
                <tr
                  key={ar.id}
                  className={`reports-row ${selectedId === ar.id ? 'reports-row--selected' : ''}`}
                  onClick={() => handleSelectAgent(ar.id)}
                >
                  <td className="reports-cell"><StatusDot status={ar.status} /></td>
                  <td className="reports-cell reports-cell--name">{ar.workflow_name || ar.prompt?.slice(0, 60) || 'Agent Run'}</td>
                  <td className="reports-cell">
                    <span className="reports-type-badge reports-type-badge--agent">{ar.provider}</span>
                  </td>
                  <td className="reports-cell reports-cell--id">{ar.id.slice(0, 12)}</td>
                  <td className="reports-cell reports-cell--time">{formatDateTime(ar.created_at)}</td>
                  <td className="reports-cell reports-cell--duration">
                    {ar.started_at && ar.completed_at ? formatDuration(ar.started_at, ar.completed_at) : ar.status === 'running' ? '...' : '—'}
                  </td>
                  <td className="reports-cell" style={{ textAlign: 'center' }}>{ar.turns_used}</td>
                  <td className="reports-cell reports-cell--status-text">{normalizeStatus(ar.status)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Detail sidebar */}
      {selectedId && (selectedPipeline || selectedAgent) && (
        <>
          <div className="reports-detail-backdrop" onClick={() => setSelectedId(null)} />
          <div className={`reports-detail-panel ${selectedId ? 'open' : ''}`}>
            {selectedPipeline && (
              <PipelineDetail
                execution={selectedPipeline}
                actionLoading={actionLoading}
                onApprove={handleApprove}
                onReject={handleReject}
                onClose={() => setSelectedId(null)}
              />
            )}
            {selectedAgent && (
              <AgentDetail
                run={selectedAgent}
                detail={agentDetails[selectedAgent.id]}
                actionLoading={actionLoading}
                onCancel={handleCancel}
                onClose={() => setSelectedId(null)}
              />
            )}
          </div>
        </>
      )}
    </main>
  )
}

// =============================================================================
// Pipeline Detail Sidebar
// =============================================================================

function PipelineDetail({
  execution,
  actionLoading,
  onApprove,
  onReject,
  onClose,
}: {
  execution: PipelineExecutionRecord
  actionLoading: string | null
  onApprove: (token: string) => Promise<void>
  onReject: (token: string) => Promise<void>
  onClose: () => void
}) {
  const [showConfig, setShowConfig] = useState(false)
  const [showInputs, setShowInputs] = useState(false)
  const [showOutputs, setShowOutputs] = useState(false)
  const ext = execution as any

  return (
    <>
      <div className="reports-detail-header">
        <div className="reports-detail-header-top">
          <span className="reports-detail-id">{execution.id}</span>
          <button className="reports-detail-close" onClick={onClose}><CloseIcon /></button>
        </div>
        <div className="reports-detail-title">{execution.pipeline_name}</div>
        <div className="reports-detail-status">
          <StatusDot status={execution.status} />
          <span className="reports-cell--status-text">{normalizeStatus(execution.status)}</span>
          {ext.cron_job_name && (
            <span className="reports-detail-trigger">
              <CronIcon /> {ext.cron_job_name}
            </span>
          )}
        </div>
      </div>

      <div className="reports-detail-body">
        {/* Approval banner — actionable, goes first */}
        {execution.status === 'waiting_approval' && (() => {
          const waitingStep = execution.steps.find(
            s => s.status === 'waiting_approval' && s.approval_token
          )
          return waitingStep?.approval_token ? (
            <div className="reports-approval">
              <div className="reports-approval-message">
                <AlertIcon />
                <span>Step &ldquo;{waitingStep.step_id}&rdquo; requires approval</span>
              </div>
              <div className="reports-approval-actions">
                <button
                  type="button"
                  className="reports-btn reports-btn--approve"
                  onClick={() => onApprove(waitingStep.approval_token!)}
                  disabled={actionLoading === waitingStep.approval_token}
                >
                  {actionLoading === waitingStep.approval_token ? 'Approving...' : 'Approve'}
                </button>
                <button
                  type="button"
                  className="reports-btn reports-btn--reject"
                  onClick={() => onReject(waitingStep.approval_token!)}
                  disabled={actionLoading === waitingStep.approval_token}
                >
                  {actionLoading === waitingStep.approval_token ? 'Rejecting...' : 'Reject'}
                </button>
              </div>
            </div>
          ) : null
        })()}

        {/* Execution report — the main content */}
        {execution.steps.length > 0 && (
          <div className="reports-detail-section">
            <span className="reports-detail-label">Execution Report</span>
            <div className="reports-detail-steps">
              {execution.steps.map((step, index) => (
                <StepDisplay key={step.id} step={step} index={index} />
              ))}
            </div>
          </div>
        )}

        {/* Error */}
        {execution.outputs_json && (() => {
          try {
            const outputs = JSON.parse(execution.outputs_json)
            if (outputs.error) {
              return <div className="reports-detail-error">Error: {outputs.error}</div>
            }
          } catch { /* ignore */ }
          return null
        })()}

        {/* Collapsible sections for config/inputs/outputs */}
        {execution.inputs_json && (
          <div className="reports-detail-section">
            <button type="button" className="reports-detail-toggle" onClick={() => setShowInputs(!showInputs)}>
              <ChevronIcon expanded={showInputs} /> Inputs
            </button>
            {showInputs && <div className="reports-detail-code">{formatJson(execution.inputs_json)}</div>}
          </div>
        )}

        {execution.status === 'completed' && execution.outputs_json && (
          <div className="reports-detail-section">
            <button type="button" className="reports-detail-toggle" onClick={() => setShowOutputs(!showOutputs)}>
              <ChevronIcon expanded={showOutputs} /> Outputs
            </button>
            {showOutputs && <div className="reports-detail-code">{formatJson(execution.outputs_json)}</div>}
          </div>
        )}

        {ext.definition_json && (
          <div className="reports-detail-section">
            <button type="button" className="reports-detail-toggle" onClick={() => setShowConfig(!showConfig)}>
              <ChevronIcon expanded={showConfig} /> Pipeline Config
            </button>
            {showConfig && <div className="reports-detail-code">{formatJson(ext.definition_json)}</div>}
          </div>
        )}

        {ext.parent_execution_id && (
          <div className="reports-detail-section">
            <span className="reports-detail-label">Parent</span>
            <span className="reports-detail-value reports-detail-mono">{ext.parent_execution_id}</span>
          </div>
        )}
      </div>
    </>
  )
}

// =============================================================================
// Agent Detail Sidebar
// =============================================================================

function AgentDetail({
  run,
  detail,
  actionLoading,
  onCancel,
  onClose,
}: {
  run: AgentRunRecord
  detail?: AgentRunDetail
  actionLoading: string | null
  onCancel: (runId: string) => Promise<void>
  onClose: () => void
}) {
  const [showPrompt, setShowPrompt] = useState(false)
  const [showResult, setShowResult] = useState(false)

  const totalTokens = (run.usage_input_tokens || 0) + (run.usage_output_tokens || 0)

  return (
    <>
      <div className="reports-detail-header">
        <div className="reports-detail-header-top">
          <span className="reports-detail-id">{run.id}</span>
          <button className="reports-detail-close" onClick={onClose}><CloseIcon /></button>
        </div>
        <div className="reports-detail-title">{run.workflow_name || run.prompt?.slice(0, 80) || 'Agent Run'}</div>
        <div className="reports-detail-status">
          <StatusDot status={run.status} />
          <span className="reports-cell--status-text">{normalizeStatus(run.status)}</span>
        </div>
        <div className="reports-detail-tags">
          <span className="reports-detail-tag">{run.provider}</span>
          {run.model && <span className="reports-detail-tag">{run.model}</span>}
          <span className="reports-detail-tag">{run.mode}</span>
        </div>
      </div>

      <div className="reports-detail-body">
        {/* Cancel — actionable, first */}
        {run.status === 'running' && (
          <div className="reports-detail-section">
            <button
              type="button"
              className="reports-btn reports-btn--cancel"
              onClick={() => onCancel(run.id)}
              disabled={actionLoading === run.id}
            >
              {actionLoading === run.id ? 'Cancelling...' : 'Cancel Agent'}
            </button>
          </div>
        )}

        {/* Summary — the execution narrative */}
        {run.summary_markdown && (
          <div className="reports-detail-section">
            <span className="reports-detail-label">Summary</span>
            <div className="reports-detail-code">{run.summary_markdown}</div>
          </div>
        )}

        {/* Error */}
        {(run.status === 'error' || run.status === 'timeout') && run.error && (
          <div className="reports-detail-error">Error: {run.error}</div>
        )}

        {/* Result */}
        {run.status === 'success' && run.result && (
          <div className="reports-detail-section">
            <button type="button" className="reports-detail-toggle" onClick={() => setShowResult(!showResult)}>
              <ChevronIcon expanded={showResult} /> Result
            </button>
            {showResult && <div className="reports-detail-code">{run.result}</div>}
          </div>
        )}

        {/* Commands — what the agent actually did */}
        {detail?.commands && detail.commands.length > 0 && (
          <div className="reports-detail-section">
            <span className="reports-detail-label">Commands ({detail.commands.length})</span>
            <div className="reports-detail-commands">
              {detail.commands.map(cmd => (
                <div key={cmd.id} className="reports-detail-command">
                  <span className="reports-detail-command-type">{cmd.command_type}</span>
                  <span className="reports-detail-command-time">{formatTime(cmd.created_at)}</span>
                  {cmd.payload && <span className="reports-detail-command-payload">{cmd.payload.slice(0, 80)}</span>}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Stats — compact, not rehashing row data */}
        {totalTokens > 0 && (
          <div className="reports-detail-section">
            <span className="reports-detail-label">Usage</span>
            <div className="reports-detail-stats">
              <div className="reports-detail-stat">
                <span className="reports-detail-stat-label">Input</span>
                <span className="reports-detail-stat-value">{(run.usage_input_tokens || 0).toLocaleString()}</span>
              </div>
              <div className="reports-detail-stat">
                <span className="reports-detail-stat-label">Output</span>
                <span className="reports-detail-stat-value">{(run.usage_output_tokens || 0).toLocaleString()}</span>
              </div>
              {(run.usage_cache_read_tokens || 0) > 0 && (
                <div className="reports-detail-stat">
                  <span className="reports-detail-stat-label">Cache</span>
                  <span className="reports-detail-stat-value">{(run.usage_cache_read_tokens || 0).toLocaleString()}</span>
                </div>
              )}
              {run.usage_total_cost_usd != null && run.usage_total_cost_usd > 0 && (
                <div className="reports-detail-stat">
                  <span className="reports-detail-stat-label">Cost</span>
                  <span className="reports-detail-stat-value reports-detail-stat-value--cost">${run.usage_total_cost_usd.toFixed(4)}</span>
                </div>
              )}
              <div className="reports-detail-stat">
                <span className="reports-detail-stat-label">Tools</span>
                <span className="reports-detail-stat-value">{run.tool_calls_count}</span>
              </div>
            </div>
          </div>
        )}

        {/* Prompt — collapsible, not the main focus */}
        {run.prompt && (
          <div className="reports-detail-section">
            <button type="button" className="reports-detail-toggle" onClick={() => setShowPrompt(!showPrompt)}>
              <ChevronIcon expanded={showPrompt} /> Prompt
            </button>
            {showPrompt && <div className="reports-detail-code">{run.prompt}</div>}
          </div>
        )}

        {/* Context — task, isolation, branch */}
        {(run.task_id || run.worktree_id || run.clone_id || run.git_branch) && (
          <div className="reports-detail-section">
            <span className="reports-detail-label">Context</span>
            {run.task_id && <span className="reports-detail-value reports-detail-mono">Task: {run.task_id}</span>}
            {run.git_branch && <span className="reports-detail-value reports-detail-mono">Branch: {run.git_branch}</span>}
            {(run.worktree_id || run.clone_id) && (
              <span className="reports-detail-value">{run.worktree_id ? `Worktree: ${run.worktree_id}` : `Clone: ${run.clone_id}`}</span>
            )}
          </div>
        )}
      </div>
    </>
  )
}
