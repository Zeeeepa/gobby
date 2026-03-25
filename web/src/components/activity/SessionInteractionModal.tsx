import { useState, useCallback, useEffect, useRef } from 'react'
import {
  Dialog,
  DialogContent,
  DialogTitle,
  DialogDescription,
} from '../chat/ui/Dialog'

interface SessionEntry {
  id: string
  type: 'agent' | 'cli'
  label: string
  hasTmux: boolean
  runId?: string
  seqNum?: number | null
}

export type InteractionMode = 'context' | 'command' | 'keys' | 'pane'

interface SessionInteractionModalProps {
  open: boolean
  onClose: () => void
  mode: InteractionMode
  entry: SessionEntry
  fromSessionId?: string
}

const MODE_CONFIG: Record<InteractionMode, { title: string; description: string; placeholder: string }> = {
  context: {
    title: 'Send Context',
    description: 'Inject context into the session. The agent will see this on its next hook cycle.',
    placeholder: 'Enter context to inject...',
  },
  command: {
    title: 'Send Command',
    description: 'Send a command the agent must execute before proceeding.',
    placeholder: 'Enter command text...',
  },
  keys: {
    title: 'Send Keys',
    description: 'Send keystrokes directly to the tmux terminal.',
    placeholder: 'Type text to send...',
  },
  pane: {
    title: 'Capture Pane',
    description: 'Terminal output from the session.',
    placeholder: '',
  },
}

// Quick-send buttons for keys mode
const QUICK_KEYS = [
  { label: 'Ctrl-C', keys: 'C-c', literal: false },
  { label: 'Enter', keys: 'Enter', literal: false },
  { label: 'Escape', keys: 'Escape', literal: false },
  { label: 'y + Enter', keys: 'y\n', literal: true },
  { label: 'n + Enter', keys: 'n\n', literal: true },
]

function getBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || ''
}

async function callTool(
  serverName: string,
  toolName: string,
  args: Record<string, unknown>,
): Promise<any> {
  const baseUrl = getBaseUrl()
  const response = await fetch(`${baseUrl}/api/mcp/tools/call`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      server_name: serverName,
      tool_name: toolName,
      arguments: args,
    }),
  })
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }
  return response.json()
}

export function SessionInteractionModal({
  open,
  onClose,
  mode,
  entry,
  fromSessionId,
}: SessionInteractionModalProps) {
  const [text, setText] = useState('')
  const [literal, setLiteral] = useState(true)
  const [paneOutput, setPaneOutput] = useState<string | null>(null)
  const [paneLoading, setPaneLoading] = useState(false)
  const [sending, setSending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const inputRef = useRef<HTMLTextAreaElement>(null)

  // Reset state when modal opens
  useEffect(() => {
    if (open) {
      setText('')
      setLiteral(true)
      setError(null)
      setPaneOutput(null)
      setSending(false)
      if (mode === 'pane') {
        fetchPane()
      }
    }
  }, [open, mode])

  // Focus input when modal opens
  useEffect(() => {
    if (open && mode !== 'pane') {
      setTimeout(() => inputRef.current?.focus(), 100)
    }
  }, [open, mode])

  const fetchPane = useCallback(async () => {
    setPaneLoading(true)
    setError(null)
    try {
      const result = await callTool('gobby-sessions', 'capture_output', {
        session_id: entry.id,
        lines: 80,
      })
      if (result?.success) {
        setPaneOutput(result.output ?? result.result?.output ?? '')
      } else {
        setError(result?.error ?? result?.result?.error ?? 'Failed to capture pane')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to capture pane')
    } finally {
      setPaneLoading(false)
    }
  }, [entry.id])

  const handleSend = useCallback(async () => {
    if (!text.trim() && mode !== 'keys') return
    setSending(true)
    setError(null)
    try {
      let result: any
      if (mode === 'context') {
        result = await callTool('gobby-agents', 'send_message', {
          from_session: fromSessionId ?? '',
          to_session: entry.id,
          content: text,
        })
      } else if (mode === 'command') {
        result = await callTool('gobby-agents', 'send_command', {
          from_session: fromSessionId ?? '',
          to_session: entry.id,
          command_text: text,
        })
      } else if (mode === 'keys') {
        result = await callTool('gobby-sessions', 'send_keys', {
          session_id: entry.id,
          keys: text,
          literal,
        })
      }
      const inner = result?.result ?? result
      if (inner?.success) {
        onClose()
      } else {
        setError(inner?.error ?? 'Operation failed')
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Operation failed')
    } finally {
      setSending(false)
    }
  }, [text, literal, mode, entry.id, fromSessionId, onClose])

  const handleQuickKey = useCallback(
    async (keys: string, isLiteral: boolean) => {
      setSending(true)
      setError(null)
      try {
        const result = await callTool('gobby-sessions', 'send_keys', {
          session_id: entry.id,
          keys,
          literal: isLiteral,
        })
        const inner = result?.result ?? result
        if (inner?.success) {
          onClose()
        } else {
          setError(inner?.error ?? 'Failed to send keys')
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to send keys')
      } finally {
        setSending(false)
      }
    },
    [entry.id, onClose]
  )

  const config = MODE_CONFIG[mode]
  const displayLabel = entry.seqNum ? `#${entry.seqNum}: ${entry.label}` : entry.label

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-md">
        <DialogTitle>{config.title}</DialogTitle>
        <DialogDescription>
          {config.description}
          <br />
          <span className="text-xs text-muted-foreground mt-1">Target: {displayLabel}</span>
        </DialogDescription>

        {mode === 'pane' ? (
          <div className="mt-3">
            {paneLoading ? (
              <div className="text-xs text-muted-foreground p-3">Loading...</div>
            ) : (
              <pre className="session-pane-output">{paneOutput ?? 'No output'}</pre>
            )}
            <div className="flex justify-end gap-2 mt-3">
              <button className="session-modal-btn session-modal-btn--secondary" onClick={fetchPane} disabled={paneLoading}>
                Refresh
              </button>
              <button className="session-modal-btn" onClick={onClose}>
                Close
              </button>
            </div>
          </div>
        ) : (
          <div className="mt-3">
            <textarea
              ref={inputRef}
              className="session-modal-textarea"
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={config.placeholder}
              rows={mode === 'keys' ? 2 : 4}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) {
                  e.preventDefault()
                  handleSend()
                }
              }}
            />

            {mode === 'keys' && (
              <>
                <div className="flex items-center gap-2 mt-2">
                  <label className="text-xs text-muted-foreground flex items-center gap-1.5">
                    <input
                      type="checkbox"
                      checked={literal}
                      onChange={(e) => setLiteral(e.target.checked)}
                      className="rounded"
                    />
                    Literal mode
                  </label>
                  <span className="text-xs text-muted-foreground">
                    {literal ? '(text as-is, \\n = Enter)' : '(tmux key names: C-c, Escape, etc.)'}
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5 mt-2">
                  {QUICK_KEYS.map((qk) => (
                    <button
                      key={qk.label}
                      className="session-modal-quickkey"
                      onClick={() => handleQuickKey(qk.keys, qk.literal)}
                      disabled={sending}
                    >
                      {qk.label}
                    </button>
                  ))}
                </div>
              </>
            )}

            {error && <p className="text-xs text-red-400 mt-2">{error}</p>}

            <div className="flex justify-end gap-2 mt-3">
              <button className="session-modal-btn session-modal-btn--secondary" onClick={onClose}>
                Cancel
              </button>
              <button className="session-modal-btn" onClick={handleSend} disabled={sending || (!text.trim() && mode !== 'keys')}>
                {sending ? 'Sending...' : 'Send'}
              </button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}
