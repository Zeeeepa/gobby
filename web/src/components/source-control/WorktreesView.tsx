import { useState, useMemo } from 'react'
import type { WorktreeInfo } from '../../hooks/useSourceControl'
import { ResourceCard, worktreeToFields } from './ResourceCard'

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
  const [confirmCleanup, setConfirmCleanup] = useState(false)
  const [cleanupLoading, setCleanupLoading] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)
  const [cleanupHours, setCleanupHours] = useState(24)
  const filtered = statusFilter
    ? worktrees.filter((w) => w.status === statusFilter)
    : worktrees

  const statusCounts = useMemo(() => {
    const counts = new Map<string, number>()
    for (const w of worktrees) {
      counts.set(w.status, (counts.get(w.status) || 0) + 1)
    }
    return counts
  }, [worktrees])

  const handleCleanup = async () => {
    setCleanupLoading(true)
    setActionError(null)
    try {
      await onCleanup(cleanupHours, false)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Failed to cleanup worktrees')
    } finally {
      setCleanupLoading(false)
      setConfirmCleanup(false)
    }
  }

  const handleAction = async (action: (id: string) => Promise<boolean>, id: string, errorMsg: string) => {
    setActionError(null)
    try {
      await action(id)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : errorMsg)
    }
  }

  return (
    <div className="sc-worktrees">
      {actionError && (
        <p className="sc-text-muted" style={{ color: 'var(--color-error)', padding: '8px 0' }}>{actionError}</p>
      )}
      <div className="sc-worktrees__toolbar">
        <div className="sc-filter-chips">
          <button
            className={`sc-filter-chip ${!statusFilter ? 'sc-filter-chip--active' : ''}`}
            onClick={() => setStatusFilter(null)}
          >
            All ({worktrees.length})
          </button>
          {STATUSES.map((s) => {
            const count = statusCounts.get(s) || 0
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
                aria-label="Cleanup threshold in hours"
              />
              <span className="sc-text-muted">hours?</span>
              <button
                className="sc-btn sc-btn--sm sc-btn--danger"
                onClick={handleCleanup}
                disabled={cleanupLoading}
              >
                {cleanupLoading ? 'Cleaning...' : 'Confirm'}
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
            <ResourceCard
              key={wt.id}
              id={wt.id}
              title={wt.branch_name}
              status={wt.status}
              fields={worktreeToFields(wt)}
              onSync={(id) => handleAction(onSync, id, 'Failed to sync worktree')}
              onDelete={(id) => handleAction(onDelete, id, 'Failed to delete worktree')}
            />
          ))}
        </div>
      )}
    </div>
  )
}
