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

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    // Use relative path - Vite will proxy to the daemon
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${protocol}//${window.location.host}/ws`

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

        if (data.type === 'chat_stream') {
          handleChatStream(data as unknown as ChatStreamChunk)
        } else if (data.type === 'chat_error') {
          handleChatError(data as unknown as ChatError)
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

  // Send a message
  const sendMessage = useCallback((content: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not connected')
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
    wsRef.current.send(
      JSON.stringify({
        type: 'chat_message',
        content,
        message_id: messageId,
      })
    )

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
