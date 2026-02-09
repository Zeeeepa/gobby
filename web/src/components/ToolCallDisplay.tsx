import { useState } from 'react'
import type { ToolCall } from './Message'

interface ToolCallDisplayProps {
  toolCalls: ToolCall[]
}

interface AskUserOption {
  label: string
  description: string
}

interface AskUserQuestionItem {
  question: string
  header: string
  options: AskUserOption[]
  multiSelect: boolean
}

function isAskUserQuestion(call: ToolCall): boolean {
  return call.tool_name === 'AskUserQuestion'
}

function AskUserQuestionDisplay({ call }: { call: ToolCall }) {
  const args = call.arguments as { questions?: AskUserQuestionItem[] } | undefined
  const questions = args?.questions

  if (!questions || !Array.isArray(questions)) {
    return null
  }

  const isWaiting = call.status === 'calling'

  return (
    <div className={`ask-user-question${isWaiting ? ' ask-user-waiting' : ''}`}>
      {questions.map((q, qi) => (
        <div key={qi} className="ask-user-block">
          <div className="ask-user-header-row">
            <span className="ask-user-chip">{q.header}</span>
            {q.multiSelect && <span className="ask-user-multi-hint">Select multiple</span>}
          </div>
          <div className="ask-user-question-text">{q.question}</div>
          <div className="ask-user-options">
            {q.options.map((opt, oi) => (
              <div key={oi} className="ask-user-option">
                <div className="ask-user-option-label">{opt.label}</div>
                {opt.description && (
                  <div className="ask-user-option-desc">{opt.description}</div>
                )}
              </div>
            ))}
            <div className="ask-user-option ask-user-option-other">
              <div className="ask-user-option-label">Other</div>
              <div className="ask-user-option-desc">Provide custom text input</div>
            </div>
          </div>
          {isWaiting && (
            <div className="ask-user-pending">Waiting for your response...</div>
          )}
        </div>
      ))}
    </div>
  )
}

function formatToolName(fullName: string): string {
  // Convert mcp__gobby-tasks__create_task to create_task
  const parts = fullName.split('__')
  return parts[parts.length - 1] || fullName
}

function ToolCallItem({ call }: { call: ToolCall }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const displayName = formatToolName(call.tool_name)

  // Render AskUserQuestion with dedicated UI
  if (isAskUserQuestion(call)) {
    return <AskUserQuestionDisplay call={call} />
  }

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
