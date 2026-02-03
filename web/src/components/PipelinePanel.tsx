import { useState } from 'react'
import type { PipelineExecution, PipelineStep } from '../hooks/usePipeline'

interface PipelinePanelProps {
  executions: PipelineExecution[]
  isConnected: boolean
  onApprove: (token: string) => Promise<unknown>
  onReject: (token: string) => Promise<unknown>
  onClearCompleted: () => void
}

export function PipelinePanel({
  executions,
  isConnected,
  onApprove,
  onReject,
  onClearCompleted,
}: PipelinePanelProps) {
  const [expanded, setExpanded] = useState<Set<string>>(new Set())
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const toggleExpanded = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev)
      if (next.has(id)) {
        next.delete(id)
      } else {
        next.add(id)
      }
      return next
    })
  }

  const handleApprove = async (token: string) => {
    setActionLoading(token)
    try {
      await onApprove(token)
    } finally {
      setActionLoading(null)
    }
  }

  const handleReject = async (token: string) => {
    setActionLoading(token)
    try {
      await onReject(token)
    } finally {
      setActionLoading(null)
    }
  }

  const hasCompleted = executions.some(
    (e) => e.status === 'completed' || e.status === 'failed'
  )

  if (executions.length === 0) {
    return (
      <div className="pipeline-panel pipeline-panel--empty">
        <div className="pipeline-empty">
          <PipelineIcon />
          <p>No pipeline executions</p>
          <span className={`pipeline-status-indicator ${isConnected ? 'connected' : ''}`}>
            {isConnected ? 'Listening for events...' : 'Disconnected'}
          </span>
        </div>
      </div>
    )
  }

  return (
    <div className="pipeline-panel">
      <div className="pipeline-header">
        <h3>Pipeline Executions</h3>
        {hasCompleted && (
          <button className="pipeline-clear-btn" onClick={onClearCompleted}>
            Clear Completed
          </button>
        )}
      </div>
      <div className="pipeline-list">
        {executions.map((execution) => (
          <div
            key={execution.id}
            className={`pipeline-execution pipeline-execution--${execution.status}`}
          >
            <div
              className="pipeline-execution-header"
              onClick={() => toggleExpanded(execution.id)}
            >
              <div className="pipeline-execution-info">
                <StatusBadge status={execution.status} />
                <span className="pipeline-name">{execution.pipelineName}</span>
                <span className="pipeline-id">{execution.id.slice(0, 8)}</span>
              </div>
              <div className="pipeline-execution-meta">
                {execution.startedAt && (
                  <span className="pipeline-time">
                    {formatTime(execution.startedAt)}
                  </span>
                )}
                <ChevronIcon expanded={expanded.has(execution.id)} />
              </div>
            </div>

            {expanded.has(execution.id) && (
              <div className="pipeline-execution-details">
                {/* Approval notification */}
                {execution.approvalRequired && (
                  <div className="pipeline-approval">
                    <div className="pipeline-approval-message">
                      <AlertIcon />
                      <span>{execution.approvalRequired.message}</span>
                    </div>
                    <div className="pipeline-approval-actions">
                      <button
                        className="pipeline-btn pipeline-btn--approve"
                        onClick={() => handleApprove(execution.approvalRequired!.token)}
                        disabled={actionLoading === execution.approvalRequired.token}
                      >
                        {actionLoading === execution.approvalRequired.token
                          ? 'Approving...'
                          : 'Approve'}
                      </button>
                      <button
                        className="pipeline-btn pipeline-btn--reject"
                        onClick={() => handleReject(execution.approvalRequired!.token)}
                        disabled={actionLoading === execution.approvalRequired.token}
                      >
                        {actionLoading === execution.approvalRequired.token
                          ? 'Rejecting...'
                          : 'Reject'}
                      </button>
                    </div>
                  </div>
                )}

                {/* Steps */}
                <div className="pipeline-steps">
                  {execution.steps.map((step, index) => (
                    <StepDisplay key={step.id || index} step={step} index={index} />
                  ))}
                </div>

                {/* Error */}
                {execution.error && (
                  <div className="pipeline-error">
                    <span>Error: {execution.error}</span>
                  </div>
                )}

                {/* Outputs */}
                {execution.outputs && Object.keys(execution.outputs).length > 0 && (
                  <div className="pipeline-outputs">
                    <h4>Outputs</h4>
                    <pre>{JSON.stringify(execution.outputs, null, 2)}</pre>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

function StepDisplay({ step, index }: { step: PipelineStep; index: number }) {
  const [showOutput, setShowOutput] = useState(false)

  return (
    <div className={`pipeline-step pipeline-step--${step.status}`}>
      <div className="pipeline-step-header" onClick={() => setShowOutput(!showOutput)}>
        <div className="pipeline-step-info">
          <StepStatusIcon status={step.status} />
          <span className="pipeline-step-index">{index + 1}.</span>
          <span className="pipeline-step-name">{step.name}</span>
        </div>
        {step.status === 'running' && <Spinner />}
        {step.output !== undefined && <ChevronIcon expanded={showOutput} />}
      </div>

      {showOutput && step.output !== undefined && (
        <div className="pipeline-step-output">
          <pre>{formatOutput(step.output)}</pre>
        </div>
      )}

      {step.error && (
        <div className="pipeline-step-error">
          <span>{step.error}</span>
        </div>
      )}
    </div>
  )
}

function StatusBadge({ status }: { status: string }) {
  const labels: Record<string, string> = {
    pending: 'Pending',
    running: 'Running',
    completed: 'Completed',
    failed: 'Failed',
    waiting_approval: 'Waiting',
    skipped: 'Skipped',
  }
  return <span className={`pipeline-badge pipeline-badge--${status}`}>{labels[status] || status}</span>
}

function StepStatusIcon({ status }: { status: string }) {
  switch (status) {
    case 'completed':
      return <CheckIcon />
    case 'failed':
      return <XIcon />
    case 'running':
      return <CircleIcon className="running" />
    case 'waiting_approval':
      return <ClockIcon />
    case 'skipped':
      return <SkipIcon />
    default:
      return <CircleIcon />
  }
}

function formatTime(date: Date): string {
  return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function formatOutput(output: unknown): string {
  if (typeof output === 'string') return output
  return JSON.stringify(output, null, 2)
}

// Icons
function PipelineIcon() {
  return (
    <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
    </svg>
  )
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      style={{ transform: expanded ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}
    >
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}

function AlertIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  )
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  )
}

function XIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function CircleIcon({ className }: { className?: string }) {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className={className}>
      <circle cx="12" cy="12" r="10" />
    </svg>
  )
}

function ClockIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}

function SkipIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <polygon points="5 4 15 12 5 20 5 4" />
      <line x1="19" y1="5" x2="19" y2="19" />
    </svg>
  )
}

function Spinner() {
  return (
    <svg className="pipeline-spinner" width="14" height="14" viewBox="0 0 24 24">
      <circle
        cx="12"
        cy="12"
        r="10"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeDasharray="31.4"
        strokeDashoffset="10"
      />
    </svg>
  )
}
