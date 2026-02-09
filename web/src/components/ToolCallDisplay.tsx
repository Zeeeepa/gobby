import { useState } from 'react'
import type { ToolCall } from './Message'

interface ToolCallDisplayProps {
  toolCalls: ToolCall[]
  onRespond?: (toolCallId: string, answers: Record<string, string>) => void
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

function AskUserQuestionDisplay({ call, onRespond }: { call: ToolCall; onRespond?: (toolCallId: string, answers: Record<string, string>) => void }) {
  const args = call.arguments as { questions?: AskUserQuestionItem[] } | undefined
  const questions = args?.questions
  const [selectedOptions, setSelectedOptions] = useState<Record<number, string[]>>({})
  const [otherTexts, setOtherTexts] = useState<Record<number, string>>({})
  const [submitted, setSubmitted] = useState(false)

  if (!questions || !Array.isArray(questions)) {
    return null
  }

  const isWaiting = call.status === 'calling'

  const handleOptionClick = (qi: number, label: string, multiSelect: boolean) => {
    if (submitted) return
    setSelectedOptions((prev) => {
      const current = prev[qi] || []
      if (label === '__other__') {
        // Toggle "Other"
        if (current.includes('__other__')) {
          return { ...prev, [qi]: current.filter((l) => l !== '__other__') }
        }
        if (multiSelect) {
          return { ...prev, [qi]: [...current, '__other__'] }
        }
        return { ...prev, [qi]: ['__other__'] }
      }
      if (multiSelect) {
        // Toggle in multi-select
        if (current.includes(label)) {
          return { ...prev, [qi]: current.filter((l) => l !== label) }
        }
        return { ...prev, [qi]: [...current.filter((l) => l !== '__other__'), label] }
      }
      // Single-select: replace
      return { ...prev, [qi]: [label] }
    })
  }

  const handleOtherTextChange = (qi: number, text: string) => {
    setOtherTexts((prev) => ({ ...prev, [qi]: text }))
  }

  const handleSubmit = () => {
    if (!onRespond || submitted) return
    const answers: Record<string, string> = {}
    questions.forEach((q, qi) => {
      const selected = selectedOptions[qi] || []
      if (selected.includes('__other__')) {
        answers[q.question] = otherTexts[qi] || ''
      } else if (selected.length > 0) {
        answers[q.question] = selected.join(', ')
      }
    })
    onRespond(call.id, answers)
    setSubmitted(true)
  }

  const hasAnySelection = Object.values(selectedOptions).some((s) => s.length > 0)

  return (
    <div className={`ask-user-question${isWaiting ? ' ask-user-waiting' : ''}${submitted ? ' ask-user-submitted' : ''}`}>
      {questions.map((q, qi) => (
        <div key={qi} className="ask-user-block">
          <div className="ask-user-header-row">
            <span className="ask-user-chip">{q.header}</span>
            {q.multiSelect && <span className="ask-user-multi-hint">Select multiple</span>}
          </div>
          <div className="ask-user-question-text">{q.question}</div>
          <div className="ask-user-options">
            {q.options.map((opt, oi) => {
              const isSelected = (selectedOptions[qi] || []).includes(opt.label)
              return (
                <div
                  key={oi}
                  className={`ask-user-option${isSelected ? ' ask-user-option-selected' : ''}`}
                  onClick={() => handleOptionClick(qi, opt.label, q.multiSelect)}
                >
                  <div className="ask-user-option-label">{opt.label}</div>
                  {opt.description && (
                    <div className="ask-user-option-desc">{opt.description}</div>
                  )}
                </div>
              )
            })}
            <div
              className={`ask-user-option ask-user-option-other${(selectedOptions[qi] || []).includes('__other__') ? ' ask-user-option-selected' : ''}`}
              onClick={() => handleOptionClick(qi, '__other__', q.multiSelect)}
            >
              <div className="ask-user-option-label">Other</div>
              <div className="ask-user-option-desc">Provide custom text input</div>
            </div>
            {(selectedOptions[qi] || []).includes('__other__') && (
              <input
                className="ask-user-other-input"
                type="text"
                placeholder="Type your answer..."
                value={otherTexts[qi] || ''}
                onChange={(e) => handleOtherTextChange(qi, e.target.value)}
                onClick={(e) => e.stopPropagation()}
                disabled={submitted}
              />
            )}
          </div>
        </div>
      ))}
      {isWaiting && !submitted && hasAnySelection && (
        <div className="ask-user-block">
          <button className="ask-user-submit-btn" onClick={handleSubmit}>
            Submit
          </button>
        </div>
      )}
      {isWaiting && !submitted && !hasAnySelection && (
        <div className="ask-user-block">
          <div className="ask-user-pending">Select an option to respond...</div>
        </div>
      )}
    </div>
  )
}

function formatToolName(fullName: string): string {
  // Convert mcp__gobby-tasks__create_task to create_task
  const parts = fullName.split('__')
  return parts[parts.length - 1] || fullName
}

function ToolCallItem({ call, onRespond }: { call: ToolCall; onRespond?: (toolCallId: string, answers: Record<string, string>) => void }) {
  const [isExpanded, setIsExpanded] = useState(false)
  const displayName = formatToolName(call.tool_name)

  // Render AskUserQuestion with dedicated UI
  if (isAskUserQuestion(call)) {
    return <AskUserQuestionDisplay call={call} onRespond={onRespond} />
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

export function ToolCallDisplay({ toolCalls, onRespond }: ToolCallDisplayProps) {
  if (!toolCalls.length) return null

  return (
    <div className="tool-calls">
      {toolCalls.map((call) => (
        <ToolCallItem key={call.id} call={call} onRespond={onRespond} />
      ))}
    </div>
  )
}
