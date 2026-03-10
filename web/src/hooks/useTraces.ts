import { useState, useEffect, useCallback, useRef } from 'react'
import { useWebSocketEvent } from './useWebSocketEvent'

export interface Span {
  span_id: string
  trace_id: string
  parent_span_id?: string
  name: string
  kind?: string
  start_time_ns: number
  end_time_ns?: number
  status?: 'OK' | 'ERROR' | 'UNSET'
  status_message?: string
  attributes: Record<string, any>
  events: any[]
}

export interface TraceSummary extends Span {
  // A trace summary is represented by its root span
}

interface TraceFilters {
  status?: string
  session_id?: string
}

export function useTraces(projectId?: string) {
  const [traces, setTraces] = useState<TraceSummary[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [filters, setFilters] = useState<TraceFilters>({})
  const [selectedTraceId, setSelectedTraceId] = useState<string | null>(null)
  const refetchTimerRef = useRef<number | null>(null)

  const fetchTraces = useCallback(async () => {
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    if (filters.status) params.set('status', filters.status)
    if (filters.session_id) params.set('session_id', filters.session_id)

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
  }, [projectId, filters])

  useEffect(() => {
    setIsLoading(true)
    fetchTraces()
  }, [fetchTraces])

  useWebSocketEvent('trace_event', useCallback(() => {
    if (refetchTimerRef.current) clearTimeout(refetchTimerRef.current)
    refetchTimerRef.current = window.setTimeout(() => {
      fetchTraces()
    }, 500)
  }, [fetchTraces]))

  useEffect(() => {
    return () => {
      if (refetchTimerRef.current) clearTimeout(refetchTimerRef.current)
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
  const [isLoading, setIsLoading] = useState(false)

  const fetchTraceDetail = useCallback(async (id: string) => {
    setIsLoading(true)
    try {
      const res = await fetch(`/api/traces/${id}`)
      if (res.ok) {
        const data = await res.json()
        setSpans(data.spans || [])
      } else {
        console.error('Failed to fetch trace detail:', res.status, res.statusText)
        setSpans([])
      }
    } catch (e) {
      console.error('Failed to fetch trace detail:', e)
    } finally {
      setIsLoading(false)
    }
  }, [])

  useEffect(() => {
    if (traceId) {
      fetchTraceDetail(traceId)
    } else {
      setSpans([])
    }
  }, [traceId, fetchTraceDetail])

  return {
    spans,
    isLoading,
    refetch: () => traceId && fetchTraceDetail(traceId),
  }
}
