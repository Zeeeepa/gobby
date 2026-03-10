import { useState, useMemo, useEffect } from 'react'
import { useTraces, useTraceDetail } from '../../hooks/useTraces'
import { TraceWaterfall } from './TraceWaterfall'
import { TraceDetail } from './TraceDetail'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '../chat/ui/Select'
import './TracesPage.css'

interface TracesPageProps {
  projectId?: string
  initialTraceId?: string | null
}

export function TracesPage({ projectId, initialTraceId }: TracesPageProps) {
  const { 
    traces, 
    isLoading, 
    filters, 
    setFilters, 
    selectedTraceId, 
    setSelectedTraceId 
  } = useTraces(projectId)

  const { spans } = useTraceDetail(selectedTraceId)
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null)

  // Handle initialTraceId from navigation
  useEffect(() => {
    if (initialTraceId && initialTraceId !== selectedTraceId) {
      setSelectedTraceId(initialTraceId)
      setSelectedSpanId(null)
    }
  }, [initialTraceId, selectedTraceId, setSelectedTraceId])

  const selectedSpan = useMemo(() => {
    return spans.find(s => s.span_id === selectedSpanId) || null
  }, [spans, selectedSpanId])

  const filteredTraces = useMemo(() => {
    if (!filters.status) return traces
    return traces.filter(t => t.status === filters.status)
  }, [traces, filters.status])

  const formatDuration = (ns: number) => {
    const ms = ns / 1_000_000
    if (ms < 1) return `${(ns / 1000).toFixed(2)}µs`
    if (ms < 1000) return `${ms.toFixed(2)}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  const formatTime = (ns: number) => {
    return new Date(ns / 1_000_000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  }

  return (
    <div className="traces-page">
      <div className="traces-browser">
        <div className="traces-toolbar">
          <input
            className="traces-filter-input"
            type="text"
            placeholder="Filter by session ID..."
            value={filters.session_id || ''}
            onChange={(e) => setFilters({ ...filters, session_id: e.target.value })}
          />
          <div className="traces-filter-row" style={{ display: 'flex', gap: '8px' }}>
            <div style={{ flex: 1 }}>
              <Select
                value={filters.status || ''}
                onValueChange={(val) => setFilters({ ...filters, status: val === 'all' ? '' : val })}
              >
                <SelectTrigger className="traces-filter-input" style={{ width: '100%', height: '30px' }}>
                  <SelectValue placeholder="All Statuses" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Statuses</SelectItem>
                  <SelectItem value="OK">OK</SelectItem>
                  <SelectItem value="ERROR">ERROR</SelectItem>
                  <SelectItem value="UNSET">UNSET</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div style={{ flex: 1 }}>
              <Select
                value={filters.time_range || ''}
                onValueChange={(val) => setFilters({ ...filters, time_range: val === 'all' ? '' : val })}
              >
                <SelectTrigger className="traces-filter-input" style={{ width: '100%', height: '30px' }}>
                  <SelectValue placeholder="All Time" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All Time</SelectItem>
                  <SelectItem value="1h">Last 1h</SelectItem>
                  <SelectItem value="24h">Last 24h</SelectItem>
                  <SelectItem value="7d">Last 7d</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
        </div>

        <div className="traces-list">
          {isLoading && traces.length === 0 ? (
            <div className="trace-empty">Loading...</div>
          ) : filteredTraces.length === 0 ? (
            <div className="trace-empty">No traces found</div>
          ) : (
            filteredTraces.map((trace) => (
              <div
                key={trace.trace_id}
                className={`trace-item ${selectedTraceId === trace.trace_id ? 'active' : ''}`}
                onClick={() => {
                  setSelectedTraceId(trace.trace_id)
                  setSelectedSpanId(null)
                }}
              >
                <div className="trace-item-header">
                  <span className="trace-item-name">{trace.name}</span>
                  <span className={`trace-badge trace-badge--${(trace.status || 'UNSET').toLowerCase()}`}>
                    {trace.status}
                  </span>
                </div>
                <div className="trace-item-meta">
                  <span className="trace-item-id">{trace.trace_id.slice(0, 8)}...</span>
                  <div style={{ display: 'flex', gap: '8px' }}>
                    <span>{formatTime(trace.start_time_ns)}</span>
                    <span>{formatDuration((trace.end_time_ns || trace.start_time_ns) - trace.start_time_ns)}</span>
                  </div>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

        <div className="traces-content">
          {selectedTraceId ? (
            <>
              <TraceWaterfall
                spans={spans}
                selectedSpanId={selectedSpanId}
                onSelectSpan={setSelectedSpanId}
              />
              {selectedSpan && (
                <TraceDetail
                  span={selectedSpan}
                  onClose={() => setSelectedSpanId(null)}
                />
              )}
            </>
          ) : (
            <div className="trace-empty">
              <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginBottom: '16px', opacity: 0.5 }}>
                <path d="M22 12h-4l-3 9L9 3l-3 9H2" />
              </svg>
              <h3>Select a trace to view details</h3>
              <p>Choose a trace from the list on the left to see the waterfall visualization and span attributes.</p>
            </div>
          )}
        </div>
      </div>
  )
}
