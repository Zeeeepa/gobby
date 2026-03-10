import { useState, useMemo, useCallback, useEffect } from 'react'
import { usePipelineExecutions } from '../../hooks/usePipelineExecutions'
import type { PipelineExecutionRecord } from '../../hooks/usePipelineExecutions'
import { useAgentRuns } from '../../hooks/useAgentRuns'
import type { AgentRunRecord, AgentRunDetail } from '../../hooks/useAgentRuns'
import {
  StatusBadge,
  StepDisplay,
  ChevronIcon,
  AlertIcon,
  PipelineIcon,
  AgentIcon,
  formatTime,
  formatDuration,
  formatJson,
} from './execution-utils'
import './PipelinesPage.css'

type TypeFilter = 'all' | 'pipelines' | 'agents'
type StatusFilter = 'all' | 'running' | 'waiting' | 'completed' | 'failed'

interface ReportingTabProps {
  searchText: string
  projectId?: string
  refreshKey?: number
}

interface TimelineEntry {
  kind: 'pipeline' | 'agent'
  id: string
  name: string
  status: string
  created_at: string
  completed_at: string | null
  pipeline?: PipelineExecutionRecord
  agent?: AgentRunRecord
}

// Normalize agent statuses to filter categories
function statusMatchesFilter(status: string, filter: StatusFilter): boolean {
  if (filter === 'all') return true
  if (filter === 'running') return status === 'running' || status === 'pending'
  if (filter === 'waiting') return status === 'waiting_approval'
  if (filter === 'completed') return status === 'completed' || status === 'success'
  if (filter === 'failed') return status === 'failed' || status === 'error' || status === 'timeout' || status === 'cancelled' || status === 'interrupted'
  return true
}

const TYPE_OPTIONS: { value: TypeFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'pipelines', label: 'Pipelines' },
  { value: 'agents', label: 'Agents' },
]

const STATUS_OPTIONS: { value: StatusFilter; label: string }[] = [
  { value: 'all', label: 'All' },
  { value: 'running', label: 'Running' },
  { value: 'waiting', label: 'Waiting' },
  { value: 'completed', label: 'Completed' },
  { value: 'failed', label: 'Failed' },
]

export function ReportingTab({ searchText, projectId, refreshKey }: ReportingTabProps) {
  const [typeFilter, setTypeFilter] = useState<TypeFilter>('all')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all')
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
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

  // Refetch when refreshKey changes (handled inside hooks via WebSocket, but
  // refreshKey is a manual signal from the toolbar button)
  useEffect(() => {
    // hooks auto-refetch, no-op needed here
  }, [refreshKey])

  // Merge into unified timeline
  const timeline = useMemo<TimelineEntry[]>(() => {
    const entries: TimelineEntry[] = []

    if (typeFilter !== 'agents') {
      for (const pe of pipelineExecutions) {
        if (!statusMatchesFilter(pe.status, statusFilter)) continue
        entries.push({
          kind: 'pipeline',
          id: pe.id,
          name: pe.pipeline_name,
          status: pe.status,
          created_at: pe.created_at,
          completed_at: pe.completed_at,
          pipeline: pe,
        })
      }
    }

    if (typeFilter !== 'pipelines') {
      for (const ar of agentRuns) {
        if (!statusMatchesFilter(ar.status, statusFilter)) continue
        entries.push({
          kind: 'agent',
          id: ar.id,
          name: ar.workflow_name || 'Agent Run',
          status: ar.status,
          created_at: ar.created_at,
          completed_at: ar.completed_at,
          agent: ar,
        })
      }
    }

    // Filter by search
    if (searchText.trim()) {
      const q = searchText.toLowerCase()
      return entries
        .filter(e => e.name.toLowerCase().includes(q) || e.id.toLowerCase().includes(q))
        .sort((a, b) => b.created_at.localeCompare(a.created_at))
    }

    return entries.sort((a, b) => b.created_at.localeCompare(a.created_at))
  }, [pipelineExecutions, agentRuns, typeFilter, statusFilter, searchText])

  const toggleExpanded = useCallback(async (id: string, kind: 'pipeline' | 'agent') => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
        // Fetch agent detail on expand
        if (kind === 'agent' && !agentDetails[id]) {
          fetchRunDetail(id).then(detail => {
            if (detail) setAgentDetails(prev => ({ ...prev, [id]: detail }))
          })
        }
      }
      return next
    })
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

  const isLoading = pipelinesLoading || agentsLoading

  return (
    <div className="workflows-content">
      {/* Type toggle */}
      <div className="pipelines-sub-tabs">
        {TYPE_OPTIONS.map(opt => (
          <button
            key={opt.value}
            type="button"
            className={`pipelines-sub-tab ${typeFilter === opt.value ? 'pipelines-sub-tab--active' : ''}`}
            onClick={() => setTypeFilter(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {/* Status filter chips */}
      <div className="pipeline-exec-filters">
        {STATUS_OPTIONS.map(opt => (
          <button
            key={opt.value}
            type="button"
            className={`pipeline-exec-filter-chip ${statusFilter === opt.value ? 'pipeline-exec-filter-chip--active' : ''}`}
            onClick={() => setStatusFilter(opt.value)}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="workflows-loading">Loading...</div>
      ) : timeline.length === 0 ? (
        <div className="pipeline-panel pipeline-panel--empty">
          <div className="pipeline-empty">
            <PipelineIcon />
            <p>No executions match the current filters.</p>
          </div>
        </div>
      ) : (
        <div className="pipeline-panel">
          <div className="pipeline-list" style={{ maxHeight: 'none' }}>
            {timeline.map(entry => (
              <div
                key={entry.id}
                className={`pipeline-execution pipeline-execution--${entry.status}`}
              >
                <div
                  className="pipeline-execution-header"
                  role="button"
                  tabIndex={0}
                  onClick={() => toggleExpanded(entry.id, entry.kind)}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggleExpanded(entry.id, entry.kind) } }}
                >
                  <div className="pipeline-execution-info">
                    {entry.kind === 'pipeline' ? (
                      <span className="reporting-kind-icon" title="Pipeline">
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2" /></svg>
                      </span>
                    ) : (
                      <span className="reporting-kind-icon" title="Agent"><AgentIcon /></span>
                    )}
                    <StatusBadge status={entry.status} />
                    <span className="pipeline-name">{entry.name}</span>
                    <span className="pipeline-id">{entry.id.slice(0, 12)}</span>
                  </div>
                  <div className="pipeline-execution-meta">
                    <span className="pipeline-time">{formatTime(entry.created_at)}</span>
                    {entry.completed_at && (
                      <span className="pipeline-step-timing">
                        {formatDuration(entry.created_at, entry.completed_at)}
                      </span>
                    )}
                    <ChevronIcon expanded={expanded.has(entry.id)} />
                  </div>
                </div>

                {expanded.has(entry.id) && entry.kind === 'pipeline' && entry.pipeline && (
                  <PipelineDrillDown
                    execution={entry.pipeline}
                    actionLoading={actionLoading}
                    onApprove={handleApprove}
                    onReject={handleReject}
                  />
                )}

                {expanded.has(entry.id) && entry.kind === 'agent' && entry.agent && (
                  <AgentDrillDown
                    run={entry.agent}
                    detail={agentDetails[entry.id]}
                    actionLoading={actionLoading}
                    onCancel={handleCancel}
                  />
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Pipeline Drill-Down ──

function PipelineDrillDown({
  execution,
  actionLoading,
  onApprove,
  onReject,
}: {
  execution: PipelineExecutionRecord
  actionLoading: string | null
  onApprove: (token: string) => Promise<void>
  onReject: (token: string) => Promise<void>
}) {
  const [showConfig, setShowConfig] = useState(false)

  return (
    <div className="pipeline-execution-details">
      {/* Trigger info */}
      {(execution as any).cron_job_name && (
        <div className="reporting-detail-section">
          <span className="reporting-detail-label">Trigger:</span>
          <span>Cron: {(execution as any).cron_job_name} ({(execution as any).cron_expr})</span>
        </div>
      )}

      {/* Definition snapshot */}
      {(execution as any).definition_json && (
        <div className="reporting-detail-section">
          <button
            type="button"
            className="reporting-config-toggle"
            onClick={() => setShowConfig(!showConfig)}
          >
            <ChevronIcon expanded={showConfig} />
            <span>Pipeline Config</span>
          </button>
          {showConfig && (
            <div className="reporting-config-block">
              <pre>{formatJson((execution as any).definition_json)}</pre>
            </div>
          )}
        </div>
      )}

      {/* Inputs */}
      {execution.inputs_json && (
        <div className="reporting-detail-section">
          <h4>Inputs</h4>
          <pre>{formatJson(execution.inputs_json)}</pre>
        </div>
      )}

      {/* Parent link */}
      {(execution as any).parent_execution_id && (
        <div className="reporting-detail-section">
          <span className="reporting-detail-label">Parent:</span>
          <span>{(execution as any).parent_execution_id.slice(0, 12)}</span>
        </div>
      )}

      {/* Approval banner */}
      {execution.status === 'waiting_approval' && (() => {
        const waitingStep = execution.steps.find(
          s => s.status === 'waiting_approval' && s.approval_token
        )
        return waitingStep?.approval_token ? (
          <div className="pipeline-approval">
            <div className="pipeline-approval-message">
              <AlertIcon />
              <span>Step "{waitingStep.step_id}" requires approval</span>
            </div>
            <div className="pipeline-approval-actions">
              <button
                type="button"
                className="pipeline-btn pipeline-btn--approve"
                onClick={() => onApprove(waitingStep.approval_token!)}
                disabled={actionLoading === waitingStep.approval_token}
              >
                {actionLoading === waitingStep.approval_token ? 'Approving...' : 'Approve'}
              </button>
              <button
                type="button"
                className="pipeline-btn pipeline-btn--reject"
                onClick={() => onReject(waitingStep.approval_token!)}
                disabled={actionLoading === waitingStep.approval_token}
              >
                {actionLoading === waitingStep.approval_token ? 'Rejecting...' : 'Reject'}
              </button>
            </div>
          </div>
        ) : null
      })()}

      {/* Steps */}
      {execution.steps.length > 0 && (
        <div className="pipeline-steps">
          {execution.steps.map((step, index) => (
            <StepDisplay key={step.id} step={step} index={index} />
          ))}
        </div>
      )}

      {/* Error */}
      {execution.outputs_json && (() => {
        try {
          const outputs = JSON.parse(execution.outputs_json)
          if (outputs.error) {
            return (
              <div className="pipeline-error">
                <span>Error: {outputs.error}</span>
              </div>
            )
          }
        } catch { /* ignore */ }
        return null
      })()}

      {/* Outputs */}
      {execution.status === 'completed' && execution.outputs_json && (
        <div className="pipeline-outputs">
          <h4>Outputs</h4>
          <pre>{formatJson(execution.outputs_json)}</pre>
        </div>
      )}
    </div>
  )
}

// ── Agent Drill-Down ──

function AgentDrillDown({
  run,
  detail,
  actionLoading,
  onCancel,
}: {
  run: AgentRunRecord
  detail?: AgentRunDetail
  actionLoading: string | null
  onCancel: (runId: string) => Promise<void>
}) {
  const [showPrompt, setShowPrompt] = useState(false)
  const [showResult, setShowResult] = useState(false)

  const totalTokens = (run.usage_input_tokens || 0) + (run.usage_output_tokens || 0)

  return (
    <div className="pipeline-execution-details">
      {/* Header badges */}
      <div className="reporting-detail-section reporting-badges-row">
        <span className="pipeline-badge pipeline-badge--provider">{run.provider}</span>
        {run.model && <span className="pipeline-badge pipeline-badge--model">{run.model}</span>}
        <span className="pipeline-badge pipeline-badge--mode">{run.mode}</span>
      </div>

      {/* Prompt */}
      <div className="reporting-detail-section">
        <button
          type="button"
          className="reporting-config-toggle"
          onClick={() => setShowPrompt(!showPrompt)}
        >
          <ChevronIcon expanded={showPrompt} />
          <span>Prompt</span>
        </button>
        {showPrompt && (
          <div className="reporting-config-block">
            <pre>{run.prompt}</pre>
          </div>
        )}
      </div>

      {/* Stats grid */}
      <div className="reporting-stats-grid">
        <div className="reporting-stat">
          <span className="reporting-stat-label">Turns</span>
          <span className="reporting-stat-value">{run.turns_used}</span>
        </div>
        <div className="reporting-stat">
          <span className="reporting-stat-label">Tool Calls</span>
          <span className="reporting-stat-value">{run.tool_calls_count}</span>
        </div>
        {run.started_at && run.completed_at && (
          <div className="reporting-stat">
            <span className="reporting-stat-label">Duration</span>
            <span className="reporting-stat-value">{formatDuration(run.started_at, run.completed_at)}</span>
          </div>
        )}
        {totalTokens > 0 && (
          <div className="reporting-stat">
            <span className="reporting-stat-label">Tokens</span>
            <span className="reporting-stat-value">
              {(run.usage_input_tokens || 0).toLocaleString()} in / {(run.usage_output_tokens || 0).toLocaleString()} out
            </span>
          </div>
        )}
        {(run.usage_cache_read_tokens || 0) > 0 && (
          <div className="reporting-stat">
            <span className="reporting-stat-label">Cache</span>
            <span className="reporting-stat-value">
              {(run.usage_cache_read_tokens || 0).toLocaleString()} read / {(run.usage_cache_creation_tokens || 0).toLocaleString()} created
            </span>
          </div>
        )}
        {run.usage_total_cost_usd != null && run.usage_total_cost_usd > 0 && (
          <div className="reporting-stat">
            <span className="reporting-stat-label">Cost</span>
            <span className="reporting-stat-value">${run.usage_total_cost_usd.toFixed(4)}</span>
          </div>
        )}
      </div>

      {/* Summary markdown */}
      {run.summary_markdown && (
        <div className="reporting-detail-section">
          <h4>Summary</h4>
          <div className="reporting-config-block">
            <pre>{run.summary_markdown}</pre>
          </div>
        </div>
      )}

      {/* Task link */}
      {run.task_id && (
        <div className="reporting-detail-section">
          <span className="reporting-detail-label">Task:</span>
          <span>{run.task_id}</span>
        </div>
      )}

      {/* Isolation context */}
      {(run.worktree_id || run.clone_id) && (
        <div className="reporting-detail-section">
          <span className="reporting-detail-label">Isolation:</span>
          <span>{run.worktree_id ? `worktree: ${run.worktree_id}` : `clone: ${run.clone_id}`}</span>
        </div>
      )}

      {/* Git branch */}
      {run.git_branch && (
        <div className="reporting-detail-section">
          <span className="reporting-detail-label">Branch:</span>
          <span>{run.git_branch}</span>
        </div>
      )}

      {/* Result (success) */}
      {run.status === 'success' && run.result && (
        <div className="reporting-detail-section">
          <button
            type="button"
            className="reporting-config-toggle"
            onClick={() => setShowResult(!showResult)}
          >
            <ChevronIcon expanded={showResult} />
            <span>Result</span>
          </button>
          {showResult && (
            <div className="reporting-config-block">
              <pre>{run.result}</pre>
            </div>
          )}
        </div>
      )}

      {/* Error */}
      {(run.status === 'error' || run.status === 'timeout') && run.error && (
        <div className="pipeline-error">
          <span>Error: {run.error}</span>
        </div>
      )}

      {/* Commands */}
      {detail?.commands && detail.commands.length > 0 && (
        <div className="reporting-detail-section">
          <h4>Commands ({detail.commands.length})</h4>
          <div className="reporting-config-block">
            {detail.commands.map(cmd => (
              <div key={cmd.id} className="reporting-command-entry">
                <span className="pipeline-badge pipeline-badge--{cmd.status}">{cmd.command_type}</span>
                <span className="pipeline-time">{formatTime(cmd.created_at)}</span>
                {cmd.payload && <span className="pipeline-id">{cmd.payload.slice(0, 60)}</span>}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Cancel button */}
      {run.status === 'running' && (
        <div className="reporting-detail-section">
          <button
            type="button"
            className="pipeline-btn pipeline-btn--reject"
            onClick={() => onCancel(run.id)}
            disabled={actionLoading === run.id}
          >
            {actionLoading === run.id ? 'Cancelling...' : 'Cancel Agent'}
          </button>
        </div>
      )}
    </div>
  )
}
