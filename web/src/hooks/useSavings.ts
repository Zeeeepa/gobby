import { useState, useEffect, useCallback, useRef } from 'react'
import type { TimeRange } from '../components/dashboard/TimeRangePills'

export interface SavingsData {
  days: number
  total_tokens_saved: number
  total_cost_saved_usd: number
  total_events: number
  categories: Record<string, {
    tokens_saved: number
    cost_saved_usd: number
    event_count: number
  }>
}

const RANGE_TO_DAYS: Record<TimeRange, number> = {
  '24h': 1,
  '7d': 7,
  '30d': 30,
  'all': 36500,
}

export function savingsRangeToDays(range: TimeRange): number {
  return RANGE_TO_DAYS[range]
}

export function useSavings(days: number) {
  const [data, setData] = useState<SavingsData | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const fetchSavings = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const resp = await fetch(`/api/admin/savings?days=${days}`, { signal: controller.signal })
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
    fetchSavings().then(() => setIsLoading(false))
    const interval = setInterval(fetchSavings, 30_000)
    return () => {
      clearInterval(interval)
      abortRef.current?.abort()
    }
  }, [fetchSavings])

  return { data, isLoading, error }
}
