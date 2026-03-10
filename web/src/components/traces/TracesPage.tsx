import { useState, useMemo, useEffect } from 'react'
import './TracesPage.css'
import { useTraces, useTraceDetail } from '../../hooks/useTraces'
import { TraceWaterfall } from './TraceWaterfall'
import { TraceDetail } from './TraceDetail'
import { SidebarPanel } from '../shared/SidebarPanel'
import { formatDuration, formatRelativeTime } from '../../utils/formatTime'

interface TracesPageProps {
  projectId?: string
  initialTraceId?: string | null
}

export function TracesPage({ projectId, initialTraceId }: TracesPageProps) {
  const {
    traces,
    isLoading: isTracesLoading,
    filters,
    setFilters,
    selectedTraceId,
    setSelectedTraceId,
  } = useTraces(projectId)

  // Auto-select initial trace on mount if provided
  useEffect(() => {
    if (initialTraceId) {
      setSelectedTraceId(initialTraceId)
    }
  }, [initialTraceId, setSelectedTraceId])

  const { spans, isLoading: isTraceLoading } = useTraceDetail(selectedTraceId)
  const [selectedSpanId, setSelectedSpanId] = useState<string | null>(null)
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const selectedSpan = useMemo(() => {
    return spans.find(s => s.span_id === selectedSpanId) || null
  }, [spans, selectedSpanId])

  return (
    <div className="traces-page">
      {/* Left panel: Trace browser */}
      <div className={`traces-browser ${sidebarOpen ? '' : 'collapsed'}`}>
        <div className="traces-sidebar-header">
          {sidebarOpen && <span className="traces-sidebar-title">Traces</span>}
          <button
            className="traces-sidebar-toggle"
            onClick={() => setSidebarOpen(!sidebarOpen)}
            title={sidebarOpen ? 'Collapse' : 'Expand'}
          >
            {sidebarOpen ? '\u25C0' : '\u25B6'}
          </button>
        </div>

        {sidebarOpen && (
          <>
            <div className="traces-filter-bar">
              <input
                className="traces-filter-input"
                type="text"
                placeholder="Filter by session ID..."
                value={filters.session_id || ''}
                onChange={(e) => setFilters({ ...filters, session_id: e.target.value || undefined })}
              />
              <div className="traces-filter-row">
                <select
                  className="traces-filter-select"
                  value={filters.status || ''}
                  onChange={(e) => setFilters({ ...filters, status: e.target.value || undefined })}
                >
                  <option value="">All Statuses</option>
                  <option value="OK">OK</option>
                  <option value="ERROR">ERROR</option>
                  <option value="UNSET">UNSET</option>
                </select>
              </div>
            </div>

            <div className="traces-list">
              {traces.length === 0 && !isTracesLoading && (
                <div className="trace-empty">No traces found</div>
              )}
              {isTracesLoading && traces.length === 0 && (
                <div className="trace-empty">Loading traces...</div>
              )}
              {traces.map((trace) => {
                const isSelected = trace.trace_id === selectedTraceId
                const durationNs = (trace.end_time_ns || trace.start_time_ns) - trace.start_time_ns
                const durationMs = durationNs / 1_000_000

                return (
                  <div
                    key={trace.trace_id}
                    className={`trace-item ${isSelected ? 'selected' : ''}`}
                    onClick={() => {
                      setSelectedTraceId(trace.trace_id)
                      setSelectedSpanId(null)
                    }}
                  >
                    <div className="trace-item-header">
                      <span className="trace-item-name">{trace.name}</span>
                      <span className={`trace-status-badge trace-status-badge--${(trace.status || 'unset').toLowerCase()}`}>
                        {trace.status || 'UNSET'}
                      </span>
                    </div>
                    <div className="trace-item-id">
                      {trace.trace_id.slice(0, 8)}...
                    </div>
                    <div className="trace-item-meta">
                      <span>{formatDuration(durationMs)}</span>
                      <span>{formatRelativeTime(new Date(trace.start_time_ns / 1_000_000).toISOString())}</span>
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>

      {/* Main content: Waterfall and Detail */}
      <div className="traces-main">
        {selectedTraceId ? (
          <div className="trace-content">
            {isTraceLoading ? (
              <div className="trace-empty">Loading trace waterfall...</div>
            ) : (
              <TraceWaterfall
                spans={spans}
                selectedSpanId={selectedSpanId}
                onSelectSpan={setSelectedSpanId}
              />
            )}
          </div>
        ) : (
          <div className="trace-empty">
            <h3>Select a trace</h3>
            <p>Choose a trace from the list to view the waterfall visualization and span details.</p>
          </div>
        )}
      </div>

      {/* Span detail sidebar */}
      <SidebarPanel
        isOpen={!!selectedSpanId}
        onClose={() => setSelectedSpanId(null)}
        title={selectedSpan?.name || 'Span Detail'}
        width={440}
        headerContent={
          selectedSpan && (
            <div style={{ marginTop: '8px' }}>
              <span className={`trace-status-badge trace-status-badge--${(selectedSpan.status || 'unset').toLowerCase()}`}>
                {selectedSpan.status || 'UNSET'}
              </span>
            </div>
          )
        }
      >
        <TraceDetail span={selectedSpan} />
      </SidebarPanel>
    </div>
  )
}

