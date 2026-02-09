import { useEffect, useRef, useCallback, useState } from 'react'
import { Terminal as XTerm } from '@xterm/xterm'
import { FitAddon } from '@xterm/addon-fit'
import '@xterm/xterm/css/xterm.css'
import { TmuxSession } from '../hooks/useTmuxSessions'

interface TerminalsPageProps {
  sessions: TmuxSession[]
  attachedSession: string | null
  streamingId: string | null
  isLoading: boolean
  attachSession: (sessionName: string, socket: string) => void
  detachSession: () => void
  createSession: (name?: string, socket?: string) => void
  killSession: (sessionName: string, socket: string) => void
  refreshSessions: () => void
  sendInput: (data: string) => void
  resizeTerminal: (rows: number, cols: number) => void
  onOutput: (callback: (runId: string, data: string) => void) => void
}

export function TerminalsPage({
  sessions,
  attachedSession,
  streamingId,
  isLoading,
  attachSession,
  detachSession,
  createSession,
  killSession,
  refreshSessions,
  sendInput,
  resizeTerminal,
  onOutput,
}: TerminalsPageProps) {
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const defaultSessions = sessions.filter(s => s.socket === 'default')
  const gobbySessions = sessions.filter(s => s.socket === 'gobby')

  return (
    <div className="terminals-page">
      {/* Sidebar */}
      <div className={`terminals-sidebar ${sidebarOpen ? '' : 'collapsed'}`}>
        <div className="terminals-sidebar-header">
          <span className="terminals-sidebar-title">Sessions</span>
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
              title="New session"
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
                No tmux sessions found
              </div>
            )}

            {defaultSessions.length > 0 && (
              <SessionGroup
                label="Your Sessions"
                sessions={defaultSessions}
                attachedSession={attachedSession}
                streamingId={streamingId}
                onAttach={attachSession}
                onDetach={detachSession}
                onKill={killSession}
              />
            )}

            {gobbySessions.length > 0 && (
              <SessionGroup
                label="Agent Sessions"
                sessions={gobbySessions}
                attachedSession={attachedSession}
                streamingId={streamingId}
                onAttach={attachSession}
                onDetach={detachSession}
                onKill={killSession}
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
            sendInput={sendInput}
            resizeTerminal={resizeTerminal}
            onOutput={onOutput}
            onDetach={detachSession}
          />
        ) : (
          <div className="terminals-empty">
            <TerminalIcon size={48} />
            <h3>No session attached</h3>
            <p>Select a session from the sidebar or create a new one.</p>
            <button
              className="terminals-create-btn"
              onClick={() => createSession()}
            >
              <PlusIcon /> Create Session
            </button>
          </div>
        )}

        {/* Mobile special-key toolbar */}
        {streamingId && (
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
  onAttach: (name: string, socket: string) => void
  onDetach: () => void
  onKill: (name: string, socket: string) => void
}

function SessionGroup({ label, sessions, attachedSession, streamingId, onAttach, onDetach, onKill }: SessionGroupProps) {
  return (
    <div className="session-group">
      <div className="session-group-label">{label}</div>
      {sessions.map((session) => {
        const isAttached = attachedSession === session.name && streamingId !== null
        return (
          <div
            key={`${session.socket}-${session.name}`}
            className={`session-item ${isAttached ? 'attached' : ''}`}
          >
            <div
              className="session-item-main"
              onClick={() => {
                if (isAttached) {
                  onDetach()
                } else {
                  onAttach(session.name, session.socket)
                }
              }}
            >
              <span className={`session-dot ${session.socket === 'gobby' ? 'agent' : 'user'}`} />
              <span className="session-name">{session.name}</span>
              {session.agent_managed && (
                <span className="session-badge agent-badge">agent</span>
              )}
              {isAttached && (
                <span className="session-badge attached-badge">attached</span>
              )}
            </div>
            <div className="session-item-actions">
              {session.pane_pid && (
                <span className="session-pid">PID {session.pane_pid}</span>
              )}
              {!session.agent_managed && (
                <button
                  className="session-kill-btn"
                  onClick={(e) => {
                    e.stopPropagation()
                    onKill(session.name, session.socket)
                  }}
                  title="Kill session"
                >
                  <XIcon />
                </button>
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
  sendInput: (data: string) => void
  resizeTerminal: (rows: number, cols: number) => void
  onOutput: (callback: (runId: string, data: string) => void) => void
  onDetach: () => void
}

function TerminalView({ streamingId, sessionName, sendInput, resizeTerminal, onOutput, onDetach }: TerminalViewProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const terminalRef = useRef<XTerm | null>(null)
  const fitAddonRef = useRef<FitAddon | null>(null)

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
        black: '#0a0a0a',
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
      cursorBlink: true,
      scrollback: 10000,
    })

    const fitAddon = new FitAddon()
    terminal.loadAddon(fitAddon)

    terminal.open(containerRef.current)
    fitAddon.fit()

    terminalRef.current = terminal
    fitAddonRef.current = fitAddon

    // Send input to backend
    const inputDisposable = terminal.onData((data) => {
      sendInput(data)
    })

    // Send resize to backend
    const resizeDisposable = terminal.onResize(({ rows, cols }) => {
      resizeTerminal(rows, cols)
    })

    // Observe container resize
    const resizeObserver = new ResizeObserver(() => {
      fitAddon.fit()
    })
    resizeObserver.observe(containerRef.current)

    const handleWindowResize = () => fitAddon.fit()
    window.addEventListener('resize', handleWindowResize)

    // Initial resize notification
    const dims = fitAddon.proposeDimensions()
    if (dims) {
      resizeTerminal(dims.rows, dims.cols)
    }

    return () => {
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
          <TerminalIcon size={14} />
          {sessionName || 'Terminal'}
        </span>
        <button className="terminals-detach-btn" onClick={onDetach}>
          Detach
        </button>
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

function XIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}
