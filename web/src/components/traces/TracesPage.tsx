import { useState, useMemo } from 'react'
import './TracesPage.css'
import { useTraces, useTraceDetail } from '../../hooks/useTraces'
import { TraceWaterfall } from './TraceWaterfall'
import { TraceDetail } from './TraceDetail'

interface TracesPageProps {
  projectId?: string
  initialTraceId?: string
}

export function TracesPage({ projectId, initialTraceId }: TracesPageProps) {
  const { 
    traces, 
    isLoading: tracesLoading, 
    filters, 
    setFilters, 
    selectedTraceId, 
    setSelectedTraceId 
  } = useTraces(projectId)

  // Use initialTraceId if provided and no selection yet
  useMemo(() => {
    if (initialTraceId && !selectedTraceId) {
      setSelectedTraceId(initialTraceId)
    }
  }, [initialTraceId, selectedTraceId, setSelectedTraceId])

  const { spans, isLoading: detailLoading } = useTraceDetail(selectedTraceId)
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null)

  const selectedSpan = useMemo(() => {
    return spans.find(s => s.span_id === selectedSpanId) || (spans.length > 0 ? spans[0] : null)
  }, [spans, selectedSpanId])

  const formatDuration = (ns: number) => {
    if (ns < 1000) return `${ns}ns`
    if (ns < 1000000) return `${(ns / 1000).toFixed(2)}µs`
    if (ns < 1000000000) return `${(ns / 1000000).toFixed(2)}ms`
    return `${(ns / 1000000000).toFixed(2)}s`
  }

  const filteredTraces = useMemo(() => {
    if (!filters.session_id) return traces
    return traces.filter(t => t.attributes?.session_id === filters.session_id)
  }, [traces, filters.session_id])

  return (
    <div className="traces-page">
      <div className="traces-toolbar">
        <div style={{ fontWeight: 600 }}>Traces</div>
        <input
          type="text"
          placeholder="Filter by Session ID..."
          className="traces-filter-input"
          value={filters.session_id || ''}
          onChange={(e) => setFilters({ ...filters, session_id: e.target.value })}
        />
        {tracesLoading && <div className="trace-id">Loading...</div>}
      </div>

      <div className="traces-content">
        {/* Left: Trace List */}
        <div className="traces-list-container">
          {filteredTraces.length === 0 && !tracesLoading ? (
            <div className="trace-no-selection" style={{ padding: '2rem' }}>No traces found</div>
          ) : (
            filteredTraces.map((trace) => {
              const duration = (trace.end_time_ns || trace.start_time_ns) - trace.start_time_ns
              const isSelected = trace.trace_id === selectedTraceId
              const statusClass = !trace.status || trace.status === 'UNSET' ? 'unset' : trace.status.toLowerCase() === 'error' ? 'error' : 'ok'
              
              return (
                <div
                  key={trace.trace_id}
                  className={`trace-item ${isSelected ? 'selected' : ''}`}
                  onClick={() => setSelectedTraceId(trace.trace_id)}
                >
                  <div className="trace-item-header">
                    <span className="trace-name">{trace.name}</span>
                    <span className={`badge badge-${statusClass}`} style={{ fontSize: '0.6rem' }}>
                      {trace.status || 'UNSET'}
                    </span>
                  </div>
                  <div className="trace-id">{trace.trace_id.substring(0, 16)}...</div>
                  <div className="trace-item-meta">
                    <span>{formatDuration(duration)}</span>
                    <span>{new Date(trace.start_time_ns / 1000000).toLocaleTimeString()}</span>
                  </div>
                </div>
              )
            })
          )}
        </div>

        {/* Right: Waterfall + Detail */}
        <div className="trace-main-view">
          {selectedTraceId ? (
            <>
              {detailLoading ? (
                <div className="trace-no-selection">Loading trace details...</div>
              ) : spans.length > 0 ? (
                <TraceWaterfall
                  spans={spans}
                  selectedSpanId={selectedSpanId || (spans[0]?.span_id)}
                  onSelectSpan={setSelectedSpanId}
                />
              ) : (
                <div className="trace-no-selection">No spans found for this trace</div>
              )}
            </>
          ) : (
            <div className="trace-no-selection">Select a trace to view waterfall</div>
          )}
        </div>

        {/* Far Right: Attribute Inspector */}
        <TraceDetail span={selectedSpan} />
      </div>
    </div>
  )
}
