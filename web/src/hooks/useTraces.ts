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
  status: string | null
  status_message: string | null
  attributes: Record<string, any>
  events: any[]
}

export interface TraceFilters {
  session_id?: string
  status?: string
}

export function useTraces(projectId?: string) {
  const [traces, setTraces] = useState<Span[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [filters, setFilters] = useState<TraceFilters>({})
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null)
  const refetchTimerRef = useRef<number | null>(null)

  const fetchTraces = useCallback(async () => {
    const params = new URLSearchParams()
    if (filters.session_id) params.set('session_id', filters.session_id)
    // projectId is currently not supported by the backend /api/traces but kept for future use
    // if (projectId) params.set('project_id', projectId)

    try {
      const res = await fetch(`/api/traces?${params}`)
      if (res.ok) {
        const data = await res.json()
        setTraces(data.traces || [])
      } else {
        console.error('Failed to fetch traces:', res.status, res.statusText)
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
        console.error('Failed to fetch trace detail:', res.status, res.statusText)
        setSpans([])
        setRootSpan(null)
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
    fetchTraceDetail,
  }
}
