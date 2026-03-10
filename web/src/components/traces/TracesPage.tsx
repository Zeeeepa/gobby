import { useState, useMemo } from 'react'
import { useTraces, useTraceDetail } from '../../hooks/useTraces'
import { TraceWaterfall } from './TraceWaterfall'
import { TraceDetail } from './TraceDetail'
import './TracesPage.css'

interface TracesPageProps {
  initialTraceId?: string | null
}

export function TracesPage({ initialTraceId }: TracesPageProps) {
  const { 
    traces, 
    isLoading, 
    filters, 
    setFilters, 
    selectedTraceId, 
    setSelectedTraceId 
  } = useTraces()

  const { spans } = useTraceDetail(selectedTraceId)
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null)

  // Handle initialTraceId from navigation
  useMemo(() => {
    if (initialTraceId && initialTraceId !== selectedTraceId) {
      setSelectedTraceId(initialTraceId)
    }
  }, [initialTraceId, setSelectedTraceId])

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
            style={{ 
              padding: '6px 10px',
              border: '1px solid var(--border)',
              borderRadius: '4px',
              background: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: '13px'
            }}
          />
          <select
            className="traces-filter-input"
            value={filters.status || ''}
            onChange={(e) => setFilters({ ...filters, status: e.target.value })}
            style={{ 
              padding: '6px 10px',
              border: '1px solid var(--border)',
              borderRadius: '4px',
              background: 'var(--bg-primary)',
              color: 'var(--text-primary)',
              fontSize: '13px'
            }}
          >
            <option value="">All Statuses</option>
            <option value="OK">OK</option>
            <option value="ERROR">ERROR</option>
            <option value="UNSET">UNSET</option>
          </select>
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
                  <span>{formatDuration((trace.end_time_ns || trace.start_time_ns) - trace.start_time_ns)}</span>
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
            <h3>Select a trace to view details</h3>
            <p>Choose a trace from the list on the left to see the waterfall visualization and span attributes.</p>
          </div>
        )}
      </div>
    </div>
  )
}
