import { memo, useState, useEffect, useCallback } from 'react'
import { TaskTree } from '../tasks/TaskTree'
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
  created_at: string
  updated_at: string
}

function getBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || ''
}

export const TasksTab = memo(function TasksTab({ projectId }: TasksTabProps) {
  const [tasks, setTasks] = useState<GobbyTask[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [taskDetail, setTaskDetail] = useState<GobbyTaskDetail | null>(null)
  const [detailLoading, setDetailLoading] = useState(false)

  // Fetch all tasks
  useEffect(() => {
    setLoading(true)
    const baseUrl = getBaseUrl()
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    params.set('limit', '500')
    fetch(`${baseUrl}/api/tasks?${params}`)
      .then((res) => (res.ok ? res.json() : { tasks: [] }))
      .then((data) => setTasks(data.tasks ?? []))
      .catch(() => setTasks([]))
      .finally(() => setLoading(false))
  }, [projectId])

  // Fetch task detail when selected
  useEffect(() => {
    if (!selectedTaskId) {
      setTaskDetail(null)
      return
    }
    setDetailLoading(true)
    const baseUrl = getBaseUrl()
    fetch(`${baseUrl}/api/tasks/${selectedTaskId}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setTaskDetail(data?.task ?? null))
      .catch(() => setTaskDetail(null))
      .finally(() => setDetailLoading(false))
  }, [selectedTaskId])

  const handleSelectTask = useCallback((id: string) => {
    setSelectedTaskId((prev) => (prev === id ? null : id))
  }, [])

  if (loading) {
    return <div className="activity-tab-empty"><p>Loading tasks...</p></div>
  }

  if (tasks.length === 0) {
    return (
      <div className="activity-tab-empty">
        <p>No tasks</p>
        <p className="text-xs text-muted-foreground mt-1">Tasks will appear here when created</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* TaskTree fills available space, shrinks when detail is open */}
      <div className={`overflow-hidden ${selectedTaskId ? 'h-[55%]' : 'flex-1'}`}>
        <TaskTree
          tasks={tasks}
          onSelectTask={handleSelectTask}
        />
      </div>

      {/* Detail pane */}
      {selectedTaskId && (
        <div className="flex-1 flex flex-col min-h-0 border-t border-border">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-muted/30">
            <span className="text-xs text-muted-foreground">Task Detail</span>
            <button
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => setSelectedTaskId(null)}
            >
              Close
            </button>
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
  return (
    <div className="space-y-3 text-sm">
      {/* Title + badges */}
      <div>
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-accent text-xs">{task.ref}</span>
          <StatusPill status={task.status} />
          {task.task_type && task.task_type !== 'task' && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{task.task_type}</span>
          )}
          {task.category && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-muted text-muted-foreground">{task.category}</span>
          )}
        </div>
        <h3 className="text-foreground font-medium mt-1">{task.title}</h3>
      </div>

      {/* Priority */}
      <div className="flex items-center gap-4 text-xs text-muted-foreground">
        <span>Priority: {task.priority === 1 ? 'High' : task.priority === 2 ? 'Medium' : 'Low'}</span>
        {task.assignee && <span>Assignee: {task.assignee}</span>}
      </div>

      {/* Description */}
      {task.description && (
        <div>
          <div className="text-xs text-muted-foreground mb-1">Description</div>
          <div className="text-foreground text-xs message-content">
            <Markdown content={task.description} id={`task-desc-${task.id}`} />
          </div>
        </div>
      )}

      {/* Validation criteria */}
      {task.validation_criteria && (
        <div>
          <div className="text-xs text-muted-foreground mb-1">Validation Criteria</div>
          <div className="text-foreground text-xs message-content">
            <Markdown content={task.validation_criteria} id={`task-vc-${task.id}`} />
          </div>
        </div>
      )}

      {/* Dates */}
      <div className="text-[10px] text-muted-foreground space-y-0.5">
        <div>Created: {new Date(task.created_at).toLocaleString()}</div>
        <div>Updated: {new Date(task.updated_at).toLocaleString()}</div>
        {task.closed_at && <div>Closed: {new Date(task.closed_at).toLocaleString()}</div>}
      </div>
    </div>
  )
}

const STATUS_COLORS: Record<string, string> = {
  open: 'bg-blue-500/20 text-blue-400',
  in_progress: 'bg-yellow-500/20 text-yellow-400',
  closed: 'bg-green-500/20 text-green-400',
  review_approved: 'bg-green-500/20 text-green-400',
  needs_review: 'bg-purple-500/20 text-purple-400',
  escalated: 'bg-red-500/20 text-red-400',
  blocked: 'bg-red-500/20 text-red-400',
}

function StatusPill({ status }: { status: string }) {
  const color = STATUS_COLORS[status] ?? 'bg-neutral-500/20 text-neutral-400'
  return (
    <span className={`text-[10px] px-1.5 py-0.5 rounded ${color}`}>
      {status.replace(/_/g, ' ')}
    </span>
  )
}
