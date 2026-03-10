import type { Span } from '../../hooks/useTraces'

interface TraceDetailProps {
  span: Span | null
  onClose: () => void
}

export function TraceDetail({ span, onClose }: TraceDetailProps) {
  if (!span) {
    return (
      <div className="trace-detail">
        <div className="trace-detail-header">
          <div className="trace-detail-title">Span Details</div>
          <button className="trace-detail-close" onClick={onClose}>&times;</button>
        </div>
        <div className="trace-detail-content">
          <p>Select a span to view details.</p>
        </div>
      </div>
    )
  }

  const formatDuration = (ns: number) => {
    const ms = ns / 1_000_000
    if (ms < 1) return `${(ns / 1000).toFixed(2)}µs`
    if (ms < 1000) return `${ms.toFixed(2)}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  const formatTime = (ns: number) => {
    return new Date(ns / 1_000_000).toLocaleTimeString()
  }

  return (
    <div className="trace-detail">
      <div className="trace-detail-header">
        <div>
          <div className="trace-detail-title">{span.name}</div>
          <div style={{ fontSize: '11px', color: 'var(--text-secondary)', fontFamily: 'var(--font-mono)' }}>
            Span ID: {span.span_id}
          </div>
        </div>
        <button className="trace-detail-close" onClick={onClose}>&times;</button>
      </div>

      <div className="trace-detail-content">
        <section className="trace-detail-attributes">
          <div className="trace-detail-section-title">Overview</div>
          <table className="trace-detail-table">
            <tbody>
              <tr>
                <th>Status</th>
                <td>
                  <span className={`trace-badge trace-badge--${(span.status || 'UNSET').toLowerCase()}`}>
                    {span.status}
                  </span>
                  {span.status_message && <div style={{ marginTop: '4px', fontSize: '11px' }}>{span.status_message}</div>}
                </td>
              </tr>
              <tr>
                <th>Kind</th>
                <td>{span.kind}</td>
              </tr>
              <tr>
                <th>Duration</th>
                <td>{formatDuration((span.end_time_ns || span.start_time_ns) - span.start_time_ns)}</td>
              </tr>
              <tr>
                <th>Start Time</th>
                <td>{formatTime(span.start_time_ns)}</td>
              </tr>
            </tbody>
          </table>
        </section>

        <section className="trace-detail-attributes">
          <div className="trace-detail-section-title">Attributes</div>
          <table className="trace-detail-table">
            <tbody>
              {Object.entries(span.attributes).map(([key, value]) => (
                <tr key={key}>
                  <th>{key}</th>
                  <td>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>

        {span.events && span.events.length > 0 && (
          <section className="trace-detail-events">
            <div className="trace-detail-section-title">Events</div>
            {span.events.map((event, i) => (
              <div key={i} className="trace-detail-event">
                <div className="trace-detail-event-header">
                  <span className="trace-detail-event-name">{event.name}</span>
                  <span className="trace-detail-event-time">{formatTime(event.timestamp_ns)}</span>
                </div>
                {event.attributes && Object.keys(event.attributes).length > 0 && (
                  <table className="trace-detail-table">
                    <tbody>
                      {Object.entries(event.attributes).map(([key, value]) => (
                        <tr key={key}>
                          <th style={{ fontSize: '11px', width: '100px' }}>{key}</th>
                          <td style={{ fontSize: '11px' }}>{String(value)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            ))}
          </section>
        )}
      </div>
    </div>
  )
}
