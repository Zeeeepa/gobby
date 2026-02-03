import { useState } from 'react'
import type { ToolCall } from './Message'

interface ToolCallDisplayProps {
  toolCalls: ToolCall[]
}

function formatToolName(fullName: string): string {
  // Convert mcp__gobby-tasks__create_task to create_task
  const parts = fullName.split('__')
  return parts[parts.length - 1] || fullName
}

function ToolCallItem({ call }: { call: ToolCall }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const displayName = formatToolName(call.tool_name)

  const statusIcon = {
    calling: '\u23f3', // hourglass
    completed: '\u2713', // check mark
    error: '\u2717', // x mark
  }[call.status]

  const hasDetails = call.arguments || call.result || call.error

  return (
    <div className={`tool-call tool-call-${call.status}`}>
      <div
        className="tool-call-header"
        onClick={() => hasDetails && setIsExpanded(!isExpanded)}
        style={{ cursor: hasDetails ? 'pointer' : 'default' }}
      >
        <span className="tool-call-icon">{statusIcon}</span>
        <span className="tool-call-name">{displayName}</span>
        <span className="tool-call-server">{call.server_name}</span>
        {hasDetails && (
          <span className="tool-call-expand">{isExpanded ? '\u25bc' : '\u25b6'}</span>
        )}
      </div>

      {isExpanded && hasDetails && (
        <div className="tool-call-details">
          {call.arguments && Object.keys(call.arguments).length > 0 && (
            <div className="tool-call-section">
              <div className="tool-call-section-label">Arguments</div>
              <pre className="tool-call-json">
                {JSON.stringify(call.arguments, null, 2)}
              </pre>
            </div>
          )}

          {call.status === 'completed' && call.result !== undefined && (
            <div className="tool-call-section">
              <div className="tool-call-section-label">Result</div>
              <pre className="tool-call-json">
                {typeof call.result === 'string'
                  ? call.result
                  : JSON.stringify(call.result, null, 2)}
              </pre>
            </div>
          )}

          {call.status === 'error' && call.error && (
            <div className="tool-call-section tool-call-error">
              <div className="tool-call-section-label">Error</div>
              <pre className="tool-call-json">{call.error}</pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

export function ToolCallDisplay({ toolCalls }: ToolCallDisplayProps) {
  if (!toolCalls.length) return null

  return (
    <div className="tool-calls">
      {toolCalls.map((call) => (
        <ToolCallItem key={call.id} call={call} />
      ))}
    </div>
  )
}
