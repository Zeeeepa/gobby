import { useState, useEffect, useCallback, useRef } from 'react'

export interface TimeStats {
  days: number
  hours: number | null
  tasks: {
    open: number; in_progress: number; closed: number
    needs_review: number; review_approved: number; escalated: number
    ready: number; blocked: number; closed_24h: number
  }
  sessions: {
    active: number; paused: number; handoff_ready: number; total: number
    by_source: Record<string, Record<string, number>>
  }
  memory: {
    count: number; by_type: Record<string, number>; recent_count: number
  }
}

export function useTimeStats(hours: number, projectId?: string) {
  const [data, setData] = useState<TimeStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const fetchStats = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    try {
      let url = `/api/admin/stats?hours=${hours}`
      if (projectId) url += `&project_id=${encodeURIComponent(projectId)}`
      const resp = await fetch(url, { signal: controller.signal })
      if (resp.ok) {
        setData(await resp.json())
        setError(null)
      } else {
        setError(`HTTP ${resp.status}`)
        setData(null)
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      setError(String(e))
      setData(null)
    }
  }, [hours, projectId])

  useEffect(() => {
    setIsLoading(true)
    fetchStats().then(() => setIsLoading(false))
    const interval = setInterval(fetchStats, 30_000)
    return () => {
      clearInterval(interval)
      abortRef.current?.abort()
    }
  }, [fetchStats])

  return { data, isLoading, error }
}
