import { useState, useEffect, useCallback, useRef } from 'react'

export interface RunningAgent {
  run_id: string
  session_id: string
  parent_session_id: string
  mode: string
  started_at: string
  pid: number | null
  provider: string
  workflow_name: string | null
  worktree_id: string | null
  terminal_type: string | null
  has_task: boolean
}

export interface AgentRun {
  id: string
  parent_session_id: string
  child_session_id: string | null
  workflow_name: string | null
  provider: string
  model: string | null
  status: string
  prompt: string
  result: string | null
  error: string | null
  tool_calls_count: number
  turns_used: number
  started_at: string | null
  completed_at: string | null
  created_at: string
  updated_at: string
}

const POLL_INTERVAL_MS = 5000

export function useAgentRuns() {
  const [running, setRunning] = useState<RunningAgent[]>([])
  const [recentRuns, setRecentRuns] = useState<AgentRun[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const pollRef = useRef<number | null>(null)

  const fetchRunning = useCallback(async () => {
    try {
      const res = await fetch('/api/agents/running')
      if (res.ok) {
        const data = await res.json()
        setRunning(data.agents || [])
      }
    } catch (e) {
      console.error('Failed to fetch running agents:', e)
    }
  }, [])

  const fetchRecentRuns = useCallback(async () => {
    try {
      const res = await fetch('/api/agents/runs?limit=30')
      if (res.ok) {
        const data = await res.json()
        setRecentRuns(data.runs || [])
      }
    } catch (e) {
      console.error('Failed to fetch agent runs:', e)
    }
  }, [])

  const fetchAll = useCallback(async () => {
    await Promise.all([fetchRunning(), fetchRecentRuns()])
    setIsLoading(false)
  }, [fetchRunning, fetchRecentRuns])

  const cancelAgent = useCallback(async (runId: string): Promise<boolean> => {
    try {
      const res = await fetch(`/api/agents/runs/${encodeURIComponent(runId)}/cancel`, {
        method: 'POST',
      })
      if (res.ok) {
        fetchAll()
        return true
      }
    } catch (e) {
      console.error('Failed to cancel agent:', e)
    }
    return false
  }, [fetchAll])

  useEffect(() => {
    fetchAll()
  }, [fetchAll])

  useEffect(() => {
    pollRef.current = window.setInterval(fetchAll, POLL_INTERVAL_MS)
    return () => {
      if (pollRef.current) window.clearInterval(pollRef.current)
    }
  }, [fetchAll])

  return {
    running,
    recentRuns,
    isLoading,
    cancelAgent,
    refresh: fetchAll,
  }
}
