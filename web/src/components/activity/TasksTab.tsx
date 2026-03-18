import { memo, useState, useEffect, useCallback } from 'react'
import '../tasks/task-execution.css'
import type { GobbyTask } from '../../hooks/useTasks'
import { Markdown } from '../chat/Markdown'

interface TasksTabProps {
  projectId?: string | null
}

interface GobbyTaskDetail extends GobbyTask {
  description: string | null
  category: string | null
  validation_criteria: string | null
  closed_at: string | null
}

const CLOSED_STATUSES = new Set(['closed', 'review_approved'])

const STATUS_DOT_COLORS: Record<string, string> = {
  open: '#3b82f6',
  in_progress: '#f59e0b',
  needs_review: '#8b5cf6',
  review_approved: '#22c55e',
  closed: '#737373',
  escalated: '#ef4444',
}

const PRIORITY_LABELS: Record<number, string> = {
  0: 'Critical',
  1: 'High',
  2: 'Medium',
  3: 'Low',
  4: 'Backlog',
}

const PRIORITY_TEXT_COLORS: Record<number, string> = {
  0: 'var(--status-escalated, #ef4444)',  // critical
  1: 'var(--status-escalated, #ef4444)',  // high
  2: 'var(--status-progress, #f59e0b)',   // medium
  3: 'var(--text-secondary, #a3a3a3)',    // low
  4: 'var(--text-muted, #737373)',        // backlog
}

function getBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || ''
}

export const TasksTab = memo(function TasksTab({ projectId }: TasksTabProps) {
  const [tasks, setTasks] = useState<GobbyTask[]>([])
  const [loading, setLoading] = useState(true)
  const [showClosed, setShowClosed] = useState(false)
  const [search, setSearch] = useState('')
  const [expandedId, setExpandedId] = useState<string | null>(null)
  const [taskDetail, setTaskDetail] = useState<GobbyTaskDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // Fetch tasks — only non-closed by default
  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    const baseUrl = getBaseUrl()
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    if (!showClosed) params.set('status', 'open')
    params.set('limit', '500')
    fetch(`${baseUrl}/api/tasks?${params}`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : { tasks: [] }))
      .then((data) => setTasks(data.tasks ?? []))
      .catch((err) => { if (err.name !== 'AbortError') setTasks([]) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [projectId, showClosed])

  // Fetch task detail when expanded
  useEffect(() => {
    if (!expandedId) { setTaskDetail(null); return }
    const controller = new AbortController()
    setDetailLoading(true)
    const baseUrl = getBaseUrl()
    fetch(`${baseUrl}/api/tasks/${expandedId}`, { signal: controller.signal })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setTaskDetail(data?.id ? data : (data?.task ?? null)))
      .catch((err) => { if (err.name !== 'AbortError') setTaskDetail(null) })
      .finally(() => { if (!controller.signal.aborted) setDetailLoading(false) })
    return () => controller.abort()
  }, [expandedId])

  const toggleExpand = useCallback((id: string) => {
    setExpandedId((prev) => (prev === id ? null : id))
  }, [])

  // Flat list sorted by priority then recency
  const q = search.toLowerCase().trim()
  const filtered = tasks
    .filter((t) => {
      if (!showClosed && CLOSED_STATUSES.has(t.status)) return false
      if (!q) return true
      return t.title.toLowerCase().includes(q) || t.ref.toLowerCase().includes(q)
    })
    .sort((a, b) => {
      // Priority first (lower = higher priority)
      const pa = a.priority ?? 3
      const pb = b.priority ?? 3
      if (pa !== pb) return pa - pb
      // Then by recency (newer first)
      return (b.created_at ?? '').localeCompare(a.created_at ?? '')
    })

  if (loading) {
    return <div className="activity-tab-empty"><p>Loading tasks...</p></div>
  }

  return (
    <div className="flex flex-col h-full">
      {/* Compact toolbar */}
      <div className="paneltask-toolbar">
        <input
          type="text"
          className="paneltask-search"
          placeholder="Filter..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <label className="paneltask-toggle">
          <input type="checkbox" checked={showClosed} onChange={(e) => setShowClosed(e.target.checked)} />
          Closed
        </label>
        <span className="paneltask-count">{filtered.length}</span>
      </div>

      {/* Flat task list */}
      <div className="flex-1 overflow-y-auto">
        {filtered.length === 0 ? (
          <div className="activity-tab-empty">
            <p>No {showClosed ? '' : 'open '}tasks</p>
          </div>
        ) : (
          filtered.map((task) => {
            const isExpanded = task.id === expandedId
            const ref = task.seq_num != null ? `#${task.seq_num}` : null
            const isClosed = CLOSED_STATUSES.has(task.status)
            const dotColor = STATUS_DOT_COLORS[task.status] ?? '#737373'
            const textColor = PRIORITY_TEXT_COLORS[task.priority ?? 3] ?? 'var(--text-secondary)'

            return (
              <div key={task.id}>
                <div
                  className={`paneltask-row${isExpanded ? ' paneltask-row--expanded' : ''}${isClosed ? ' paneltask-row--closed' : ''}`}
                  onClick={() => toggleExpand(task.id)}
                >
                  <span
                    className="paneltask-status-dot"
                    style={{ backgroundColor: dotColor }}
                  />
                  {ref && <span className="paneltask-ref">{ref}</span>}
                  <span className="paneltask-row-title" style={{ color: textColor }}>
                    {task.title}
                  </span>
                  <span className={`paneltask-row-arrow${isExpanded ? ' paneltask-row-arrow--open' : ''}`}>
                    {'\u203A'}
                  </span>
                </div>

                {/* Accordion detail */}
                {isExpanded && (
                  <div className="paneltask-accordion">
                    {detailLoading ? (
                      <p className="text-xs text-muted-foreground px-3 py-2">Loading...</p>
                    ) : taskDetail ? (
                      <TaskAccordionDetail task={taskDetail} />
                    ) : (
                      <p className="text-xs text-muted-foreground px-3 py-2">Task not found</p>
                    )}
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
})

function TaskAccordionDetail({ task }: { task: GobbyTaskDetail }) {
  const priorityLabel = PRIORITY_LABELS[task.priority ?? 4] ?? 'Backlog'

  return (
    <div className="paneltask-accordion-content">
      <div className="paneltask-accordion-meta">
        <span className="paneltask-accordion-status">{task.status.replace(/_/g, ' ')}</span>
        <span className="paneltask-detail-sep">{'\u00B7'}</span>
        <span>{priorityLabel}</span>
        {task.task_type !== 'task' && (
          <>
            <span className="paneltask-detail-sep">{'\u00B7'}</span>
            <span>{task.task_type}</span>
          </>
        )}
        {task.assignee && (
          <>
            <span className="paneltask-detail-sep">{'\u00B7'}</span>
            <span>{task.assignee}</span>
          </>
        )}
      </div>

      {task.description && (
        <div className="paneltask-accordion-section">
          <div className="message-content text-xs">
            <Markdown content={task.description} id={`task-desc-${task.id}`} />
          </div>
        </div>
      )}

      {task.validation_criteria && (
        <div className="paneltask-accordion-section">
          <div className="paneltask-detail-label">Validation</div>
          <div className="message-content text-xs">
            <Markdown content={task.validation_criteria} id={`task-vc-${task.id}`} />
          </div>
        </div>
      )}

      <div className="paneltask-accordion-dates">
        <span>Created {new Date(task.created_at).toLocaleDateString()}</span>
        {task.closed_at && <span> {'\u00B7'} Closed {new Date(task.closed_at).toLocaleDateString()}</span>}
      </div>
    </div>
  )
}
