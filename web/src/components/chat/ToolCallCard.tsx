import { memo, useCallback, useMemo, useState } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import type { ToolCall } from '../../types/chat'
import { cn } from '../../lib/utils'
import { Badge } from './ui/Badge'
import { Button } from './ui/Button'
import type { A2UISurfaceState, UserAction } from '../canvas'
import { A2UIRenderer } from '../canvas'

interface ToolCallCardProps {
  toolCalls: ToolCall[]
  onRespond?: (toolCallId: string, answers: Record<string, string>) => void
  onRespondToApproval?: (toolCallId: string, decision: 'approve' | 'reject' | 'approve_always') => void
  canvasSurfaces?: Map<string, A2UISurfaceState>
  onCanvasInteraction?: (canvasId: string, action: UserAction) => void
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

// --- Tool call grouping types and logic ---

export interface ToolCallGroup {
  kind: 'group'
  toolName: string
  displayName: string
  calls: ToolCall[]
  hasErrors: boolean
  allCompleted: boolean
  hasInFlight: boolean
}
export interface ToolCallSingle { kind: 'single'; call: ToolCall }
export type ToolCallSegment = ToolCallGroup | ToolCallSingle

const UNGROUPABLE_TOOLS = new Set(['render_surface', 'AskUserQuestion'])

export function groupToolCalls(toolCalls: ToolCall[]): ToolCallSegment[] {
  const segments: ToolCallSegment[] = []
  let i = 0

  while (i < toolCalls.length) {
    const call = toolCalls[i]

    if (UNGROUPABLE_TOOLS.has(call.tool_name) || call.status === 'pending_approval') {
      segments.push({ kind: 'single', call })
      i++
      continue
    }

    let j = i + 1
    while (
      j < toolCalls.length &&
      toolCalls[j].tool_name === call.tool_name &&
      !UNGROUPABLE_TOOLS.has(toolCalls[j].tool_name) &&
      toolCalls[j].status !== 'pending_approval'
    ) {
      j++
    }

    const runLength = j - i
    if (runLength >= 2) {
      const calls = toolCalls.slice(i, j)
      segments.push({
        kind: 'group',
        toolName: call.tool_name,
        displayName: formatToolName(call.tool_name),
        calls,
        hasErrors: calls.some(c => c.status === 'error'),
        allCompleted: calls.every(c => c.status === 'completed'),
        hasInFlight: calls.some(c => c.status === 'calling'),
      })
    } else {
      segments.push({ kind: 'single', call })
    }

    i = j
  }

  return segments
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

  // Fallback: syntax-highlighted JSON
  return (
    <div>
      <div className="text-muted-foreground mb-1 font-medium">Arguments</div>
      <SyntaxHighlighter
        style={highlighterTheme}
        language="json"
        PreTag="div"
        customStyle={{ margin: 0, borderRadius: '0.25rem', maxHeight: '24rem', overflow: 'auto' }}
      >
        {JSON.stringify(args, null, 2)}
      </SyntaxHighlighter>
    </div>
  )
}

function ToolResultContent({ call }: { call: ToolCall }) {
  const resultStr = useMemo(() => {
    try {
      if (typeof call.result === 'string') {
        try {
          return JSON.stringify(JSON.parse(call.result), null, 2)
        } catch {
          return call.result
        }
      } else {
        return JSON.stringify(call.result, null, 2)
      }
    } catch (e) {
      if (process.env.NODE_ENV === 'development') console.error('Failed to serialize tool call result:', e)
      return String(call.result)
    }
  }, [call.result])
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

  // Detect if result looks like JSON for syntax highlighting
  const looksLikeJson = resultStr.trimStart().startsWith('{') || resultStr.trimStart().startsWith('[')

  return looksLikeJson ? (
    <SyntaxHighlighter
      style={highlighterTheme}
      language="json"
      PreTag="div"
      customStyle={{ margin: 0, borderRadius: '0.25rem', maxHeight: '24rem', overflow: 'auto' }}
    >
      {resultStr}
    </SyntaxHighlighter>
  ) : (
    <pre className="bg-muted rounded p-2 overflow-x-auto text-foreground max-h-96 overflow-y-auto font-mono text-xs">
      {resultStr}
    </pre>
  )
}

const ToolCallItem = memo(function ToolCallItem({ call, onRespond, onRespondToApproval, canvasSurfaces, onCanvasInteraction, nested = false }: { call: ToolCall; onRespond?: (toolCallId: string, answers: Record<string, string>) => void; onRespondToApproval?: (toolCallId: string, decision: 'approve' | 'reject' | 'approve_always') => void; canvasSurfaces?: Map<string, A2UISurfaceState>; onCanvasInteraction?: (canvasId: string, action: UserAction) => void; nested?: boolean }) {
  const [expanded, setExpanded] = useState(false)
  const displayName = formatToolName(call.tool_name)

  if (call.tool_name === 'render_surface') {
    return <CanvasSurfaceCard call={call} canvasSurfaces={canvasSurfaces} onCanvasInteraction={onCanvasInteraction} />
  }

  if (call.tool_name === 'AskUserQuestion') {
    return <AskUserQuestionCard call={call} onRespond={onRespond} />
  }

  if (call.status === 'pending_approval') {
    return <ToolApprovalCard call={call} onRespondToApproval={onRespondToApproval} />
  }

  const hasDetails = call.arguments || call.result || call.error

  return (
    <div className={cn(
      nested
        ? 'border-b border-border last:border-b-0 overflow-hidden'
        : 'rounded-lg border border-border overflow-hidden my-1.5',
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
})

function ToolApprovalCard({ call, onRespondToApproval }: { call: ToolCall; onRespondToApproval?: (toolCallId: string, decision: 'approve' | 'reject' | 'approve_always') => void }) {
  const displayName = formatToolName(call.tool_name)

  const handleDecision = (decision: 'approve' | 'reject' | 'approve_always') => {
    onRespondToApproval?.(call.id, decision)
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
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault()
                  handleSubmit()
                }
              }}
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

function CanvasSurfaceCard({ call, canvasSurfaces, onCanvasInteraction }: { call: ToolCall; canvasSurfaces?: Map<string, A2UISurfaceState>; onCanvasInteraction?: (canvasId: string, action: UserAction) => void }) {
  const [expanded, setExpanded] = useState(true)
  const args = call.arguments as { canvas_id?: string } | undefined
  const canvasId = args?.canvas_id
  const surfaceState = canvasId ? canvasSurfaces?.get(canvasId) : undefined
  const displayName = formatToolName(call.tool_name)

  return (
    <div className={cn(
      'rounded-lg border border-accent/20 overflow-hidden my-1.5',
      call.status === 'error' && 'border-destructive-foreground/30'
    )}>
      <div
        className="flex items-center gap-2 px-3 py-1.5 text-sm cursor-pointer hover:bg-muted/50 transition-colors bg-accent/5"
        onClick={() => setExpanded(!expanded)}
      >
        <StatusIcon status={call.status} />
        <span className="font-mono text-foreground">{displayName}</span>
        <span className="text-muted-foreground text-xs">{call.server_name}</span>
        {surfaceState && <Badge variant="info" className="ml-2">Interactive</Badge>}
        <div className="flex-1" />
        <span className="text-muted-foreground text-xs">{expanded ? '\u25BC' : '\u25B6'}</span>
      </div>
      {expanded && (
        <div className="border-t border-border px-3 py-2 text-xs space-y-2">
          {surfaceState && onCanvasInteraction ? (
            <A2UIRenderer surfaceState={surfaceState} onAction={onCanvasInteraction} />
          ) : (
            <div className="text-muted-foreground italic">Targeting {canvasId || 'an unknown canvas'}</div>
          )}
          {call.status === 'error' && call.error && (
            <div>
              <div className="text-destructive-foreground mb-1 font-medium mt-2">Error</div>
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

function GroupStatusIcon({ hasErrors, allCompleted, hasInFlight }: { hasErrors: boolean; allCompleted: boolean; hasInFlight: boolean }) {
  if (hasInFlight) {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-accent animate-spin">
        <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="16" />
      </svg>
    )
  }
  if (hasErrors) {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-destructive-foreground">
        <line x1="18" y1="6" x2="6" y2="18" />
        <line x1="6" y1="6" x2="18" y2="18" />
      </svg>
    )
  }
  if (allCompleted) {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-success-foreground">
        <polyline points="20 6 9 17 4 12" />
      </svg>
    )
  }
  return null
}

function ToolCallGroupHeader({ group, expanded, onToggle, onRespond, onRespondToApproval, canvasSurfaces, onCanvasInteraction }: {
  group: ToolCallGroup
  expanded: boolean
  onToggle: () => void
  onRespond?: (toolCallId: string, answers: Record<string, string>) => void
  onRespondToApproval?: (toolCallId: string, decision: 'approve' | 'reject' | 'approve_always') => void
  canvasSurfaces?: Map<string, A2UISurfaceState>
  onCanvasInteraction?: (canvasId: string, action: UserAction) => void
}) {
  const serverName = group.calls[0]?.server_name

  return (
    <div className={cn(
      'rounded-lg border overflow-hidden my-1.5',
      group.hasErrors ? 'border-destructive-foreground/30' : group.hasInFlight ? 'border-accent/30' : 'border-border'
    )}>
      <div
        className="flex items-center gap-2 px-3 py-1.5 text-sm cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={onToggle}
      >
        <GroupStatusIcon hasErrors={group.hasErrors} allCompleted={group.allCompleted} hasInFlight={group.hasInFlight} />
        <span className="font-mono text-foreground">{group.displayName}</span>
        <Badge variant="default">×{group.calls.length}</Badge>
        {serverName && <span className="text-muted-foreground text-xs">{serverName}</span>}
        <div className="flex-1" />
        <span className="text-muted-foreground text-xs">{expanded ? '\u25BC' : '\u25B6'}</span>
      </div>
      {expanded && (
        <div className="border-t border-border pl-4">
          {group.calls.map(call => (
            <ToolCallItem
              key={call.id}
              call={call}
              nested
              onRespond={onRespond}
              onRespondToApproval={onRespondToApproval}
              canvasSurfaces={canvasSurfaces}
              onCanvasInteraction={onCanvasInteraction}
            />
          ))}
        </div>
      )}
    </div>
  )
}

// --- Tier 1: Tool Chain wrapper (collapsible group of all calls between text blocks) ---

function buildChainSummary(toolCalls: ToolCall[]): string {
  const counts = new Map<string, number>()
  for (const tc of toolCalls) {
    const name = formatToolName(tc.tool_name)
    counts.set(name, (counts.get(name) || 0) + 1)
  }
  const parts = Array.from(counts.entries()).map(([name, count]) =>
    count > 1 ? `${count} ${name}` : name
  )
  return parts.join(', ')
}

interface ToolChainGroupProps {
  toolCalls: ToolCall[]
  onRespond?: (toolCallId: string, answers: Record<string, string>) => void
  onRespondToApproval?: (toolCallId: string, decision: 'approve' | 'reject' | 'approve_always') => void
  canvasSurfaces?: Map<string, A2UISurfaceState>
  onCanvasInteraction?: (canvasId: string, action: UserAction) => void
}

export const ToolChainGroup = memo(function ToolChainGroup({ toolCalls, onRespond, onRespondToApproval, canvasSurfaces, onCanvasInteraction }: ToolChainGroupProps) {
  const hasInFlight = toolCalls.some(tc => tc.status === 'calling')
  const hasApproval = toolCalls.some(tc => tc.status === 'pending_approval')
  const hasErrors = toolCalls.some(tc => tc.status === 'error')
  const allCompleted = toolCalls.every(tc => tc.status === 'completed')
  // Auto-expand if something needs attention; collapse when all done
  const [expanded, setExpanded] = useState(hasInFlight || hasApproval || !allCompleted)

  const summary = useMemo(() => buildChainSummary(toolCalls), [toolCalls])
  const count = toolCalls.length

  if (!count) return null

  // Single call — no point wrapping in a "1 tool call" group, render directly
  if (count === 1) {
    return (
      <ToolCallCards
        toolCalls={toolCalls}
        onRespond={onRespond}
        onRespondToApproval={onRespondToApproval}
        canvasSurfaces={canvasSurfaces}
        onCanvasInteraction={onCanvasInteraction}
      />
    )
  }

  return (
    <div className={cn(
      'rounded-lg border overflow-hidden my-1.5',
      hasErrors ? 'border-destructive-foreground/30' : hasInFlight ? 'border-accent/30' : 'border-border'
    )}>
      <div
        className="flex items-center gap-2 px-3 py-1.5 text-sm cursor-pointer hover:bg-muted/50 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <GroupStatusIcon hasErrors={hasErrors} allCompleted={allCompleted} hasInFlight={hasInFlight} />
        <span className="text-muted-foreground">
          {count} tool call{count !== 1 ? 's' : ''}
        </span>
        <span className="text-muted-foreground/60 text-xs truncate">{summary}</span>
        <div className="flex-1" />
        <span className="text-muted-foreground text-xs">{expanded ? '\u25BC' : '\u25B6'}</span>
      </div>
      {expanded && (
        <div className="border-t border-border px-3">
          <ToolCallCards
            toolCalls={toolCalls}
            onRespond={onRespond}
            onRespondToApproval={onRespondToApproval}
            canvasSurfaces={canvasSurfaces}
            onCanvasInteraction={onCanvasInteraction}
          />
        </div>
      )}
    </div>
  )
})

export const ToolCallCards = memo(function ToolCallCards({ toolCalls, onRespond, onRespondToApproval, canvasSurfaces, onCanvasInteraction }: ToolCallCardProps) {
  const segments = useMemo(() => groupToolCalls(toolCalls), [toolCalls])
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(() => new Set())

  const toggleGroup = useCallback((key: string) => {
    setExpandedGroups(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }, [])

  if (!toolCalls.length) return null

  return (
    <div className="my-1">
      {segments.map(segment => {
        if (segment.kind === 'single') {
          return (
            <ToolCallItem
              key={segment.call.id}
              call={segment.call}
              onRespond={onRespond}
              onRespondToApproval={onRespondToApproval}
              canvasSurfaces={canvasSurfaces}
              onCanvasInteraction={onCanvasInteraction}
            />
          )
        }
        const groupKey = `${segment.calls[0].id}-${segment.toolName}`
        return (
          <ToolCallGroupHeader
            key={groupKey}
            group={segment}
            expanded={expandedGroups.has(groupKey)}
            onToggle={() => toggleGroup(groupKey)}
            onRespond={onRespond}
            onRespondToApproval={onRespondToApproval}
            canvasSurfaces={canvasSurfaces}
            onCanvasInteraction={onCanvasInteraction}
          />
        )
      })}
    </div>
  )
})
