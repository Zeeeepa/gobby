import type { Span } from '../../hooks/useTraces'

interface TraceDetailProps {
  span: Span | null
}

export function TraceDetail({ span }: TraceDetailProps) {
  if (!span) {
    return (
      <div className="trace-no-selection">
        Select a span to view details
      </div>
    )
  }

  const formatDuration = (ns: number) => {
    if (ns < 1000) return `${ns}ns`
    if (ns < 1000000) return `${(ns / 1000).toFixed(2)}µs`
    if (ns < 1000000000) return `${(ns / 1000000).toFixed(2)}ms`
    return `${(ns / 1000000000).toFixed(2)}s`
  }

  const startTime = new Date(span.start_time_ns / 1000000).toLocaleString()
  const duration = (span.end_time_ns || span.start_time_ns) - span.start_time_ns
  const statusClass = !span.status || span.status === 'UNSET' ? 'unset' : span.status.toLowerCase() === 'error' ? 'error' : 'ok'

  return (
    <div className="trace-detail-panel">
      <div className="trace-detail-header">
        <div className="trace-detail-title">{span.name}</div>
        <div className="trace-item-meta">
          <span className={`badge badge-${statusClass}`}>{span.status || 'UNSET'}</span>
          <span>{formatDuration(duration)}</span>
        </div>
      </div>

      <div className="trace-detail-section">
        <div className="trace-detail-section-title">Overview</div>
        <table className="trace-attributes-table">
          <tbody>
            <tr>
              <th className="trace-attribute-key">Span ID</th>
              <td className="trace-attribute-value">{span.span_id}</td>
            </tr>
            <tr>
              <th className="trace-attribute-key">Trace ID</th>
              <td className="trace-attribute-value">{span.trace_id}</td>
            </tr>
            <tr>
              <th className="trace-attribute-key">Kind</th>
              <td className="trace-attribute-value">{span.kind}</td>
            </tr>
            <tr>
              <th className="trace-attribute-key">Start Time</th>
              <td className="trace-attribute-value">{startTime}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div className="trace-detail-section">
        <div className="trace-detail-section-title">Attributes</div>
        {Object.keys(span.attributes).length > 0 ? (
          <table className="trace-attributes-table">
            <tbody>
              {Object.entries(span.attributes).map(([key, value]) => (
                <tr key={key}>
                  <th className="trace-attribute-key">{key}</th>
                  <td className="trace-attribute-value">
                    {typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="trace-no-selection" style={{ padding: 0, justifyContent: 'flex-start' }}>No attributes</div>
        )}
      </div>

      {span.events && span.events.length > 0 && (
        <div className="trace-detail-section">
          <div className="trace-detail-section-title">Events</div>
          {span.events.map((event, i) => (
            <div key={i} className="trace-event-item">
              <div className="trace-event-header">
                <span>{event.name}</span>
                <span className="trace-event-time">
                  {formatDuration(event.timestamp - span.start_time_ns)}
                </span>
              </div>
              {event.attributes && Object.keys(event.attributes).length > 0 && (
                <pre style={{ fontSize: '0.7rem', margin: '4px 0', opacity: 0.8 }}>
                  {JSON.stringify(event.attributes, null, 2)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}

      {span.status === 'ERROR' && span.status_message && (
        <div className="trace-detail-section" style={{ borderLeft: '4px solid #ef4444' }}>
          <div className="trace-detail-section-title" style={{ color: '#ef4444' }}>Error Message</div>
          <div style={{ fontSize: '0.8rem', fontFamily: 'var(--font-mono)', wordBreak: 'break-all' }}>
            {span.status_message}
          </div>
        </div>
      )}
    </div>
  )
}
