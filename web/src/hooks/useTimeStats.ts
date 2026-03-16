import { useState, useEffect, useCallback, useRef } from 'react'
import type { TimeRange } from '../components/dashboard/TimeRangePills'

export interface TimeStats {
  days: number
  tasks: {
    open: number; in_progress: number; closed: number
    needs_review: number; review_approved: number; escalated: number
    ready: number; blocked: number; closed_24h: number
  }
  sessions: {
    active: number; paused: number; handoff_ready: number; total: number
  }
  memory: {
    count: number; by_type: Record<string, number>; recent_count: number
  }
}

const RANGE_TO_DAYS: Record<TimeRange, number> = {
  '24h': 1,
  '7d': 7,
  '30d': 30,
  'all': 0,
}

export function rangeToDays(range: TimeRange): number {
  return RANGE_TO_DAYS[range]
}

export function useTimeStats(days: number) {
  const [data, setData] = useState<TimeStats | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const fetchStats = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const resp = await fetch(`/api/admin/stats?days=${days}`, { signal: controller.signal })
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
  }, [days])

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
