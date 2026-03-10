import type { Span } from '../../hooks/useTraces'
import { formatDuration } from '../../utils/formatTime'

interface TraceDetailProps {
  span: Span | null
}

export function TraceDetail({ span }: TraceDetailProps) {
  if (!span) {
    return null
  }

  const durationNs = (span.end_time_ns || span.start_time_ns) - span.start_time_ns
  const durationMs = durationNs / 1_000_000

  return (
    <div className="trace-detail-body">
      <div className="trace-detail-section">
        <span className="trace-detail-section-title">Overview</span>
        <table className="trace-detail-attributes">
          <tbody>
            <tr>
              <th>Span ID</th>
              <td>{span.span_id}</td>
            </tr>
            <tr>
              <th>Kind</th>
              <td>{span.kind || 'Internal'}</td>
            </tr>
            <tr>
              <th>Duration</th>
              <td>{formatDuration(durationMs)}</td>
            </tr>
            <tr>
              <th>Start Time</th>
              <td>{new Date(span.start_time_ns / 1_000_000).toLocaleString()}</td>
            </tr>
          </tbody>
        </table>
      </div>

      {Object.keys(span.attributes).length > 0 && (
        <div className="trace-detail-section">
          <span className="trace-detail-section-title">Attributes</span>
          <table className="trace-detail-attributes">
            <tbody>
              {Object.entries(span.attributes).map(([key, value]) => (
                <tr key={key}>
                  <th>{key}</th>
                  <td>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {span.events && span.events.length > 0 && (
        <div className="trace-detail-section">
          <span className="trace-detail-section-title">Events</span>
          <div className="trace-detail-events-list">
            {span.events.map((event, i) => (
              <div key={i} className="trace-detail-event-item">
                <div className="trace-detail-event-header">
                  <span className="trace-detail-event-name">{event.name}</span>
                  <span className="trace-detail-event-time">
                    +{formatDuration((event.timestamp_ns - span.start_time_ns) / 1_000_000)}
                  </span>
                </div>
                {event.attributes && Object.keys(event.attributes).length > 0 && (
                  <pre className="trace-detail-event-attributes">
                    {JSON.stringify(event.attributes, null, 2)}
                  </pre>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {span.status === 'ERROR' && span.status_message && (
        <div className="trace-detail-section">
          <span className="trace-detail-section-title">Error Message</span>
          <div className="trace-detail-error">
            {span.status_message}
          </div>
        </div>
      )}
    </div>
  )
}

