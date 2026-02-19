import { useState } from 'react'
import type { WorktreeInfo } from '../../hooks/useSourceControl'
import { StatusBadge } from './StatusBadge'

interface Props {
  worktrees: WorktreeInfo[]
  onDelete: (id: string) => Promise<boolean>
  onSync: (id: string) => Promise<boolean>
  onCleanup: (hours?: number, dryRun?: boolean) => Promise<WorktreeInfo[]>
}

type StatusFilter = string | null

const STATUSES = ['active', 'stale', 'merged', 'abandoned'] as const

export function WorktreesView({ worktrees, onDelete, onSync, onCleanup }: Props) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [confirmCleanup, setConfirmCleanup] = useState(false)
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const filtered = statusFilter
    ? worktrees.filter((w) => w.status === statusFilter)
    : worktrees

  const handleDelete = async (id: string) => {
    setActionLoading(id)
    try {
      await onDelete(id)
    } finally {
      setActionLoading(null)
      setConfirmDelete(null)
    }
  }

  const handleSync = async (id: string) => {
    setActionLoading(id)
    try {
      await onSync(id)
    } finally {
      setActionLoading(null)
    }
  }

  const handleCleanup = async () => {
    setActionLoading('cleanup')
    try {
      await onCleanup(cleanupHours, false)
    } finally {
      setActionLoading(null)
      setConfirmCleanup(false)
    }
  }

  const [cleanupHours, setCleanupHours] = useState(24)

  return (
    <div className="sc-worktrees">
      <div className="sc-worktrees__toolbar">
        <div className="sc-filter-chips">
          <button
            className={`sc-filter-chip ${!statusFilter ? 'sc-filter-chip--active' : ''}`}
            onClick={() => setStatusFilter(null)}
          >
            All ({worktrees.length})
          </button>
          {STATUSES.map((s) => {
            const count = worktrees.filter((w) => w.status === s).length
            if (count === 0) return null
            return (
              <button
                key={s}
                className={`sc-filter-chip ${statusFilter === s ? 'sc-filter-chip--active' : ''}`}
                onClick={() => setStatusFilter(statusFilter === s ? null : s)}
              >
                {s} ({count})
              </button>
            )
          })}
        </div>
        <div className="sc-worktrees__actions">
          {confirmCleanup ? (
            <div className="sc-worktrees__confirm">
              <span className="sc-text-muted">Older than</span>
              <input
                type="number"
                min={1}
                value={cleanupHours}
                onChange={(e) => setCleanupHours(Math.max(1, Number(e.target.value)))}
                className="sc-input sc-input--sm"
                style={{ width: '4em' }}
              />
              <span className="sc-text-muted">hours?</span>
              <button
                className="sc-btn sc-btn--sm sc-btn--danger"
                onClick={handleCleanup}
                disabled={actionLoading === 'cleanup'}
              >
                {actionLoading === 'cleanup' ? 'Cleaning...' : 'Confirm'}
              </button>
              <button
                className="sc-btn sc-btn--sm"
                onClick={() => setConfirmCleanup(false)}
              >
                Cancel
              </button>
            </div>
          ) : (
            <button
              className="sc-btn sc-btn--sm"
              onClick={() => setConfirmCleanup(true)}
            >
              Cleanup Stale
            </button>
          )}
        </div>
      </div>

      {filtered.length === 0 ? (
        <p className="sc-text-muted sc-worktrees__empty">No worktrees found</p>
      ) : (
        <div className="sc-card-grid">
          {filtered.map((wt) => (
            <div key={wt.id} className="sc-card">
              <div className="sc-card__header">
                <span className="sc-card__title">{wt.branch_name}</span>
                <StatusBadge status={wt.status} />
              </div>
              <div className="sc-card__body">
                <div className="sc-card__field">
                  <span className="sc-card__label">Path</span>
                  <code className="sc-card__value">{wt.worktree_path}</code>
                </div>
                {wt.task_id && (
                  <div className="sc-card__field">
                    <span className="sc-card__label">Task</span>
                    <span className="sc-card__value">{wt.task_id}</span>
                  </div>
                )}
                {wt.agent_session_id && (
                  <div className="sc-card__field">
                    <span className="sc-card__label">Session</span>
                    <span className="sc-card__value sc-text-muted">{wt.agent_session_id}</span>
                  </div>
                )}
                <div className="sc-card__field">
                  <span className="sc-card__label">Created</span>
                  <span className="sc-card__value sc-text-muted">
                    {new Date(wt.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
              <div className="sc-card__actions">
                <button
                  className="sc-btn sc-btn--sm"
                  onClick={() => handleSync(wt.id)}
                  disabled={actionLoading === wt.id}
                >
                  Sync
                </button>
                {confirmDelete === wt.id ? (
                  <>
                    <button
                      className="sc-btn sc-btn--sm sc-btn--danger"
                      onClick={() => handleDelete(wt.id)}
                      disabled={actionLoading === wt.id}
                    >
                      {actionLoading === wt.id ? 'Deleting...' : 'Confirm'}
                    </button>
                    <button
                      className="sc-btn sc-btn--sm"
                      onClick={() => setConfirmDelete(null)}
                    >
                      Cancel
                    </button>
                  </>
                ) : (
                  <button
                    className="sc-btn sc-btn--sm sc-btn--danger"
                    onClick={() => setConfirmDelete(wt.id)}
                  >
                    Delete
                  </button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
