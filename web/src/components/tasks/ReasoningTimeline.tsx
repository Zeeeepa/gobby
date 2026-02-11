import { useState } from 'react'
import type { GobbyTaskDetail } from '../../hooks/useTasks'

// =============================================================================
// Phase derivation from task lifecycle
// =============================================================================

interface TimelinePhase {
  key: string
  icon: string
  label: string
  status: 'complete' | 'active' | 'pending'
  timestamp: string | null
  summary: string | null
}

const STATUS_ORDER = ['open', 'in_progress', 'needs_review', 'approved', 'closed']

function derivePhases(task: GobbyTaskDetail): TimelinePhase[] {
  const statusIdx = STATUS_ORDER.indexOf(task.status)
  const isFailed = task.status === 'escalated' || statusIdx === -1

  const phases: TimelinePhase[] = []

  // Plan: task was created
  phases.push({
    key: 'plan',
    icon: '\u{1F4CB}',
    label: 'Plan',
    status: 'complete',
    timestamp: task.created_at,
    summary: `Task created: ${task.title}`,
  })

  // Investigate: work started (in_progress or beyond)
  const investigateReached = statusIdx >= 1 || isFailed
  phases.push({
    key: 'investigate',
    icon: '\u{1F50D}',
    label: 'Investigate',
    status: investigateReached
      ? (statusIdx === 1 && !isFailed ? 'active' : 'complete')
      : 'pending',
    timestamp: investigateReached ? task.updated_at : null,
    summary: task.assignee
      ? `Assigned to ${task.agent_name || task.assignee}`
      : investigateReached ? 'Work started' : null,
  })

  // Act: commits linked or review stage
  const actReached = statusIdx >= 2 || (task.commits && task.commits.length > 0) || isFailed
  phases.push({
    key: 'act',
    icon: '\u{2699}\u{FE0F}',
    label: 'Act',
    status: actReached
      ? (statusIdx === 2 ? 'active' : 'complete')
      : 'pending',
    timestamp: actReached ? task.updated_at : null,
    summary: task.commits && task.commits.length > 0
      ? `${task.commits.length} commit${task.commits.length > 1 ? 's' : ''} linked`
      : actReached ? 'Changes submitted' : null,
  })

  // Verify: validation or close
  const verifyReached = statusIdx >= 3 || task.validation_status !== 'pending' || isFailed
  let verifySummary: string | null = null
  if (isFailed) {
    verifySummary = `Escalated: ${task.escalation_reason || 'needs attention'}`
  } else if (task.validation_status === 'passed' || task.validation_status === 'valid') {
    verifySummary = 'Validation passed'
  } else if (task.validation_status === 'failed') {
    verifySummary = `Validation failed: ${task.validation_feedback || 'see feedback'}`
  } else if (task.closed_at) {
    verifySummary = `Closed: ${task.closed_reason || 'completed'}`
  }

  phases.push({
    key: 'verify',
    icon: '\u{2705}',
    label: 'Verify',
    status: verifyReached
      ? ((statusIdx >= 4 || task.validation_status === 'passed' || task.validation_status === 'valid') ? 'complete' : 'active')
      : 'pending',
    timestamp: task.closed_at || (verifyReached ? task.updated_at : null),
    summary: verifySummary,
  })

  return phases
}

// =============================================================================
// Relative time helper
// =============================================================================

function relativeTime(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime()
  const seconds = Math.floor(diff / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

// =============================================================================
// ReasoningTimeline
// =============================================================================

// =============================================================================
// Intervention buttons per phase
// =============================================================================

type InterventionAction = 'retry' | 'edit_and_run' | 'rollback' | 'mark_resolved'

interface InterventionButton {
  action: InterventionAction
  label: string
  icon: string
  variant: 'default' | 'primary' | 'danger'
}

function getInterventionsForPhase(
  phase: TimelinePhase,
  taskStatus: string,
): InterventionButton[] {
  const isFailed = taskStatus === 'escalated'

  if (phase.status === 'pending') return []

  if (phase.status === 'active') {
    const buttons: InterventionButton[] = [
      { action: 'mark_resolved', label: 'Mark Resolved', icon: '\u2714', variant: 'primary' },
    ]
    if (phase.key !== 'plan') {
      buttons.push({ action: 'retry', label: 'Retry', icon: '\u21BB', variant: 'default' })
    }
    return buttons
  }

  // complete
  const buttons: InterventionButton[] = []

  if (isFailed && phase.key === 'verify') {
    buttons.push({ action: 'retry', label: 'Retry', icon: '\u21BB', variant: 'primary' })
    buttons.push({ action: 'mark_resolved', label: 'Mark Resolved', icon: '\u2714', variant: 'default' })
  } else if (phase.key !== 'plan') {
    buttons.push({ action: 'rollback', label: 'Roll Back', icon: '\u21A9', variant: 'danger' })
    buttons.push({ action: 'retry', label: 'Retry', icon: '\u21BB', variant: 'default' })
  }

  return buttons
}

// =============================================================================
// ReasoningTimeline
// =============================================================================

interface ReasoningTimelineProps {
  task: GobbyTaskDetail
  onIntervene?: (phaseKey: string, action: InterventionAction) => void
}

export function ReasoningTimeline({ task, onIntervene }: ReasoningTimelineProps) {
  const phases = derivePhases(task)
  const [expanded, setExpanded] = useState<Set<string>>(new Set())

  const toggle = (key: string) => {
    setExpanded(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <div className="reasoning-timeline">
      {phases.map((phase, i) => {
        const isExpanded = expanded.has(phase.key)
        const isLast = i === phases.length - 1

        return (
          <div key={phase.key} className={`reasoning-phase reasoning-phase--${phase.status}`}>
            <div className="reasoning-phase-line">
              <span className={`reasoning-phase-dot reasoning-phase-dot--${phase.status}`}>
                {phase.status === 'active' && <span className="reasoning-phase-dot-pulse" />}
              </span>
              {!isLast && <span className={`reasoning-phase-connector reasoning-phase-connector--${phase.status}`} />}
            </div>
            <div className="reasoning-phase-content">
              <button
                className="reasoning-phase-header"
                onClick={() => phase.summary && toggle(phase.key)}
                disabled={!phase.summary}
              >
                <span className="reasoning-phase-icon">{phase.icon}</span>
                <span className="reasoning-phase-label">{phase.label}</span>
                {phase.timestamp && (
                  <span className="reasoning-phase-time">{relativeTime(phase.timestamp)}</span>
                )}
                {phase.summary && (
                  <span className="reasoning-phase-chevron">{isExpanded ? '\u25BE' : '\u25B8'}</span>
                )}
              </button>
              {isExpanded && phase.summary && (
                <div className="reasoning-phase-detail">
                  {phase.summary}
                  {onIntervene && (() => {
                    const buttons = getInterventionsForPhase(phase, task.status)
                    if (buttons.length === 0) return null
                    return (
                      <div className="reasoning-phase-interventions">
                        {buttons.map(btn => (
                          <button
                            key={btn.action}
                            className={`reasoning-intervention-btn reasoning-intervention-btn--${btn.variant}`}
                            onClick={(e) => {
                              e.stopPropagation()
                              onIntervene(phase.key, btn.action)
                            }}
                          >
                            <span className="reasoning-intervention-icon">{btn.icon}</span>
                            {btn.label}
                          </button>
                        ))}
                      </div>
                    )
                  })()}
                </div>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
