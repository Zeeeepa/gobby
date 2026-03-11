import { useState, useEffect, useCallback, useRef } from 'react'

export interface MetricSnapshot {
  timestamp: string
  metrics: {
    counters: Record<string, { value: number }>
    gauges: Record<string, { value: number }>
    histograms: Record<string, { count: number; sum: number; avg: number }>
    uptime_seconds: number
  }
}

interface SnapshotsResponse {
  snapshots: MetricSnapshot[]
  count: number
  hours: number
}

export function useMetricSnapshots(hours: number = 1) {
  const [data, setData] = useState<MetricSnapshot[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const abortRef = useRef<AbortController | null>(null)

  const fetchSnapshots = useCallback(async () => {
    abortRef.current?.abort()
    const controller = new AbortController()
    abortRef.current = controller
    try {
      const response = await fetch(
        `/api/metrics/snapshots?hours=${hours}&limit=${hours * 60}`,
        { signal: controller.signal }
      )
      if (response.ok) {
        const json: SnapshotsResponse = await response.json()
        setData(json.snapshots)
        setError(null)
      } else {
        setError(`HTTP ${response.status}`)
      }
    } catch (e) {
      if (e instanceof DOMException && e.name === 'AbortError') return
      setError(String(e))
    }
  }, [hours])

  useEffect(() => {
    setIsLoading(true)
    fetchSnapshots().then(() => setIsLoading(false))
    const interval = setInterval(fetchSnapshots, 30_000)
    return () => {
      clearInterval(interval)
      abortRef.current?.abort()
    }
  }, [fetchSnapshots])

  return { data, isLoading, error }
}
