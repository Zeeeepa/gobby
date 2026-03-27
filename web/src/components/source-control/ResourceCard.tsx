import { useState } from 'react'
import { StatusBadge } from './StatusBadge'

export interface ResourceField {
  label: string
  value: string
  muted?: boolean
  code?: boolean
}

export interface ResourceCardProps {
  id: string
  title: string
  status: string
  fields: ResourceField[]
  onSync?: (id: string) => Promise<unknown>
  onDelete?: (id: string) => Promise<unknown>
}

export function ResourceCard({ id, title, status, fields, onSync, onDelete }: ResourceCardProps) {
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [loading, setLoading] = useState<'sync' | 'delete' | null>(null)

  const handleSync = async () => {
    if (!onSync) return
    setLoading('sync')
    try {
      await onSync(id)
    } finally {
      setLoading(null)
    }
  }

  const handleDelete = async () => {
    if (!onDelete) return
    setLoading('delete')
    try {
      await onDelete(id)
    } finally {
      setLoading(null)
      setConfirmDelete(false)
    }
  }

  return (
    <div className="sc-card">
      <div className="sc-card__header">
        <span className="sc-card__title">{title}</span>
        <StatusBadge status={status} />
      </div>
      <div className="sc-card__body">
        {fields.map((f) => (
          <div key={f.label} className="sc-card__field">
            <span className="sc-card__label">{f.label}</span>
            {f.code ? (
              <code className="sc-card__value">{f.value}</code>
            ) : (
              <span className={`sc-card__value${f.muted ? ' sc-text-muted' : ''}`}>{f.value}</span>
            )}
          </div>
        ))}
      </div>
      {(onSync || onDelete) && (
        <div className="sc-card__actions">
          {onSync && (
            <button
              className="sc-btn sc-btn--sm"
              onClick={handleSync}
              disabled={loading !== null}
            >
              {loading === 'sync' ? 'Syncing...' : 'Sync'}
            </button>
          )}
          {onDelete && (
            confirmDelete ? (
              <>
                <button
                  className="sc-btn sc-btn--sm sc-btn--danger"
                  onClick={handleDelete}
                  disabled={loading !== null}
                >
                  {loading === 'delete' ? 'Deleting...' : 'Confirm'}
                </button>
                <button
                  className="sc-btn sc-btn--sm"
                  onClick={() => setConfirmDelete(false)}
                >
                  Cancel
                </button>
              </>
            ) : (
              <button
                className="sc-btn sc-btn--sm sc-btn--danger"
                onClick={() => setConfirmDelete(true)}
              >
                Delete
              </button>
            )
          )}
        </div>
      )}
    </div>
  )
}

function formatDate(dateStr: string): string {
  const d = new Date(dateStr)
  return isNaN(d.getTime()) ? '-' : d.toLocaleDateString()
}

export function worktreeToFields(wt: { worktree_path: string; task_id: string | null; agent_session_id: string | null; created_at: string }): ResourceField[] {
  const fields: ResourceField[] = [
    { label: 'Path', value: wt.worktree_path, code: true },
  ]
  if (wt.task_id) fields.push({ label: 'Task', value: wt.task_id })
  if (wt.agent_session_id) fields.push({ label: 'Session', value: wt.agent_session_id, muted: true })
  fields.push({ label: 'Created', value: formatDate(wt.created_at), muted: true })
  return fields
}

export function cloneToFields(clone: { clone_path: string; remote_url: string | null; task_id: string | null; created_at: string }): ResourceField[] {
  const fields: ResourceField[] = [
    { label: 'Path', value: clone.clone_path, code: true },
  ]
  if (clone.remote_url) fields.push({ label: 'Remote', value: clone.remote_url, muted: true })
  if (clone.task_id) fields.push({ label: 'Task', value: clone.task_id })
  fields.push({ label: 'Created', value: formatDate(clone.created_at), muted: true })
  return fields
}
