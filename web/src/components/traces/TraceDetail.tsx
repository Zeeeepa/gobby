import { SidebarPanel } from '../shared/SidebarPanel'
import type { SpanRecord } from '../../hooks/useTraces'

interface TraceDetailProps {
  isOpen: boolean
  onClose: () => void
  span?: SpanRecord
}

function formatNsToMs(ns: number): string {
  return (ns / 1_000_000).toFixed(2) + 'ms'
}

export function TraceDetail({ isOpen, onClose, span }: TraceDetailProps) {
  if (!span) {
    return (
      <SidebarPanel isOpen={isOpen} onClose={onClose} title="Span Detail">
        <div className="trace-detail-content">No span selected</div>
      </SidebarPanel>
    )
  }

  const durationMs = formatNsToMs(span.end_time_ns - span.start_time_ns)

  let attributes: Record<string, any> = {}
  try {
    if (span.attributes_json) {
      attributes = JSON.parse(span.attributes_json)
    }
  } catch (e) {
    console.error('Failed to parse span attributes', e)
  }

  let events: any[] = []
  try {
    if (span.events_json) {
      events = JSON.parse(span.events_json)
    }
  } catch (e) {
    console.error('Failed to parse span events', e)
  }

  return (
    <SidebarPanel isOpen={isOpen} onClose={onClose} title={`Span: ${span.name}`}>
      <div className="trace-detail-content">
        <div className="trace-detail-section">
          <h3>Overview</h3>
          <table className="trace-detail-table">
            <tbody>
              <tr><th>Name</th><td>{span.name}</td></tr>
              <tr><th>Status</th><td>{span.status}</td></tr>
              <tr><th>Kind</th><td>{span.kind}</td></tr>
              <tr><th>Duration</th><td>{durationMs}</td></tr>
              <tr><th>Span ID</th><td>{span.span_id}</td></tr>
              <tr><th>Trace ID</th><td>{span.trace_id}</td></tr>
            </tbody>
          </table>
        </div>

        {Object.keys(attributes).length > 0 && (
          <div className="trace-detail-section">
            <h3>Attributes</h3>
            <table className="trace-detail-table">
              <tbody>
                {Object.entries(attributes).map(([key, value]) => (
                  <tr key={key}>
                    <th>{key}</th>
                    <td>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {events.length > 0 && (
          <div className="trace-detail-section">
            <h3>Events</h3>
            <div className="trace-detail-events">
              {events.map((event, index) => {
                const eventAttrs = event.attributes || {}
                return (
                  <div key={index} className="trace-detail-event">
                    <div className="trace-detail-event-header">
                      <span className="trace-detail-event-name">{event.name}</span>
                      {event.timestamp && (
                        <span className="trace-detail-event-time">
                          {new Date(event.timestamp / 1_000_000).toISOString()}
                        </span>
                      )}
                    </div>
                    {Object.keys(eventAttrs).length > 0 && (
                      <table className="trace-detail-table">
                        <tbody>
                          {Object.entries(eventAttrs).map(([key, value]) => (
                            <tr key={key}>
                              <th>{key}</th>
                              <td>{typeof value === 'object' ? JSON.stringify(value) : String(value)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    )}
                  </div>
                )
              })}
            </div>
          </div>
        )}
      </div>
    </SidebarPanel>
  )
}
