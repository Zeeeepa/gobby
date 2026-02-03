import { useState, useEffect, useCallback, useRef } from 'react'

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
}

export interface RunningAgent {
  run_id: string
  session_id: string
  parent_session_id: string
  mode: string
  provider: string
  pid?: number
}

export function useTerminal() {
  const [isConnected, setIsConnected] = useState(false)
  const [agents, setAgents] = useState<RunningAgent[]>([])
  const [selectedAgent, setSelectedAgent] = useState<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const outputCallbackRef = useRef<((runId: string, data: string) => void) | null>(null)

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
    if (event.event === 'agent_started' && event.mode === 'embedded') {
      // Add new embedded agent
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
        }]
      })
      // Auto-select if no agent selected
      setSelectedAgent(prev => prev || event.run_id)
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

  return {
    isConnected,
    agents,
    selectedAgent,
    setSelectedAgent,
    sendInput,
    onOutput,
  }
}
