import { useState } from 'react'
import type { CloneInfo } from '../../hooks/useSourceControl'
import { ResourceCard, cloneToFields } from './ResourceCard'

interface Props {
  clones: CloneInfo[]
  onDelete: (id: string) => Promise<boolean>
  onSync: (id: string) => Promise<boolean>
}

export function ClonesView({ clones, onDelete, onSync }: Props) {
  const [statusFilter, setStatusFilter] = useState<string | null>(null)
  const [actionError, setActionError] = useState<string | null>(null)

  const statuses = ['active', 'syncing', 'stale', 'cleanup']
  const filtered = statusFilter
    ? clones.filter((c) => c.status === statusFilter)
    : clones

  const handleAction = async (action: (id: string) => Promise<boolean>, id: string, errorMsg: string) => {
    setActionError(null)
    try {
      await action(id)
    } catch (e) {
      setActionError(e instanceof Error ? e.message : errorMsg)
    }
  }

  return (
    <div className="sc-clones">
      {actionError && (
        <p className="sc-text-muted" style={{ color: 'var(--color-error)', padding: '8px 0' }}>{actionError}</p>
      )}
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
            <ResourceCard
              key={clone.id}
              id={clone.id}
              title={clone.branch_name}
              status={clone.status}
              fields={cloneToFields(clone)}
              onSync={(id) => handleAction(onSync, id, 'Failed to sync clone')}
              onDelete={(id) => handleAction(onDelete, id, 'Failed to delete clone')}
            />
          ))}
        </div>
      )}
    </div>
  )
}
