import { useState, useEffect, useCallback, useRef } from 'react'
import type { ChatMessage, ToolCall } from '../components/Message'

const STORAGE_KEY = 'gobby-chat-history'
const CONVERSATION_ID_KEY = 'gobby-conversation-id'
const MAX_STORED_MESSAGES = 100

// Serialized message format for localStorage
interface StoredMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string // ISO string
  toolCalls?: ToolCall[]
}

function loadMessages(): ChatMessage[] {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored) {
      const parsed: StoredMessage[] = JSON.parse(stored)
      return parsed.map((m) => ({
        ...m,
        timestamp: new Date(m.timestamp),
      }))
    }
  } catch (e) {
    console.error('Failed to load chat history:', e)
  }
  return []
}

function saveMessages(messages: ChatMessage[]): void {
  try {
    // Only keep the last N messages
    const toStore = messages.slice(-MAX_STORED_MESSAGES)
    const serialized: StoredMessage[] = toStore.map((m) => ({
      ...m,
      timestamp: m.timestamp.toISOString(),
    }))
    localStorage.setItem(STORAGE_KEY, JSON.stringify(serialized))
  } catch (e) {
    console.error('Failed to save chat history:', e)
  }
}

interface WebSocketMessage {
  type: string
  [key: string]: unknown
}

interface ChatStreamChunk {
  type: 'chat_stream'
  message_id: string
  content: string
  done: boolean
  tool_calls_count?: number
}

interface ChatError {
  type: 'chat_error'
  message_id?: string
  error: string
}

interface ToolStatusMessage {
  type: 'tool_status'
  message_id: string
  tool_call_id: string
  status: 'calling' | 'completed' | 'error'
  tool_name?: string
  server_name?: string
  arguments?: Record<string, unknown>
  result?: unknown
  error?: string
}

/** crypto.randomUUID() requires a secure context (HTTPS/localhost). Fall back for HTTP access (e.g. Tailscale IP). */
function uuid(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    try { return crypto.randomUUID() } catch { /* non-secure context */ }
  }
  // Fallback using crypto.getRandomValues (works in all contexts)
  const bytes = new Uint8Array(16)
  crypto.getRandomValues(bytes)
  bytes[6] = (bytes[6] & 0x0f) | 0x40 // version 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80 // variant 1
  const hex = Array.from(bytes, b => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`
}

function loadConversationId(): string {
  return localStorage.getItem(CONVERSATION_ID_KEY) || uuid()
}

function saveConversationId(id: string): void {
  localStorage.setItem(CONVERSATION_ID_KEY, id)
}

export function useChat() {
  const [messages, setMessages] = useState<ChatMessage[]>(() => loadMessages())
  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const conversationIdRef = useRef<string>(loadConversationId())

  // Refs for handlers to avoid stale closures in WebSocket callbacks
  const handleChatStreamRef = useRef<(chunk: ChatStreamChunk) => void>(() => {})
  const handleChatErrorRef = useRef<(error: ChatError) => void>(() => {})
  const handleToolStatusRef = useRef<(status: ToolStatusMessage) => void>(() => {})

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    // Determine WebSocket URL based on context:
    // - HTTPS (e.g., Tailscale Serve): use wss:// with /ws path
    // - HTTP dev mode: connect directly to daemon port 60888
    const isSecure = window.location.protocol === 'https:'
    const wsUrl = isSecure
      ? `wss://${window.location.host}/ws`
      : `ws://${window.location.hostname}:60888`

    console.log('Connecting to WebSocket:', wsUrl)
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('WebSocket connected')
      setIsConnected(true)

      // Subscribe to chat events
      ws.send(JSON.stringify({
        type: 'subscribe',
        events: ['chat_stream', 'chat_error', 'tool_status'],
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
        } else if (data.type === 'tool_status') {
          handleToolStatusRef.current(data as unknown as ToolStatusMessage)
        } else if (data.type === 'connection_established') {
          // If the server still has our conversation alive, keep using it.
          // Otherwise our stored ID is fine — the server will create a new session on first message.
          const serverConversations = (data.conversation_ids as string[]) || []
          if (serverConversations.includes(conversationIdRef.current)) {
            console.log('Reconnected to existing conversation:', conversationIdRef.current)
          }
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

  // Handle tool status updates
  const handleToolStatus = useCallback((status: ToolStatusMessage) => {
    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === status.message_id)
      if (idx < 0) return prev

      const updated = [...prev]
      const toolCalls = [...(updated[idx].toolCalls || [])]
      const existingIdx = toolCalls.findIndex((t) => t.id === status.tool_call_id)

      if (existingIdx >= 0) {
        // Merge with existing call to preserve tool_name/server_name from initial "calling" event
        const existing = toolCalls[existingIdx]
        const merged: ToolCall = {
          ...existing,
          status: status.status,
          result: status.result,
          error: status.error,
        }
        toolCalls[existingIdx] = merged
      } else {
        // New tool call - create with all available data
        const newCall: ToolCall = {
          id: status.tool_call_id,
          tool_name: status.tool_name || 'unknown',
          server_name: status.server_name || 'builtin',
          status: status.status,
          arguments: status.arguments,
          result: status.result,
          error: status.error,
        }
        toolCalls.push(newCall)
      }

      updated[idx] = { ...updated[idx], toolCalls }
      return updated
    })
  }, [])

  // Keep refs updated to avoid stale closures
  useEffect(() => {
    handleChatStreamRef.current = handleChatStream
    handleChatErrorRef.current = handleChatError
    handleToolStatusRef.current = handleToolStatus
  }, [handleChatStream, handleChatError, handleToolStatus])

  // Persist messages to localStorage
  useEffect(() => {
    saveMessages(messages)
  }, [messages])

  // Clear chat history
  const clearHistory = useCallback(() => {
    setMessages([])
    localStorage.removeItem(STORAGE_KEY)
    // Start a fresh conversation — new ID so the backend creates a new ChatSession
    conversationIdRef.current = uuid()
    localStorage.removeItem(CONVERSATION_ID_KEY)
  }, [])

  // Stop the current streaming response
  const stopStreaming = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({
      type: 'stop_chat',
      conversation_id: conversationIdRef.current,
    }))
    setIsStreaming(false) // Optimistic update
  }, [])

  // Send a message (allowed even while streaming — cancels the active stream)
  const sendMessage = useCallback((content: string, model?: string | null): boolean => {
    console.log('sendMessage called:', content, 'model:', model)
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not connected, state:', wsRef.current?.readyState)
      return false
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

    // Persist conversation_id on first send
    saveConversationId(conversationIdRef.current)

    // Send to server — backend will cancel any active stream automatically
    const payload: Record<string, unknown> = {
      type: 'chat_message',
      content,
      message_id: messageId,
      conversation_id: conversationIdRef.current,
    }

    // Include model if specified
    if (model) {
      payload.model = model
    }

    console.log('Sending WebSocket message:', payload)
    wsRef.current.send(JSON.stringify(payload))

    setIsStreaming(true)
    return true
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
    stopStreaming,
    clearHistory,
  }
}
