import { useState, useEffect, useCallback, useRef } from 'react'

const SHOW_MODES = ['embedded', 'tmux', 'terminal'] as const

interface WebSocketMessage {
  type: string
  [key: string]: unknown
}

interface TerminalOutputMessage {
  type: 'terminal_output'
  run_id: string
  data: string
  timestamp: string
}

interface AgentEventMessage {
  type: 'agent_event'
  event: string
  run_id: string
  parent_session_id: string
  session_id?: string
  mode?: string
  provider?: string
  pid?: number
  tmux_session_name?: string
}

export interface RunningAgent {
  run_id: string
  session_id: string
  parent_session_id: string
  mode: string
  provider: string
  pid?: number
  tmux_session_name?: string
}

export function useTerminal() {
  const [isConnected, setIsConnected] = useState(false)
  const [agents, setAgents] = useState<RunningAgent[]>([])
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const outputCallbackRef = useRef<((runId: string, data: string) => void) | null>(null)

  // Fetch running agents from the API and replace local state (reconciliation)
  const refreshAgents = useCallback(() => {
    fetch('/api/agents/running')
      .then(r => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json() })
      .then(data => {
        if (data.agents) {
          const fresh: RunningAgent[] = data.agents
            .filter((a: RunningAgent) => (SHOW_MODES as readonly string[]).includes(a.mode))
            .map((a: RunningAgent) => ({
              run_id: a.run_id,
              session_id: a.session_id,
              parent_session_id: a.parent_session_id,
              mode: a.mode,
              provider: a.provider,
              pid: a.pid,
              tmux_session_name: a.tmux_session_name,
            }))
          setAgents(fresh)
          // Clear selection if the selected agent is no longer running
          setSelectedAgent(prev => prev && fresh.some(a => a.run_id === prev) ? prev : null)
        }
      })
      .catch((e) => console.debug('Failed to fetch running agents:', e))
  }, [])

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const isSecure = window.location.protocol === 'https:'
    const wsUrl = isSecure
      ? `wss://${window.location.host}/ws`
      : `ws://${window.location.host}/ws`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setIsConnected(true)
      // Subscribe to terminal and agent events
      ws.send(JSON.stringify({
        type: 'subscribe',
        events: ['terminal_output', 'agent_event'],
      }))
      // Fetch current running agents to recover any missed before WS connected
      refreshAgents()
    }

    ws.onclose = () => {
      setIsConnected(false)
      // Reconnect after 2 seconds
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect()
      }, 2000)
    }

    ws.onerror = (error) => {
      console.error('Terminal WebSocket error:', error)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WebSocketMessage

        if (data.type === 'terminal_output') {
          const msg = data as unknown as TerminalOutputMessage
          if (outputCallbackRef.current) {
            outputCallbackRef.current(msg.run_id, msg.data)
          }
        } else if (data.type === 'agent_event') {
          const msg = data as unknown as AgentEventMessage
          handleAgentEvent(msg)
        }
      } catch (e) {
        console.error('Failed to parse terminal message:', e)
      }
    }
  }, [])

  // Handle agent lifecycle events
  const handleAgentEvent = useCallback((event: AgentEventMessage) => {
    if (event.event === 'agent_started' && (SHOW_MODES as readonly string[]).includes(event.mode || '')) {
      // Add new agent (embedded, tmux, or terminal)
      setAgents(prev => {
        const exists = prev.some(a => a.run_id === event.run_id)
        if (exists) return prev
        return [...prev, {
          run_id: event.run_id,
          session_id: event.session_id || '',
          parent_session_id: event.parent_session_id,
          mode: event.mode || 'embedded',
          provider: event.provider || 'unknown',
          pid: event.pid,
          tmux_session_name: event.tmux_session_name,
        }]
      })
      // Auto-select if no agent selected (only for embedded)
      if (event.mode === 'embedded') {
        setSelectedAgent(prev => prev || event.run_id)
      }
    } else if (['agent_completed', 'agent_failed', 'agent_cancelled', 'agent_timeout'].includes(event.event)) {
      // Remove finished agent
      setAgents(prev => prev.filter(a => a.run_id !== event.run_id))
      // Clear selection if this agent was selected
      setSelectedAgent(prev => prev === event.run_id ? null : prev)
    }
  }, [])

  // Send terminal input
  const sendInput = useCallback((runId: string, data: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({
      type: 'terminal_input',
      run_id: runId,
      data,
    }))
  }, [])

  // Register output callback
  const onOutput = useCallback((callback: (runId: string, data: string) => void) => {
    outputCallbackRef.current = callback
  }, [])

  // Connect on mount
  useEffect(() => {
    connect()

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      wsRef.current?.close()
    }
  }, [connect])

  // Reconcile agent list when browser tab becomes visible (catches missed WS events)
  useEffect(() => {
    const handleVisibility = () => {
      if (document.visibilityState === 'visible') {
        refreshAgents()
      }
    }
    document.addEventListener('visibilitychange', handleVisibility)
    return () => document.removeEventListener('visibilitychange', handleVisibility)
  }, [refreshAgents])

  return {
    isConnected,
    agents,
    selectedAgent,
    setSelectedAgent,
    sendInput,
    onOutput,
    refreshAgents,
  }
}
