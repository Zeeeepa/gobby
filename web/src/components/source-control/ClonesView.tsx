import { useState } from 'react'
import type { CloneInfo } from '../../hooks/useSourceControl'
import { StatusBadge } from './StatusBadge'

interface Props {
  clones: CloneInfo[]
  onDelete: (id: string) => Promise<boolean>
  onSync: (id: string) => Promise<boolean>
}

export function ClonesView({ clones, onDelete, onSync }: Props) {
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null)
  const [actionLoading, setActionLoading] = useState<string | null>(null)

  const statuses = ['active', 'syncing', 'stale', 'cleanup']
  const filtered = statusFilter
    ? clones.filter((c) => c.status === statusFilter)
    : clones

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

  return (
    <div className="sc-clones">
      <div className="sc-filter-chips">
        <button
          className={`sc-filter-chip ${!statusFilter ? 'sc-filter-chip--active' : ''}`}
          onClick={() => setStatusFilter(null)}
          aria-pressed={!statusFilter}
        >
          All ({clones.length})
        </button>
        {statuses.map((s) => {
          const count = clones.filter((c) => c.status === s).length
          if (count === 0) return null
          return (
            <button
              key={s}
              className={`sc-filter-chip ${statusFilter === s ? 'sc-filter-chip--active' : ''}`}
              onClick={() => setStatusFilter(statusFilter === s ? null : s)}
              aria-pressed={statusFilter === s}
            >
              {s} ({count})
            </button>
          )
        })}
      </div>

      {filtered.length === 0 ? (
        <p className="sc-text-muted sc-clones__empty">No clones found</p>
      ) : (
        <div className="sc-card-grid">
          {filtered.map((clone) => (
            <div key={clone.id} className="sc-card">
              <div className="sc-card__header">
                <span className="sc-card__title">{clone.branch_name}</span>
                <StatusBadge status={clone.status} />
              </div>
              <div className="sc-card__body">
                <div className="sc-card__field">
                  <span className="sc-card__label">Path</span>
                  <code className="sc-card__value">{clone.clone_path}</code>
                </div>
                {clone.remote_url && (
                  <div className="sc-card__field">
                    <span className="sc-card__label">Remote</span>
                    <span className="sc-card__value sc-text-muted">{clone.remote_url}</span>
                  </div>
                )}
                {clone.task_id && (
                  <div className="sc-card__field">
                    <span className="sc-card__label">Task</span>
                    <span className="sc-card__value">{clone.task_id}</span>
                  </div>
                )}
                <div className="sc-card__field">
                  <span className="sc-card__label">Created</span>
                  <span className="sc-card__value sc-text-muted">
                    {new Date(clone.created_at).toLocaleDateString()}
                  </span>
                </div>
              </div>
              <div className="sc-card__actions">
                <button
                  className="sc-btn sc-btn--sm"
                  onClick={() => handleSync(clone.id)}
                  disabled={actionLoading === clone.id}
                >
                  {actionLoading === clone.id && confirmDelete !== clone.id ? 'Syncing...' : 'Sync'}
                </button>
                {confirmDelete === clone.id ? (
                  <>
                    <button
                      className="sc-btn sc-btn--sm sc-btn--danger"
                      onClick={() => handleDelete(clone.id)}
                      disabled={actionLoading === clone.id}
                    >
                      {actionLoading === clone.id ? 'Deleting...' : 'Confirm'}
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
                    onClick={() => setConfirmDelete(clone.id)}
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
