import { useState, useMemo, useEffect } from 'react'
import { useTraces, useTraceDetail } from '../../hooks/useTraces'
import { TraceWaterfall } from './TraceWaterfall'
import { TraceDetail } from './TraceDetail'
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
            <select
              className="traces-filter-input"
              value={filters.status || ''}
              onChange={(e) => setFilters({ ...filters, status: e.target.value })}
              style={{ flex: 1 }}
            >
              <option value="">All Statuses</option>
              <option value="OK">OK</option>
              <option value="ERROR">ERROR</option>
              <option value="UNSET">UNSET</option>
            </select>
            <select
              className="traces-filter-input"
              value={filters.time_range || ''}
              onChange={(e) => setFilters({ ...filters, time_range: e.target.value })}
              style={{ flex: 1 }}
            >
              <option value="">All Time</option>
              <option value="1h">Last 1h</option>
              <option value="24h">Last 24h</option>
              <option value="7d">Last 7d</option>
            </select>
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
