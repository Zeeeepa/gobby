import { memo, useState, useEffect, useCallback } from 'react'
import '../tasks/task-execution.css'
import type { GobbyTask } from '../../hooks/useTasks'
import { StatusDot } from '../tasks/TaskBadges'
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

function getBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || ''
}

export const TasksTab = memo(function TasksTab({ projectId }: TasksTabProps) {
  const [tasks, setTasks] = useState<GobbyTask[]>([])
  const [loading, setLoading] = useState(true)
  const [showClosed, setShowClosed] = useState(false)
  const [search, setSearch] = useState('')
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [taskDetail, setTaskDetail] = useState<GobbyTaskDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // Fetch tasks — only non-closed by default
  useEffect(() => {
    setLoading(true)
    const baseUrl = getBaseUrl()
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    if (!showClosed) params.set('status', 'open')
    params.set('limit', '500')
    fetch(`${baseUrl}/api/tasks?${params}`)
      .then((res) => (res.ok ? res.json() : { tasks: [] }))
      .then((data) => setTasks(data.tasks ?? []))
      .catch(() => setTasks([]))
      .finally(() => setLoading(false))
  }, [projectId, showClosed])

  // Fetch task detail when selected
  useEffect(() => {
    if (!selectedTaskId) { setTaskDetail(null); return }
    setDetailLoading(true)
    const baseUrl = getBaseUrl()
    fetch(`${baseUrl}/api/tasks/${selectedTaskId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setTaskDetail(data?.id ? data : (data?.task ?? null)))
      .catch(() => setTaskDetail(null))
      .finally(() => setDetailLoading(false))
  }, [selectedTaskId])

  // Build tree
  const taskMap = new Map<string, GobbyTask & { children: GobbyTask[] }>()
  for (const t of tasks) taskMap.set(t.id, { ...t, children: [] })
  const roots: (GobbyTask & { children: GobbyTask[] })[] = []
  for (const t of taskMap.values()) {
    if (t.parent_task_id && taskMap.has(t.parent_task_id)) {
      taskMap.get(t.parent_task_id)!.children.push(t)
    } else {
      roots.push(t)
    }
  }

  // Search filter
  const q = search.toLowerCase().trim()
  const matchesSearch = (t: GobbyTask): boolean => {
    if (!q) return true
    return t.title.toLowerCase().includes(q) || t.ref.toLowerCase().includes(q)
  }

  const toggleExpanded = useCallback((id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }, [])

  const handleSelect = useCallback((id: string) => {
    setSelectedTaskId((prev) => (prev === id ? null : id))
  }, [])

  const renderTask = (task: GobbyTask & { children?: GobbyTask[] }, depth: number) => {
    if (!matchesSearch(task)) return null
    const hasChildren = task.children && task.children.length > 0
    const isExpanded = expandedIds.has(task.id)
    const isSelected = task.id === selectedTaskId
    const ref = task.seq_num != null ? `#${task.seq_num}` : null
    const isClosed = CLOSED_STATUSES.has(task.status)

    return (
      <div key={task.id}>
        <div
          className={`paneltask${isSelected ? ' paneltask--selected' : ''}${isClosed ? ' paneltask--closed' : ''}`}
          style={{ paddingLeft: `${8 + depth * 14}px` }}
          onClick={() => handleSelect(task.id)}
        >
          {hasChildren ? (
            <button
              className="paneltask-chevron"
              onClick={(e) => { e.stopPropagation(); toggleExpanded(task.id) }}
            >
              {isExpanded ? '\u25BE' : '\u25B8'}
            </button>
          ) : (
            <span className="paneltask-chevron paneltask-chevron--leaf" />
          )}
          <StatusDot status={task.status} />
          {ref && <span className="paneltask-ref">{ref}</span>}
          <span className="paneltask-title">{task.title}</span>
        </div>
        {hasChildren && isExpanded && (task.children as (GobbyTask & { children?: GobbyTask[] })[]).map((c) => renderTask(c, depth + 1))}
      </div>
    )
  }

  if (loading) {
    return <div className="activity-tab-empty"><p>Loading tasks...</p></div>
  }

  const visibleCount = tasks.filter((t) => !CLOSED_STATUSES.has(t.status) || showClosed).length

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
        <span className="paneltask-count">{visibleCount}</span>
      </div>

      {/* Task tree */}
      <div className={`overflow-y-auto ${selectedTaskId ? 'max-h-[55%]' : 'flex-1'}`}>
        {roots.length === 0 ? (
          <div className="activity-tab-empty">
            <p>No {showClosed ? '' : 'open '}tasks</p>
          </div>
        ) : (
          roots.map((t) => renderTask(t, 0))
        )}
      </div>

      {/* Detail pane */}
      {selectedTaskId && (
        <div className="flex-1 flex flex-col min-h-0 border-t border-border">
          <div className="paneltask-detail-header">
            <span className="text-xs text-muted-foreground">Detail</span>
            <button className="paneltask-detail-close" onClick={() => setSelectedTaskId(null)}>{'\u2715'}</button>
          </div>
          <div className="flex-1 overflow-y-auto p-3">
            {detailLoading ? (
              <p className="text-xs text-muted-foreground">Loading...</p>
            ) : taskDetail ? (
              <TaskDetailView task={taskDetail} />
            ) : (
              <p className="text-xs text-muted-foreground">Task not found</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
})

function TaskDetailView({ task }: { task: GobbyTaskDetail }) {
  const priorityLabel = task.priority === 0 ? 'Critical' : task.priority === 1 ? 'High' : task.priority === 2 ? 'Medium' : task.priority === 3 ? 'Low' : 'Backlog'

  return (
    <div className="paneltask-detail">
      <div className="paneltask-detail-badges">
        <span className="paneltask-ref">{task.ref}</span>
        <StatusPill status={task.status} />
        {task.task_type !== 'task' && <TypePill type={task.task_type} />}
      </div>
      <h3 className="paneltask-detail-title">{task.title}</h3>

      <div className="paneltask-detail-meta">
        <span>{priorityLabel} priority</span>
        {task.assignee && <><span className="paneltask-detail-sep">/</span><span>{task.assignee}</span></>}
        {task.category && <><span className="paneltask-detail-sep">/</span><span>{task.category}</span></>}
      </div>

      {task.description && (
        <div className="paneltask-detail-section">
          <div className="paneltask-detail-label">Description</div>
          <div className="message-content text-xs">
            <Markdown content={task.description} id={`task-desc-${task.id}`} />
          </div>
        </div>
      )}

      {task.validation_criteria && (
        <div className="paneltask-detail-section">
          <div className="paneltask-detail-label">Validation</div>
          <div className="message-content text-xs">
            <Markdown content={task.validation_criteria} id={`task-vc-${task.id}`} />
          </div>
        </div>
      )}

      <div className="paneltask-detail-dates">
        <span>Created {new Date(task.created_at).toLocaleDateString()}</span>
        {task.closed_at && <span>Closed {new Date(task.closed_at).toLocaleDateString()}</span>}
      </div>
    </div>
  )
}

function StatusPill({ status }: { status: string }) {
  const colors: Record<string, string> = {
    open: 'var(--status-open, #3b82f6)',
    in_progress: 'var(--status-progress, #f59e0b)',
    closed: 'var(--status-closed, #737373)',
    review_approved: 'var(--status-closed, #22c55e)',
    needs_review: 'var(--status-review, #8b5cf6)',
    escalated: 'var(--status-escalated, #ef4444)',
  }
  const c = colors[status] ?? '#737373'
  return (
    <span className="paneltask-pill" style={{ color: c, borderColor: c }}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}

function TypePill({ type }: { type: string }) {
  return <span className="paneltask-pill paneltask-pill--type">{type}</span>
}
