import { useState, useEffect, useCallback, useRef } from 'react'

export interface TmuxSession {
  name: string
  socket: string
  pane_pid: number | null
  pane_title: string | null
  window_name: string | null
  agent_managed: boolean
  agent_run_id: string | null
  attached_bridge: string | null
}

interface TmuxSessionsResult {
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

export function useTmuxSessions(): TmuxSessionsResult {
  const [sessions, setSessions] = useState<TmuxSession[]>([])
  const [attachedSession, setAttachedSession] = useState<string | null>(null)
  const [streamingId, setStreamingId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const outputCallbackRef = useRef<((runId: string, data: string) => void) | null>(null)

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const isSecure = window.location.protocol === 'https:'
    const wsUrl = isSecure
      ? `wss://${window.location.host}/ws`
      : `ws://${window.location.host}/ws`

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      ws.send(JSON.stringify({
        type: 'subscribe',
        events: ['terminal_output', 'tmux_session_event'],
      }))
      // Fetch session list on connect
      ws.send(JSON.stringify({ type: 'tmux_list_sessions', request_id: 'init' }))
    }

    ws.onclose = () => {
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect()
      }, 2000)
    }

    ws.onerror = (error) => {
      console.error('Tmux WebSocket error:', error)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        handleMessage(data)
      } catch (e) {
        console.error('Failed to parse tmux message:', e)
      }
    }
  }, [])

  const handleMessage = useCallback((data: Record<string, unknown>) => {
    switch (data.type) {
      case 'tmux_sessions_list':
        setSessions(data.sessions as TmuxSession[])
        setIsLoading(false)
        break

      case 'tmux_attach_result':
        if (data.success) {
          setStreamingId(data.streaming_id as string)
          setAttachedSession(data.session_name as string)
        }
        setIsLoading(false)
        break

      case 'tmux_detach_result':
        if (data.success) {
          setStreamingId(null)
          setAttachedSession(null)
        }
        setIsLoading(false)
        break

      case 'tmux_create_result':
        if (data.success) {
          refreshSessions()
        }
        setIsLoading(false)
        break

      case 'tmux_kill_result':
        refreshSessions()
        setIsLoading(false)
        break

      case 'tmux_session_event':
        // Refresh on any session lifecycle change
        refreshSessions()
        break

      case 'terminal_output':
        if (outputCallbackRef.current) {
          outputCallbackRef.current(data.run_id as string, data.data as string)
        }
        break
    }
  }, [])

  const refreshSessions = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({
      type: 'tmux_list_sessions',
      request_id: `refresh-${Date.now()}`,
    }))
  }, [])

  const attachSession = useCallback((sessionName: string, socket: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setIsLoading(true)
    wsRef.current.send(JSON.stringify({
      type: 'tmux_attach',
      request_id: `attach-${Date.now()}`,
      session_name: sessionName,
      socket,
    }))
  }, [])

  const detachSession = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || !streamingId) return
    setIsLoading(true)
    wsRef.current.send(JSON.stringify({
      type: 'tmux_detach',
      request_id: `detach-${Date.now()}`,
      streaming_id: streamingId,
    }))
  }, [streamingId])

  const createSession = useCallback((name?: string, socket?: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setIsLoading(true)
    wsRef.current.send(JSON.stringify({
      type: 'tmux_create_session',
      request_id: `create-${Date.now()}`,
      name,
      socket: socket || 'default',
    }))
  }, [])

  const killSession = useCallback((sessionName: string, socket: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    setIsLoading(true)
    if (sessionName === attachedSession) {
      setStreamingId(null)
      setAttachedSession(null)
    }
    wsRef.current.send(JSON.stringify({
      type: 'tmux_kill_session',
      request_id: `kill-${Date.now()}`,
      session_name: sessionName,
      socket,
    }))
  }, [attachedSession])

  const sendInput = useCallback((data: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || !streamingId) return
    wsRef.current.send(JSON.stringify({
      type: 'terminal_input',
      run_id: streamingId,
      data,
    }))
  }, [streamingId])

  const resizeTerminal = useCallback((rows: number, cols: number) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN || !streamingId) return
    wsRef.current.send(JSON.stringify({
      type: 'tmux_resize',
      streaming_id: streamingId,
      rows,
      cols,
    }))
  }, [streamingId])

  const onOutput = useCallback((callback: (runId: string, data: string) => void) => {
    outputCallbackRef.current = callback
  }, [])

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
  }
}
