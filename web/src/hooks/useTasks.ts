import { useState, useEffect, useCallback, useRef } from 'react'

// =============================================================================
// Types
// =============================================================================

export interface GobbyTask {
  id: string
  ref: string
  title: string
  status: string
  priority: number
  type: string
  parent_task_id: string | null
  created_at: string
  updated_at: string
  seq_num: number | null
  path_cache: string | null
  requires_user_review: boolean
}

export interface GobbyTaskDetail extends GobbyTask {
  description: string | null
  assignee: string | null
  labels: string[] | null
  category: string | null
  validation_status: string | null
  validation_feedback: string | null
  validation_criteria: string | null
  validation_fail_count: number
  closed_at: string | null
  closed_reason: string | null
  closed_commit_sha: string | null
  commits: string[] | null
  escalated_at: string | null
  escalation_reason: string | null
  project_id: string
  created_in_session_id: string | null
  closed_in_session_id: string | null
  complexity_score: number | null
  is_expanded: boolean
  expansion_status: string
}

export interface TaskFilters {
  status: string | null
  priority: number | null
  taskType: string | null
  assignee: string | null
  label: string | null
  parentTaskId: string | null
  search: string
}

export interface TaskStats {
  [status: string]: number
}

export interface TaskListResponse {
  tasks: GobbyTask[]
  total: number
  stats: TaskStats
  limit: number
  offset: number
}

interface CreateTaskParams {
  title: string
  description?: string
  priority?: number
  task_type?: string
  parent_task_id?: string
  labels?: string[]
  category?: string
  validation_criteria?: string
  assignee?: string
}

interface UpdateTaskParams {
  title?: string
  description?: string
  status?: string
  priority?: number
  task_type?: string
  assignee?: string
  labels?: string[]
  parent_task_id?: string
  category?: string
  validation_criteria?: string
}

// =============================================================================
// Helpers
// =============================================================================

const POLL_INTERVAL_MS = 5000

function getBaseUrl(): string {
  const isSecure = window.location.protocol === 'https:'
  return isSecure ? '' : `http://${window.location.hostname}:60887`
}

// =============================================================================
// Hook
// =============================================================================

export function useTasks() {
  const [tasks, setTasks] = useState<GobbyTask[]>([])
  const [total, setTotal] = useState(0)
  const [stats, setStats] = useState<TaskStats>({})
  const [filters, setFilters] = useState<TaskFilters>({
    status: null,
    priority: null,
    taskType: null,
    assignee: null,
    label: null,
    parentTaskId: null,
    search: '',
  })
  const [isLoading, setIsLoading] = useState(true)
  const pollRef = useRef<number | null>(null)

  // Fetch tasks list
  const fetchTasks = useCallback(async () => {
    try {
      const baseUrl = getBaseUrl()
      const params = new URLSearchParams({ limit: '200' })
      if (filters.status) params.set('status', filters.status)
      if (filters.priority !== null) params.set('priority', String(filters.priority))
      if (filters.taskType) params.set('task_type', filters.taskType)
      if (filters.assignee) params.set('assignee', filters.assignee)
      if (filters.label) params.set('label', filters.label)
      if (filters.parentTaskId) params.set('parent_task_id', filters.parentTaskId)
      if (filters.search) params.set('search', filters.search)

      const response = await fetch(`${baseUrl}/tasks?${params}`)
      if (response.ok) {
        const data: TaskListResponse = await response.json()
        setTasks(data.tasks || [])
        setTotal(data.total)
        setStats(data.stats || {})
      }
    } catch (e) {
      console.error('Failed to fetch tasks:', e)
    } finally {
      setIsLoading(false)
    }
  }, [filters])

  // Get single task detail
  const getTask = useCallback(async (taskId: string): Promise<GobbyTaskDetail | null> => {
    try {
      const baseUrl = getBaseUrl()
      const response = await fetch(`${baseUrl}/tasks/${encodeURIComponent(taskId)}`)
      if (response.ok) {
        return await response.json()
      }
    } catch (e) {
      console.error('Failed to get task:', e)
    }
    return null
  }, [])

  // Create task
  const createTask = useCallback(
    async (params: CreateTaskParams): Promise<GobbyTaskDetail | null> => {
      try {
        const baseUrl = getBaseUrl()
        const response = await fetch(`${baseUrl}/tasks`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params),
        })
        if (response.ok) {
          const task = await response.json()
          fetchTasks()
          return task
        }
      } catch (e) {
        console.error('Failed to create task:', e)
      }
      return null
    },
    [fetchTasks]
  )

  // Update task
  const updateTask = useCallback(
    async (taskId: string, params: UpdateTaskParams): Promise<GobbyTaskDetail | null> => {
      try {
        const baseUrl = getBaseUrl()
        const response = await fetch(`${baseUrl}/tasks/${encodeURIComponent(taskId)}`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params),
        })
        if (response.ok) {
          const task = await response.json()
          fetchTasks()
          return task
        }
      } catch (e) {
        console.error('Failed to update task:', e)
      }
      return null
    },
    [fetchTasks]
  )

  // Close task
  const closeTask = useCallback(
    async (taskId: string, reason?: string): Promise<GobbyTaskDetail | null> => {
      try {
        const baseUrl = getBaseUrl()
        const response = await fetch(
          `${baseUrl}/tasks/${encodeURIComponent(taskId)}/close`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason }),
          }
        )
        if (response.ok) {
          const task = await response.json()
          fetchTasks()
          return task
        }
      } catch (e) {
        console.error('Failed to close task:', e)
      }
      return null
    },
    [fetchTasks]
  )

  // Reopen task
  const reopenTask = useCallback(
    async (taskId: string, reason?: string): Promise<GobbyTaskDetail | null> => {
      try {
        const baseUrl = getBaseUrl()
        const response = await fetch(
          `${baseUrl}/tasks/${encodeURIComponent(taskId)}/reopen`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ reason }),
          }
        )
        if (response.ok) {
          const task = await response.json()
          fetchTasks()
          return task
        }
      } catch (e) {
        console.error('Failed to reopen task:', e)
      }
      return null
    },
    [fetchTasks]
  )

  // Delete task
  const deleteTask = useCallback(
    async (taskId: string, cascade = false): Promise<boolean> => {
      try {
        const baseUrl = getBaseUrl()
        const params = cascade ? '?cascade=true' : ''
        const response = await fetch(
          `${baseUrl}/tasks/${encodeURIComponent(taskId)}${params}`,
          { method: 'DELETE' }
        )
        if (response.ok) {
          fetchTasks()
          return true
        }
      } catch (e) {
        console.error('Failed to delete task:', e)
      }
      return false
    },
    [fetchTasks]
  )

  // Fetch on mount and when filters change
  useEffect(() => {
    setIsLoading(true)
    fetchTasks()
  }, [fetchTasks])

  // Polling
  useEffect(() => {
    pollRef.current = window.setInterval(fetchTasks, POLL_INTERVAL_MS)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [fetchTasks])

  const refreshTasks = useCallback(() => {
    setIsLoading(true)
    fetchTasks()
  }, [fetchTasks])

  return {
    tasks,
    total,
    stats,
    isLoading,
    filters,
    setFilters,
    getTask,
    createTask,
    updateTask,
    closeTask,
    reopenTask,
    deleteTask,
    refreshTasks,
  }
}
