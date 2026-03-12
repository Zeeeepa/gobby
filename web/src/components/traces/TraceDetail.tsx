import { useState } from 'react'
import { SidebarPanel } from '../shared/SidebarPanel'
import type { SpanRecord } from '../../hooks/useTraces'
import { parseLLMAttributes, formatTokenCount } from './llm-utils'

interface TraceDetailProps {
  isOpen: boolean
  onClose: () => void
  span?: SpanRecord
}

function formatNsToMs(ns: number): string {
  return (ns / 1_000_000).toFixed(2) + 'ms'
}

function LLMSummary({ span }: { span: SpanRecord }) {
  const [showRaw, setShowRaw] = useState(false)
  const [showPrompt, setShowPrompt] = useState(false)
  const [showCompletion, setShowCompletion] = useState(false)

  const llm = parseLLMAttributes(span.attributes_json)
  if (!llm) return null

  const durationNs = span.end_time_ns - span.start_time_ns
  const durationSec = durationNs / 1_000_000_000
  const tokensPerSec = durationSec > 0 ? (llm.completionTokens / durationSec).toFixed(1) : '-'
  const totalTokens = llm.promptTokens + llm.completionTokens
  const promptRatio = totalTokens > 0 ? (llm.promptTokens / totalTokens) * 100 : 0

  let attributes: Record<string, any> = {}
  try {
    if (span.attributes_json) attributes = JSON.parse(span.attributes_json)
  } catch { /* ignore */ }

  if (showRaw) {
    return (
      <div className="trace-detail-section">
        <h3>
          Raw Attributes
          <button className="llm-toggle-raw" onClick={() => setShowRaw(false)}>Show LLM view</button>
        </h3>
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
    )
  }

  return (
    <>
      <div className="trace-detail-section">
        <h3>
          LLM Call
          <button className="llm-toggle-raw" onClick={() => setShowRaw(true)}>Show raw</button>
        </h3>
        <div className="llm-summary">
          <div className="llm-summary-item">
            <span className="llm-summary-label">Provider</span>
            <span className="llm-summary-value">{llm.system}</span>
          </div>
          <div className="llm-summary-item">
            <span className="llm-summary-label">Model</span>
            <span className="llm-summary-value">{llm.model}</span>
          </div>
          <div className="llm-summary-item">
            <span className="llm-summary-label">Latency</span>
            <span className="llm-summary-value">{formatNsToMs(durationNs)}</span>
          </div>
          <div className="llm-summary-item">
            <span className="llm-summary-label">Tokens/sec</span>
            <span className="llm-summary-value">{tokensPerSec}</span>
          </div>
          <div className="llm-summary-item" style={{ gridColumn: '1 / -1' }}>
            <span className="llm-summary-label">
              Tokens: {formatTokenCount(llm.promptTokens)} in / {formatTokenCount(llm.completionTokens)} out / {formatTokenCount(totalTokens)} total
            </span>
            <div className="llm-token-bar">
              <div className="llm-token-bar-fill" style={{ width: `${promptRatio}%` }} />
            </div>
          </div>
        </div>
      </div>

      {llm.prompt && (
        <div className="trace-detail-section">
          <h3>
            Prompt
            <button className="llm-toggle-raw" onClick={() => setShowPrompt(!showPrompt)}>
              {showPrompt ? 'Collapse' : 'Expand'}
            </button>
          </h3>
          {showPrompt && (
            <div className="llm-content-block llm-content-block--prompt">{llm.prompt}</div>
          )}
        </div>
      )}

      {llm.completion && (
        <div className="trace-detail-section">
          <h3>
            Completion
            <button className="llm-toggle-raw" onClick={() => setShowCompletion(!showCompletion)}>
              {showCompletion ? 'Collapse' : 'Expand'}
            </button>
          </h3>
          {showCompletion && (
            <div className="llm-content-block llm-content-block--completion">{llm.completion}</div>
          )}
        </div>
      )}
    </>
  )
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
  const llmAttrs = parseLLMAttributes(span.attributes_json)

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

        {llmAttrs ? (
          <LLMSummary span={span} />
        ) : (
          Object.keys(attributes).length > 0 && (
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
          )
        )}

        {events.length > 0 && (
          <div className="trace-detail-section">
            <h3>Events</h3>
            <div className="trace-detail-events">
              {events.map((event, index) => {
                const eventAttrs = event.attributes || {}
                return (
                  <div key={`${event.name}-${index}`} className="trace-detail-event">
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
