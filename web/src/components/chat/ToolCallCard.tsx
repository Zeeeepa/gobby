import { useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { ToolCall } from '../../types/chat'
import { cn } from '../../lib/utils'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'

interface ToolCallCardProps {
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

function formatToolName(fullName: string): string {
  const parts = fullName.split('__')
  return parts[parts.length - 1] || fullName
}

const EXT_TO_LANGUAGE: Record<string, string> = {
  py: 'python', tsx: 'tsx', ts: 'typescript', jsx: 'jsx', js: 'javascript',
  json: 'json', yaml: 'yaml', yml: 'yaml', md: 'markdown', css: 'css',
  html: 'html', sh: 'bash', bash: 'bash', zsh: 'bash', sql: 'sql',
  rs: 'rust', go: 'go', rb: 'ruby', java: 'java', c: 'c', cpp: 'cpp',
  h: 'c', hpp: 'cpp', toml: 'toml', xml: 'xml', svg: 'xml',
}

function parseReadOutput(result: string): { content: string; startLine: number } | null {
  const lines = result.split('\n')
  const parsed: string[] = []
  let startLine = 1
  let firstLine = true

  for (const line of lines) {
    const match = line.match(/^\s*(\d+)\u2192(.*)$/)
    if (!match) {
      if (line.trim() === '') { parsed.push(''); continue }
      return null
    }
    if (firstLine) {
      startLine = parseInt(match[1], 10)
      firstLine = false
    }
    parsed.push(match[2])
  }

  if (parsed.length === 0) return null
  return { content: parsed.join('\n').replace(/\n$/, ''), startLine }
}

function getLanguageFromPath(filePath: string): string {
  const ext = filePath.split('.').pop()?.toLowerCase() || ''
  return EXT_TO_LANGUAGE[ext] || 'text'
}

const highlighterTheme = {
  ...oneDark,
  'pre[class*="language-"]': {
    ...oneDark['pre[class*="language-"]'],
    background: '#0d0d0d',
    margin: '0',
    padding: '0.75rem',
    fontSize: '0.75rem',
  },
  'code[class*="language-"]': {
    ...oneDark['code[class*="language-"]'],
    background: 'transparent',
    fontFamily: "'SF Mono', 'Fira Code', 'JetBrains Mono', monospace",
  },
}

function ToolArgumentsContent({ args }: { args: Record<string, unknown> }) {
  const filePath = args.file_path as string | undefined

  // Write pattern: file_path + content
  if (filePath && typeof args.content === 'string') {
    const language = getLanguageFromPath(filePath)
    return (
      <div>
        <div className="text-muted-foreground mb-1 font-medium">
          Write <span className="font-mono text-foreground">{filePath}</span>
        </div>
        <SyntaxHighlighter
          style={highlighterTheme}
          language={language}
          PreTag="div"
          customStyle={{ margin: 0, borderRadius: '0.25rem', maxHeight: '24rem', overflow: 'auto' }}
        >
          {args.content as string}
        </SyntaxHighlighter>
      </div>
    )
  }

  // Edit pattern: file_path + old_string + new_string
  if (filePath && typeof args.old_string === 'string' && typeof args.new_string === 'string') {
    const language = getLanguageFromPath(filePath)
    return (
      <div>
        <div className="text-muted-foreground mb-1 font-medium">
          Edit <span className="font-mono text-foreground">{filePath}</span>
        </div>
        <div className="text-muted-foreground mb-0.5 text-[0.65rem] uppercase tracking-wide">Old</div>
        <SyntaxHighlighter
          style={highlighterTheme}
          language={language}
          PreTag="div"
          customStyle={{ margin: 0, borderRadius: '0.25rem', maxHeight: '12rem', overflow: 'auto', marginBottom: '0.5rem' }}
        >
          {args.old_string as string}
        </SyntaxHighlighter>
        <div className="text-muted-foreground mb-0.5 text-[0.65rem] uppercase tracking-wide">New</div>
        <SyntaxHighlighter
          style={highlighterTheme}
          language={language}
          PreTag="div"
          customStyle={{ margin: 0, borderRadius: '0.25rem', maxHeight: '12rem', overflow: 'auto' }}
        >
          {args.new_string as string}
        </SyntaxHighlighter>
      </div>
    )
  }

  // Fallback: raw JSON
  return (
    <div>
      <div className="text-muted-foreground mb-1 font-medium">Arguments</div>
      <pre className="bg-muted rounded p-2 overflow-x-auto text-foreground">
        {JSON.stringify(args, null, 2)}
      </pre>
    </div>
  )
}

function ToolResultContent({ call }: { call: ToolCall }) {
  let resultStr: string
  try {
    resultStr = typeof call.result === 'string' ? call.result : JSON.stringify(call.result, null, 2)
  } catch (e) {
    console.error('Failed to serialize tool call result:', e)
    resultStr = String(call.result)
  }
  const filePath = call.arguments?.file_path as string | undefined

  if (filePath) {
    const parsed = parseReadOutput(resultStr)
    if (parsed) {
      const language = getLanguageFromPath(filePath)
      return (
        <SyntaxHighlighter
          style={highlighterTheme}
          language={language}
          PreTag="div"
          showLineNumbers
          startingLineNumber={parsed.startLine}
          lineNumberStyle={{
            minWidth: '2.5em',
            paddingRight: '1em',
            textAlign: 'right',
            userSelect: 'none',
            color: '#555',
          }}
          customStyle={{
            margin: 0,
            borderRadius: '0.25rem',
            maxHeight: '24rem',
            overflow: 'auto',
          }}
        >
          {parsed.content}
        </SyntaxHighlighter>
      )
    }
  }

  return (
    <pre className="bg-muted rounded p-2 overflow-x-auto text-foreground max-h-96 overflow-y-auto font-mono text-xs">
      {resultStr}
    </pre>
  )
}

function ToolCallItem({ call, onRespond }: { call: ToolCall; onRespond?: (toolCallId: string, answers: Record<string, string>) => void }) {
  const [expanded, setExpanded] = useState(false)
  const displayName = formatToolName(call.tool_name)

  if (call.tool_name === 'AskUserQuestion') {
    return <AskUserQuestionCard call={call} onRespond={onRespond} />
  }

  if (call.status === 'pending_approval') {
    return <ToolApprovalCard call={call} onRespond={onRespond} />
  }

  const hasDetails = call.arguments || call.result || call.error

  return (
    <div className={cn(
      'rounded-lg border border-border overflow-hidden my-1.5',
      call.status === 'error' && 'border-destructive-foreground/30'
    )}>
      <div
        className="flex items-center gap-2 px-3 py-1.5 text-sm cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={() => hasDetails && setExpanded(!expanded)}
      >
        <StatusIcon status={call.status} />
        <span className="font-mono text-foreground">{displayName}</span>
        <span className="text-muted-foreground text-xs">{call.server_name}</span>
        <div className="flex-1" />
        {hasDetails && (
          <span className="text-muted-foreground text-xs">{expanded ? '\u25BC' : '\u25B6'}</span>
        )}
      </div>
      {expanded && hasDetails && (
        <div className="border-t border-border px-3 py-2 text-xs space-y-2">
          {call.arguments && Object.keys(call.arguments).length > 0 && (
            <ToolArgumentsContent args={call.arguments} />
          )}
          {call.status === 'completed' && call.result !== undefined && (
            <div>
              <div className="text-muted-foreground mb-1 font-medium">Result</div>
              <ToolResultContent call={call} />
            </div>
          )}
          {call.status === 'error' && call.error && (
            <div>
              <div className="text-destructive-foreground mb-1 font-medium">Error</div>
              <pre className="bg-destructive/30 rounded p-2 overflow-x-auto text-destructive-foreground">
                {call.error}
              </pre>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

function ToolApprovalCard({ call, onRespond }: { call: ToolCall; onRespond?: (toolCallId: string, answers: Record<string, string>) => void }) {
  const displayName = formatToolName(call.tool_name)

  const handleDecision = (decision: 'approve' | 'reject' | 'approve_always') => {
    onRespond?.(call.id, { decision })
  }

  return (
    <div className="rounded-lg border border-warning-foreground/30 bg-warning/20 overflow-hidden my-1.5">
      <div className="flex items-center gap-2 px-3 py-2 text-sm">
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-warning-foreground shrink-0">
          <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <span className="font-mono text-foreground">{displayName}</span>
        <Badge variant="warning">Approval Required</Badge>
      </div>
      {call.arguments && Object.keys(call.arguments).length > 0 && (
        <div className="px-3 pb-2 text-xs">
          <ToolArgumentsContent args={call.arguments} />
        </div>
      )}
      <div className="flex items-center gap-2 px-3 pb-2">
        <Button size="sm" variant="primary" onClick={() => handleDecision('approve')}>
          Approve
        </Button>
        <Button size="sm" variant="ghost" onClick={() => handleDecision('approve_always')}>
          Always Approve
        </Button>
        <Button size="sm" variant="destructive" onClick={() => handleDecision('reject')}>
          Reject
        </Button>
      </div>
    </div>
  )
}

function AskUserQuestionCard({ call, onRespond }: { call: ToolCall; onRespond?: (toolCallId: string, answers: Record<string, string>) => void }) {
  const args = call.arguments as { questions?: AskUserQuestionItem[] } | undefined
  const questions = args?.questions
  const [selectedOptions, setSelectedOptions] = useState<Record<number, string[]>>({})
  const [otherTexts, setOtherTexts] = useState<Record<number, string>>({})
  const [submitted, setSubmitted] = useState(false)

  if (!questions || !Array.isArray(questions)) return null

  const isWaiting = call.status === 'calling'

  const handleOptionClick = (qi: number, label: string, multiSelect: boolean) => {
    if (submitted) return
    setSelectedOptions((prev) => {
      const current = prev[qi] || []
      if (label === '__other__') {
        if (current.includes('__other__')) return { ...prev, [qi]: current.filter((l) => l !== '__other__') }
        return multiSelect ? { ...prev, [qi]: [...current, '__other__'] } : { ...prev, [qi]: ['__other__'] }
      }
      if (multiSelect) {
        return current.includes(label)
          ? { ...prev, [qi]: current.filter((l) => l !== label) }
          : { ...prev, [qi]: [...current.filter((l) => l !== '__other__'), label] }
      }
      return { ...prev, [qi]: [label] }
    })
  }

  const handleSubmit = () => {
    if (!onRespond || submitted) return
    const answers: Record<string, string> = {}
    questions.forEach((q, qi) => {
      const selected = selectedOptions[qi] || []
      if (selected.includes('__other__')) answers[q.question] = otherTexts[qi] || ''
      else if (selected.length > 0) answers[q.question] = selected.join(', ')
    })
    onRespond(call.id, answers)
    setSubmitted(true)
  }

  const hasSelection = Object.values(selectedOptions).some((s) => s.length > 0)

  return (
    <div className={cn('rounded-lg border border-accent/30 bg-accent/5 overflow-hidden my-1.5 p-3', submitted && 'opacity-60')}>
      {questions.map((q, qi) => (
        <div key={qi} className="mb-3 last:mb-0">
          <div className="flex items-center gap-2 mb-1.5">
            <Badge variant="info">{q.header}</Badge>
            {q.multiSelect && <span className="text-xs text-muted-foreground">Select multiple</span>}
          </div>
          <div className="text-sm text-foreground mb-2">{q.question}</div>
          <div className="flex flex-wrap gap-1.5">
            {q.options.map((opt, oi) => {
              const isSelected = (selectedOptions[qi] || []).includes(opt.label)
              return (
                <button
                  key={oi}
                  className={cn(
                    'rounded-md border px-3 py-1.5 text-sm transition-colors text-left',
                    isSelected ? 'border-accent bg-accent/20 text-foreground' : 'border-border hover:bg-muted text-muted-foreground'
                  )}
                  onClick={() => handleOptionClick(qi, opt.label, q.multiSelect)}
                  disabled={submitted}
                >
                  <div className="font-medium">{opt.label}</div>
                  {opt.description && <div className="text-xs opacity-75">{opt.description}</div>}
                </button>
              )
            })}
            <button
              className={cn(
                'rounded-md border px-3 py-1.5 text-sm transition-colors',
                (selectedOptions[qi] || []).includes('__other__') ? 'border-accent bg-accent/20 text-foreground' : 'border-border hover:bg-muted text-muted-foreground'
              )}
              onClick={() => handleOptionClick(qi, '__other__', q.multiSelect)}
              disabled={submitted}
            >
              Other
            </button>
          </div>
          {(selectedOptions[qi] || []).includes('__other__') && (
            <input
              className="mt-2 w-full rounded-md border border-border bg-transparent px-3 py-1.5 text-sm text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-accent"
              type="text"
              placeholder="Type your answer..."
              value={otherTexts[qi] || ''}
              onChange={(e) => setOtherTexts((p) => ({ ...p, [qi]: e.target.value }))}
              disabled={submitted}
            />
          )}
        </div>
      ))}
      {isWaiting && !submitted && hasSelection && (
        <Button size="sm" variant="primary" onClick={handleSubmit} className="mt-2">
          Submit
        </Button>
      )}
    </div>
  )
}

function StatusIcon({ status }: { status: string }) {
  if (status === 'calling') {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-accent animate-spin">
        <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="16" />
      </svg>
    )
  }
  if (status === 'completed') {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-success-foreground">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    )
  }
  if (status === 'error') {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-destructive-foreground">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    )
  }
  if (status === 'pending_approval') {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-warning-foreground">
        <circle cx="12" cy="12" r="10" />
        <polyline points="12 6 12 12 16 14" />
      </svg>
    )
  }
  return null
}

export function ToolCallCards({ toolCalls, onRespond }: ToolCallCardProps) {
  if (!toolCalls.length) return null
  return (
    <div className="my-1">
      {toolCalls.map((call) => (
        <ToolCallItem key={call.id} call={call} onRespond={onRespond} />
      ))}
    </div>
  )
}
