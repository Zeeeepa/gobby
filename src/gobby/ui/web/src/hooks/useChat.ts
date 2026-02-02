import { useState, useEffect, useCallback, useRef } from 'react'
import type { ChatMessage } from '../components/Message'

interface WebSocketMessage {
  type: string
  [key: string]: unknown
}

interface ChatStreamChunk {
  type: 'chat_stream'
  message_id: string
  content: string
  done: boolean
}

interface ChatError {
  type: 'chat_error'
  message_id?: string
  error: string
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)

  // Refs for handlers to avoid stale closures in WebSocket callbacks
  const handleChatStreamRef = useRef<(chunk: ChatStreamChunk) => void>(() => {})
  const handleChatErrorRef = useRef<(error: ChatError) => void>(() => {})

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    // In development, connect directly to daemon WebSocket port
    // In production, use relative path through reverse proxy
    const isDev = import.meta.env.DEV
    const wsUrl = isDev
      ? 'ws://localhost:60888'
      : `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws`

    console.log('Connecting to WebSocket:', wsUrl)
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('WebSocket connected')
      setIsConnected(true)

      // Subscribe to chat events
      ws.send(JSON.stringify({
        type: 'subscribe',
        events: ['chat_stream', 'chat_error'],
      }))
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
      setIsConnected(false)
      setIsStreaming(false)

      // Reconnect after 2 seconds
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect()
      }, 2000)
    }

    ws.onerror = (error) => {
      console.error('WebSocket error:', error)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data) as WebSocketMessage
        console.log('WebSocket message:', data.type, data)

        if (data.type === 'chat_stream') {
          handleChatStreamRef.current(data as unknown as ChatStreamChunk)
        } else if (data.type === 'chat_error') {
          handleChatErrorRef.current(data as unknown as ChatError)
        } else if (data.type === 'connection_established') {
          console.log('Connection established:', data)
        } else if (data.type === 'subscribe_success') {
          console.log('Subscribed to events:', data)
        }
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e)
      }
    }
  }, [])

  // Handle streaming chat chunks
  const handleChatStream = useCallback((chunk: ChatStreamChunk) => {
    setMessages((prev) => {
      const existingIndex = prev.findIndex((m) => m.id === chunk.message_id)

      if (existingIndex >= 0) {
        // Update existing message
        const updated = [...prev]
        updated[existingIndex] = {
          ...updated[existingIndex],
          content: updated[existingIndex].content + chunk.content,
        }
        return updated
      } else {
        // New assistant message
        return [
          ...prev,
          {
            id: chunk.message_id,
            role: 'assistant' as const,
            content: chunk.content,
            timestamp: new Date(),
          },
        ]
      }
    })

    if (chunk.done) {
      setIsStreaming(false)
    }
  }, [])

  // Handle chat errors
  const handleChatError = useCallback((error: ChatError) => {
    setIsStreaming(false)
    setMessages((prev) => [
      ...prev,
      {
        id: error.message_id || `error-${Date.now()}`,
        role: 'system' as const,
        content: `Error: ${error.error}`,
        timestamp: new Date(),
      },
    ])
  }, [])

  // Keep refs updated to avoid stale closures
  useEffect(() => {
    handleChatStreamRef.current = handleChatStream
    handleChatErrorRef.current = handleChatError
  }, [handleChatStream, handleChatError])

  // Send a message
  const sendMessage = useCallback((content: string) => {
    console.log('sendMessage called:', content)
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not connected, state:', wsRef.current?.readyState)
      return
    }

    const messageId = `user-${Date.now()}`

    // Add user message to state
    setMessages((prev) => [
      ...prev,
      {
        id: messageId,
        role: 'user',
        content,
        timestamp: new Date(),
      },
    ])

    // Send to server
    const payload = {
      type: 'chat_message',
      content,
      message_id: messageId,
    }
    console.log('Sending WebSocket message:', payload)
    wsRef.current.send(JSON.stringify(payload))

    setIsStreaming(true)
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
    messages,
    isConnected,
    isStreaming,
    sendMessage,
  }
}
