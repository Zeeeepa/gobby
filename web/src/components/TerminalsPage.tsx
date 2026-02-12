import { useEffect, useRef, useCallback, useState } from 'react'
import { Terminal as XTerm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { TmuxSession } from '../hooks/useTmuxSessions'
import { MenuIcon } from './Icons'

interface TerminalsPageProps {
  sessions: TmuxSession[]
  attachedSession: string | null
  streamingId: string | null
  isLoading: boolean
  attachSession: (sessionName: string, socket: string) => void
  createSession: (name?: string, socket?: string) => void
  killSession: (sessionName: string, socket: string) => void
  refreshSessions: () => void
  sendInput: (data: string) => void
  resizeTerminal: (rows: number, cols: number) => void
  onOutput: (callback: (runId: string, data: string) => void) => void
}

const TERMINAL_NAMES_KEY = 'gobby-terminal-names'

function loadTerminalNames(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(TERMINAL_NAMES_KEY) || '{}')
  } catch { return {} }
}

function saveTerminalNames(names: Record<string, string>) {
  localStorage.setItem(TERMINAL_NAMES_KEY, JSON.stringify(names))
}

export function TerminalsPage({
  sessions,
  attachedSession,
  streamingId,
  isLoading,
  attachSession,
  createSession,
  killSession,
  refreshSessions,
  sendInput,
  resizeTerminal,
  onOutput,
}: TerminalsPageProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [isInteractive, setIsInteractive] = useState(false)
  const [terminalNames, setTerminalNames] = useState<Record<string, string>>(loadTerminalNames)

  const handleRename = useCallback((key: string, newName: string) => {
    setTerminalNames(prev => {
      const next = { ...prev }
      if (newName.trim()) {
        next[key] = newName.trim()
      } else {
        delete next[key]
      }
      saveTerminalNames(next)
      return next
    })
  }, [])

  // Reset interactive mode when switching sessions
  useEffect(() => {
    setIsInteractive(false)
  }, [streamingId])

  // Track attached session's socket for kill
  const attachedSocketRef = useRef<string>('default')

  const handleAttach = useCallback((name: string, socket: string) => {
    attachSession(name, socket)
    attachedSocketRef.current = socket
    setSidebarOpen(false)
  }, [attachSession])

  const handleKill = useCallback((sessionName: string, socket: string) => {
    if (!window.confirm(`Kill terminal "${sessionName}"?`)) return
    killSession(sessionName, socket)
    setIsInteractive(false)
  }, [killSession])

  const defaultSessions = sessions.filter(s => s.socket === 'default')
  const gobbySessions = sessions.filter(s => s.socket === 'gobby')

  return (
    <div className="terminals-page">
      {/* Sidebar */}
      <div className={`terminals-sidebar ${sidebarOpen ? '' : 'collapsed'}`}>
        <div className="terminals-sidebar-header">
          <span className="terminals-sidebar-title">Terminals</span>
          <div className="terminals-sidebar-actions">
            <button
              className="terminals-action-btn"
              onClick={refreshSessions}
              title="Refresh"
              disabled={isLoading}
            >
              <RefreshIcon />
            </button>
            <button
              className="terminals-action-btn"
              onClick={() => createSession()}
              title="New terminal"
            >
              <PlusIcon />
            </button>
            <button
              className="terminals-sidebar-toggle"
              onClick={() => setSidebarOpen(!sidebarOpen)}
            >
              {sidebarOpen ? '\u25C0' : '\u25B6'}
            </button>
          </div>
        </div>

        {sidebarOpen && (
          <div className="terminals-session-list">
            {sessions.length === 0 && (
              <div className="terminals-empty-sidebar">
                No tmux terminals found
              </div>
            )}

            {defaultSessions.length > 0 && (
              <SessionGroup
                label="Your Terminals"
                sessions={defaultSessions}
                attachedSession={attachedSession}
                streamingId={streamingId}
                terminalNames={terminalNames}
                onAttach={handleAttach}
                onRename={handleRename}
              />
            )}

            {gobbySessions.length > 0 && (
              <SessionGroup
                label="Agent Terminals"
                sessions={gobbySessions}
                attachedSession={attachedSession}
                streamingId={streamingId}
                terminalNames={terminalNames}
                onAttach={handleAttach}
                onRename={handleRename}
              />
            )}
          </div>
        )}
      </div>

      {/* Terminal area */}
      <div className="terminals-main">
        {streamingId ? (
          <TerminalView
            streamingId={streamingId}
            sessionName={attachedSession}
            displayName={attachedSession ? (terminalNames[`${attachedSocketRef.current}:${attachedSession}`] || attachedSession) : null}
            isInteractive={isInteractive}
            sidebarOpen={sidebarOpen}
            onSetInteractive={setIsInteractive}
            onToggleSidebar={() => setSidebarOpen(!sidebarOpen)}
            sendInput={sendInput}
            resizeTerminal={resizeTerminal}
            onOutput={onOutput}
            onKill={() => {
              if (attachedSession) {
                handleKill(attachedSession, attachedSocketRef.current)
              }
            }}
          />
        ) : (
          <div className="terminals-empty">
            {!sidebarOpen && (
              <button
                className="terminals-action-btn terminals-open-sidebar-btn"
                onClick={() => setSidebarOpen(true)}
                title="Show terminals"
              >
                <MenuIcon />
              </button>
            )}
            <TerminalIcon size={48} />
            <h3>No terminal attached</h3>
            <p>Select a terminal from the sidebar or create a new one.</p>
            <button
              className="terminals-create-btn"
              onClick={() => createSession()}
            >
              <PlusIcon /> Create Terminal
            </button>
          </div>
        )}

        {/* Mobile special-key toolbar */}
        {streamingId && isInteractive && (
          <div className="terminals-mobile-toolbar">
            <button onClick={() => sendInput('\x1b')}>Esc</button>
            <button onClick={() => sendInput('\t')}>Tab</button>
            <button onClick={() => sendInput('\x03')}>Ctrl+C</button>
            <button onClick={() => sendInput('\x04')}>Ctrl+D</button>
            <button onClick={() => sendInput('\x1b[A')}>&uarr;</button>
            <button onClick={() => sendInput('\x1b[B')}>&darr;</button>
            <button onClick={() => sendInput('\x1b[D')}>&larr;</button>
            <button onClick={() => sendInput('\x1b[C')}>&rarr;</button>
          </div>
        )}
      </div>
    </div>
  )
}

// -- Subcomponents --

interface SessionGroupProps {
  label: string
  sessions: TmuxSession[]
  attachedSession: string | null
  streamingId: string | null
  terminalNames: Record<string, string>
  onAttach: (name: string, socket: string) => void
  onRename: (key: string, newName: string) => void
}

function SessionGroup({ label, sessions, attachedSession, streamingId, terminalNames, onAttach, onRename }: SessionGroupProps) {
  const [editingKey, setEditingKey] = useState<string | null>(null)
  const [editValue, setEditValue] = useState('')

  return (
    <div className="session-group">
      <div className="session-group-label">{label}</div>
      {sessions.map((session) => {
        const isAttached = attachedSession === session.name && streamingId !== null
        const nameKey = `${session.socket}:${session.name}`
        const displayName = terminalNames[nameKey] || session.name
        const isEditing = editingKey === nameKey

        return (
          <div
            key={`${session.socket}-${session.name}`}
            className={`session-item ${isAttached ? 'attached' : ''}`}
            onClick={() => !isEditing && onAttach(session.name, session.socket)}
          >
            <div className="session-item-main">
              <span className={`session-dot ${session.socket === 'gobby' ? 'agent' : 'user'}`} />
              {isEditing ? (
                <input
                  className="session-name-input"
                  value={editValue}
                  onChange={e => setEditValue(e.target.value)}
                  onBlur={() => {
                    onRename(nameKey, editValue)
                    setEditingKey(null)
                  }}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      onRename(nameKey, editValue)
                      setEditingKey(null)
                    } else if (e.key === 'Escape') {
                      setEditingKey(null)
                    }
                  }}
                  onClick={e => e.stopPropagation()}
                  autoFocus
                />
              ) : (
                <span
                  className="session-name"
                  onDoubleClick={e => {
                    e.stopPropagation()
                    setEditingKey(nameKey)
                    setEditValue(displayName)
                  }}
                  title="Double-click to rename"
                >
                  {displayName}
                </span>
              )}
              {session.agent_managed && (
                <span className="session-badge agent-badge">agent</span>
              )}
            </div>
            <div className="session-item-actions">
              {session.pane_pid && (
                <span className="session-pid">PID {session.pane_pid}</span>
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}

interface TerminalViewProps {
  streamingId: string
  sessionName: string | null
  displayName: string | null
  isInteractive: boolean
  sidebarOpen: boolean
  onSetInteractive: (interactive: boolean) => void
  onToggleSidebar: () => void
  sendInput: (data: string) => void
  resizeTerminal: (rows: number, cols: number) => void
  onOutput: (callback: (runId: string, data: string) => void) => void
  onKill: () => void
}

function TerminalView({
  streamingId,
  sessionName,
  displayName,
  isInteractive,
  sidebarOpen,
  onSetInteractive,
  onToggleSidebar,
  sendInput,
  resizeTerminal,
  onOutput,
  onKill,
}: TerminalViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const terminalRef = useRef<XTerm | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)
  const isInteractiveRef = useRef(isInteractive)

  // Keep ref in sync for use inside terminal.onData callback
  // Also show/hide cursor based on interactive state
  useEffect(() => {
    isInteractiveRef.current = isInteractive
    if (terminalRef.current) {
      terminalRef.current.options.cursorBlink = isInteractive
      terminalRef.current.options.cursorStyle = isInteractive ? 'block' : 'bar'
      terminalRef.current.options.cursorInactiveStyle = isInteractive ? 'outline' : 'none'
    }
  }, [isInteractive])

  // Initialize terminal
  useEffect(() => {
    if (!containerRef.current) return

    const terminal = new XTerm({
      fontFamily: "'SF Mono', 'Fira Code', 'JetBrains Mono', monospace",
      fontSize: 14,
      theme: {
        background: '#0a0a0a',
        foreground: '#e5e5e5',
        cursor: '#3b82f6',
        cursorAccent: '#0a0a0a',
        selectionBackground: '#3b82f680',
        black: '#e5e5e5',
        red: '#f87171',
        green: '#4ade80',
        yellow: '#facc15',
        blue: '#3b82f6',
        magenta: '#c084fc',
        cyan: '#22d3ee',
        white: '#e5e5e5',
        brightBlack: '#737373',
        brightRed: '#fca5a5',
        brightGreen: '#86efac',
        brightYellow: '#fde047',
        brightBlue: '#60a5fa',
        brightMagenta: '#d8b4fe',
        brightCyan: '#67e8f9',
        brightWhite: '#ffffff',
      },
      cursorBlink: false,
      cursorStyle: 'bar',
      cursorInactiveStyle: 'none',
      scrollback: 10000,
      convertEol: true,
      minimumContrastRatio: 4.5,
    })

    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)

    terminal.open(containerRef.current)
    requestAnimationFrame(() => {
      fitAddon.fit()
    })

    terminalRef.current = terminal
    fitAddonRef.current = fitAddon

    // Shift+Enter handler — send newline even when xterm might not
    terminal.attachCustomKeyEventHandler((event) => {
      if (event.shiftKey && event.key === 'Enter' && event.type === 'keydown') {
        if (isInteractiveRef.current) {
          sendInput('\n')
        }
        return false
      }
      return true
    })

    // Send input to backend only when interactive
    const inputDisposable = terminal.onData((data) => {
      if (isInteractiveRef.current) {
        sendInput(data)
      }
    })

    // Send resize to backend — only when dimensions actually change
    let prevCols = 0
    let prevRows = 0
    const resizeDisposable = terminal.onResize(({ rows, cols }) => {
      if (cols !== prevCols || rows !== prevRows) {
        prevCols = cols
        prevRows = rows
        resizeTerminal(rows, cols)
      }
    })

    // Observe container resize — debounced
    let resizeTimeout: ReturnType<typeof setTimeout>
    const resizeObserver = new ResizeObserver(() => {
      clearTimeout(resizeTimeout)
      resizeTimeout = setTimeout(() => {
        requestAnimationFrame(() => {
          fitAddon.fit()
        })
      }, 100)
    })
    resizeObserver.observe(containerRef.current)

    const handleWindowResize = () => {
      clearTimeout(resizeTimeout)
      resizeTimeout = setTimeout(() => {
        requestAnimationFrame(() => {
          fitAddon.fit()
        })
      }, 100)
    }
    window.addEventListener('resize', handleWindowResize)

    // Initial resize notification
    const dims = fitAddon.proposeDimensions()
    if (dims) {
      resizeTerminal(dims.rows, dims.cols)
    }

    return () => {
      clearTimeout(resizeTimeout)
      inputDisposable.dispose()
      resizeDisposable.dispose()
      resizeObserver.disconnect()
      window.removeEventListener('resize', handleWindowResize)
      terminal.dispose()
    }
  }, [streamingId]) // Re-create terminal on new attachment

  // Handle output
  const handleOutput = useCallback((outputRunId: string, data: string) => {
    if (outputRunId === streamingId && terminalRef.current) {
      terminalRef.current.write(data)
    }
  }, [streamingId])

  useEffect(() => {
    onOutput(handleOutput)
  }, [onOutput, handleOutput])

  return (
    <div className="terminals-terminal-wrapper">
      <div className="terminals-terminal-header">
        <span className="terminals-terminal-title">
          {!sidebarOpen && (
            <button
              className="terminals-action-btn terminals-open-sidebar-btn"
              onClick={onToggleSidebar}
              title="Show terminals"
            >
              <MenuIcon />
            </button>
          )}
          <TerminalIcon size={14} />
          {displayName || sessionName || 'Terminal'}
          {!isInteractive && (
            <span className="read-only-badge">read-only</span>
          )}
        </span>
        <div className="terminals-header-actions">
          {isInteractive ? (
            <button className="terminals-detach-btn" onClick={() => onSetInteractive(false)}>
              Detach
            </button>
          ) : (
            <button className="terminals-attach-btn" onClick={() => onSetInteractive(true)}>
              Attach
            </button>
          )}
          <button className="terminals-kill-btn" onClick={onKill} title="Kill terminal">
            <TrashIcon />
          </button>
        </div>
      </div>
      <div className="terminals-terminal-container">
        <div ref={containerRef} className="terminals-terminal-content" />
      </div>
    </div>
  )
}

// -- Icons --

function TerminalIcon({ size = 16 }: { size?: number }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" y1="19" x2="20" y2="19" />
    </svg>
  )
}

function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
  )
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function TrashIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    </svg>
  )
}

