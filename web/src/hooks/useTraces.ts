import { useState, useEffect, useCallback, useRef } from 'react'
import { useWebSocketEvent } from './useWebSocketEvent'

export interface Span {
  span_id: string
  trace_id: string
  parent_span_id: string | null
  name: string
  kind: string | null
  start_time_ns: number
  end_time_ns: number | null
  status: 'UNSET' | 'OK' | 'ERROR' | string
  status_message: string | null
  attributes: Record<string, any>
  events: any[]
}

export interface TraceSummary {
  trace_id: string
  name: string
  status: string
  start_time_ns: number
  end_time_ns: number | null
  duration_ms?: number
}

interface TraceFilters {
  session_id?: string
  status?: string
}

export function useTraces() {
  const [traces, setTraces] = useState<Span[]>([])
  const [total, setTotal] = useState(0)
  const [isLoading, setIsLoading] = useState(true)
  const [filters, setFilters] = useState<TraceFilters>({})
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null)
  const refetchTimerRef = useRef<number | null>(null)

  const fetchTraces = useCallback(async () => {
    const params = new URLSearchParams()
    if (filters.session_id) params.set('session_id', filters.session_id)
    // status filtering is currently manual in the UI if not supported by backend
    
    try {
      const res = await fetch(`/api/traces?${params}`)
      if (res.ok) {
        const data = await res.json()
        setTraces(data.traces || [])
        setTotal(data.total || 0)
      } else {
        console.error('Failed to fetch traces:', res.status)
        setTraces([])
      }
    } catch (e) {
      console.error('Failed to fetch traces:', e)
    } finally {
      setIsLoading(false)
    }
  }, [filters])

  useEffect(() => {
    setIsLoading(true)
    fetchTraces()
  }, [fetchTraces])

  useWebSocketEvent('trace_event', useCallback(() => {
    if (refetchTimerRef.current) window.clearTimeout(refetchTimerRef.current)
    refetchTimerRef.current = window.setTimeout(() => {
      fetchTraces()
    }, 500)
  }, [fetchTraces]))

  useEffect(() => {
    return () => {
      if (refetchTimerRef.current) window.clearTimeout(refetchTimerRef.current)
    }
  }, [])

  return {
    traces,
    total,
    isLoading,
    filters,
    setFilters,
    fetchTraces,
    selectedTraceId,
    setSelectedTraceId,
  }
}

export function useTraceDetail(traceId: string | null) {
  const [spans, setSpans] = useState<Span[]>([])
  const [rootSpan, setRootSpan] = useState<Span | null>(null)
  const [isLoading, setIsLoading] = useState(false)

  const fetchTraceDetail = useCallback(async () => {
    if (!traceId) {
      setSpans([])
      setRootSpan(null)
      return
    }

    setIsLoading(true)
    try {
      const res = await fetch(`/api/traces/${traceId}`)
      if (res.ok) {
        const data = await res.json()
        setSpans(data.spans || [])
        setRootSpan(data.root_span || null)
      } else {
        console.error('Failed to fetch trace detail:', res.status)
      }
    } catch (e) {
      console.error('Failed to fetch trace detail:', e)
    } finally {
      setIsLoading(false)
    }
  }, [traceId])

  useEffect(() => {
    fetchTraceDetail()
  }, [fetchTraceDetail])

  return {
    spans,
    rootSpan,
    isLoading,
    refetch: fetchTraceDetail
  }
}
