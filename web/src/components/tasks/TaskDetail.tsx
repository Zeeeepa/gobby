import { useState, useEffect, useCallback } from 'react'
import type { GobbyTaskDetail } from '../../hooks/useTasks'
import { StatusBadge, PriorityBadge, TypeBadge } from './TaskBadges'

interface TaskActions {
  updateTask: (id: string, params: { status?: string }) => Promise<GobbyTaskDetail | null>
  closeTask: (id: string, reason?: string) => Promise<GobbyTaskDetail | null>
  reopenTask: (id: string) => Promise<GobbyTaskDetail | null>
}

interface TaskDetailProps {
  taskId: string | null
  getTask: (id: string) => Promise<GobbyTaskDetail | null>
  actions: TaskActions
  onClose: () => void
}

function CloseIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" /><line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}

function formatDate(iso: string | null): string {
  if (!iso) return '-'
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
    + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

export function TaskDetail({ taskId, getTask, actions, onClose }: TaskDetailProps) {
  const [task, setTask] = useState<GobbyTaskDetail | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const [actionLoading, setActionLoading] = useState(false)

  const fetchDetail = useCallback(async (id: string) => {
    setIsLoading(true)
    const result = await getTask(id)
    setTask(result)
    setIsLoading(false)
  }, [getTask])

  useEffect(() => {
    if (taskId) {
      fetchDetail(taskId)
    } else {
      setTask(null)
    }
  }, [taskId, fetchDetail])

  const handleAction = useCallback(async (action: () => Promise<GobbyTaskDetail | null>) => {
    setActionLoading(true)
    const updated = await action()
    if (updated) setTask(updated)
    setActionLoading(false)
  }, [])

  const isOpen = taskId !== null

  return (
    <>
      {/* Backdrop */}
      {isOpen && <div className="task-detail-backdrop" onClick={onClose} />}

      {/* Panel */}
      <div className={`task-detail-panel ${isOpen ? 'open' : ''}`}>
        {isLoading ? (
          <div className="task-detail-loading">Loading...</div>
        ) : task ? (
          <>
            {/* Header */}
            <div className="task-detail-header">
              <div className="task-detail-header-top">
                <span className="task-detail-ref">{task.ref}</span>
                <button className="task-detail-close" onClick={onClose} title="Close">
                  <CloseIcon />
                </button>
              </div>
              <h3 className="task-detail-title">{task.title}</h3>
              <div className="task-detail-badges">
                <StatusBadge status={task.status} />
                <PriorityBadge priority={task.priority} />
                <TypeBadge type={task.type} />
              </div>
            </div>

            {/* Actions */}
            <StatusActions
              task={task}
              actions={actions}
              loading={actionLoading}
              onAction={handleAction}
            />

            {/* Metadata */}
            <div className="task-detail-meta">
              <MetaRow label="Assignee" value={task.assignee || 'Unassigned'} />
              <MetaRow label="Created" value={formatDate(task.created_at)} />
              <MetaRow label="Updated" value={formatDate(task.updated_at)} />
              {task.closed_at && <MetaRow label="Closed" value={formatDate(task.closed_at)} />}
              {task.closed_reason && <MetaRow label="Close reason" value={task.closed_reason} />}
              {task.category && <MetaRow label="Category" value={task.category} />}
              {task.path_cache && <MetaRow label="Path" value={task.path_cache} mono />}
              {task.labels && task.labels.length > 0 && (
                <div className="task-detail-meta-row">
                  <span className="task-detail-meta-label">Labels</span>
                  <div className="task-detail-labels">
                    {task.labels.map(l => (
                      <span key={l} className="task-detail-label">{l}</span>
                    ))}
                  </div>
                </div>
              )}
              {task.validation_status && task.validation_status !== 'pending' && (
                <MetaRow label="Validation" value={task.validation_status} />
              )}
            </div>

            {/* Description */}
            {task.description && (
              <div className="task-detail-section">
                <h4 className="task-detail-section-title">Description</h4>
                <div className="task-detail-description">{task.description}</div>
              </div>
            )}

            {/* Validation criteria */}
            {task.validation_criteria && (
              <div className="task-detail-section">
                <h4 className="task-detail-section-title">Validation Criteria</h4>
                <div className="task-detail-description task-detail-criteria">
                  {task.validation_criteria}
                </div>
              </div>
            )}

            {/* Commits */}
            {task.commits && task.commits.length > 0 && (
              <div className="task-detail-section">
                <h4 className="task-detail-section-title">Commits</h4>
                <div className="task-detail-commits">
                  {task.commits.map(sha => (
                    <span key={sha} className="task-detail-commit">{sha.slice(0, 8)}</span>
                  ))}
                </div>
              </div>
            )}
          </>
        ) : null}
      </div>
    </>
  )
}

function MetaRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="task-detail-meta-row">
      <span className="task-detail-meta-label">{label}</span>
      <span className={`task-detail-meta-value ${mono ? 'mono' : ''}`}>{value}</span>
    </div>
  )
}

// =============================================================================
// Status action buttons - contextual by current status
// =============================================================================

interface StatusAction {
  label: string
  variant: 'primary' | 'default' | 'danger'
  onClick: () => Promise<GobbyTaskDetail | null>
}

function getActionsForStatus(
  task: GobbyTaskDetail,
  actions: TaskActions
): StatusAction[] {
  const { status, id } = task

  switch (status) {
    case 'open':
      return [
        { label: 'Start Work', variant: 'primary', onClick: () => actions.updateTask(id, { status: 'in_progress' }) },
        { label: 'Close', variant: 'danger', onClick: () => actions.closeTask(id) },
      ]
    case 'in_progress':
      return [
        { label: 'Submit for Review', variant: 'primary', onClick: () => actions.updateTask(id, { status: 'needs_review' }) },
        { label: 'Close', variant: 'danger', onClick: () => actions.closeTask(id) },
      ]
    case 'needs_review':
      return [
        { label: 'Approve', variant: 'primary', onClick: () => actions.updateTask(id, { status: 'approved' }) },
        { label: 'Reopen', variant: 'default', onClick: () => actions.reopenTask(id) },
      ]
    case 'approved':
      return [
        { label: 'Close', variant: 'primary', onClick: () => actions.closeTask(id) },
        { label: 'Reopen', variant: 'default', onClick: () => actions.reopenTask(id) },
      ]
    case 'closed':
      return [
        { label: 'Reopen', variant: 'default', onClick: () => actions.reopenTask(id) },
      ]
    case 'failed':
    case 'escalated':
      return [
        { label: 'Reopen', variant: 'primary', onClick: () => actions.reopenTask(id) },
      ]
    default:
      return [
        { label: 'Close', variant: 'danger', onClick: () => actions.closeTask(id) },
      ]
  }
}

function StatusActions({
  task,
  actions,
  loading,
  onAction,
}: {
  task: GobbyTaskDetail
  actions: TaskActions
  loading: boolean
  onAction: (action: () => Promise<GobbyTaskDetail | null>) => void
}) {
  const statusActions = getActionsForStatus(task, actions)

  if (statusActions.length === 0) return null

  return (
    <div className="task-detail-actions">
      {statusActions.map(a => (
        <button
          key={a.label}
          className={`task-detail-action-btn task-detail-action-btn--${a.variant}`}
          onClick={() => onAction(a.onClick)}
          disabled={loading}
        >
          {a.label}
        </button>
      ))}
    </div>
  )
}
