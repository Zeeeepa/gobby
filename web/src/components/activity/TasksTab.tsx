import { memo, useState, useEffect } from 'react'

interface TasksTabProps {
  projectId?: string | null
}

interface TaskItem {
  id: string
  seq_num?: number
  title: string
  status: string
  task_type?: string
  priority?: number
  parent_task_id?: string | null
  children?: TaskItem[]
}

const STATUS_DOTS: Record<string, string> = {
  open: 'bg-blue-400',
  in_progress: 'bg-yellow-400',
  closed: 'bg-green-400',
  review_approved: 'bg-green-400',
  needs_review: 'bg-purple-400',
  escalated: 'bg-red-400',
  blocked: 'bg-red-400',
}

const CLOSED_STATUSES = new Set(['closed', 'review_approved'])

export const TasksTab = memo(function TasksTab({ projectId }: TasksTabProps) {
  const [tasks, setTasks] = useState<TaskItem[]>([])
  const [loading, setLoading] = useState(true)
  const [showClosed, setShowClosed] = useState(false)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  useEffect(() => {
    setLoading(true)
    const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    if (!showClosed) params.set('status', 'open')
    params.set('limit', '200')
    fetch(`${baseUrl}/api/tasks?${params}`)
      .then((res) => (res.ok ? res.json() : { tasks: [] }))
      .then((data) => setTasks(data.tasks ?? []))
      .catch(() => setTasks([]))
      .finally(() => setLoading(false))
  }, [projectId, showClosed])

  if (loading) {
    return <div className="activity-tab-empty"><p>Loading tasks...</p></div>
  }

  // Build tree
  const taskMap = new Map<string, TaskItem & { children: TaskItem[] }>()
  for (const t of tasks) {
    taskMap.set(t.id, { ...t, children: [] })
  }
  const roots: TaskItem[] = []
  for (const t of taskMap.values()) {
    if (t.parent_task_id && taskMap.has(t.parent_task_id)) {
      taskMap.get(t.parent_task_id)!.children.push(t)
    } else {
      roots.push(t)
    }
  }

  // Filter closed
  const filterTasks = (items: TaskItem[]): TaskItem[] => {
    return items.filter((t) => {
      if (!showClosed && CLOSED_STATUSES.has(t.status)) return false
      return true
    })
  }

  const toggleExpanded = (id: string) => {
    setExpandedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const renderTask = (task: TaskItem, depth: number) => {
    const children = (task as any).children as TaskItem[] | undefined
    const hasChildren = children && children.length > 0
    const isExpanded = expandedIds.has(task.id)
    const dotColor = STATUS_DOTS[task.status] ?? 'bg-neutral-400'
    const ref = task.seq_num != null ? `#${task.seq_num}` : null

    return (
      <div key={task.id}>
        <div
          className="flex items-center gap-1.5 px-3 py-1.5 hover:bg-muted/50 cursor-default text-sm"
          style={{ paddingLeft: `${12 + depth * 16}px` }}
        >
          {hasChildren ? (
            <button
              className="text-[10px] text-muted-foreground w-4 text-center shrink-0"
              onClick={() => toggleExpanded(task.id)}
            >
              {isExpanded ? '\u25BC' : '\u25B6'}
            </button>
          ) : (
            <span className="w-4 shrink-0" />
          )}
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${dotColor}`} />
          {ref && <span className="text-xs text-accent font-mono shrink-0">{ref}</span>}
          <span className="text-foreground truncate">{task.title}</span>
        </div>
        {hasChildren && isExpanded && filterTasks(children!).map((c) => renderTask(c, depth + 1))}
      </div>
    )
  }

  const visibleRoots = filterTasks(roots)

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={showClosed}
            onChange={(e) => setShowClosed(e.target.checked)}
            className="rounded"
          />
          Show closed
        </label>
        <span className="text-xs text-muted-foreground ml-auto">{visibleRoots.length} tasks</span>
      </div>
      <div className="flex-1 overflow-y-auto">
        {visibleRoots.length === 0 ? (
          <div className="activity-tab-empty">
            <p>No tasks</p>
          </div>
        ) : (
          visibleRoots.map((t) => renderTask(t, 0))
        )}
      </div>
    </div>
  )
})
