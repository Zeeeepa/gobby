import { useState, useEffect, useCallback, useRef } from 'react'
import type { ChatMessage, ToolCall } from '../components/Message'
import type { QueuedFile } from '../components/ChatInput'

const CONVERSATION_ID_KEY = 'gobby-conversation-id'
const MAX_STORED_MESSAGES = 100

// Per-conversation storage key
function chatStorageKey(conversationId: string): string {
  return `gobby-chat-${conversationId}`
}

// Serialized message format for localStorage
interface StoredMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: string // ISO string
  toolCalls?: ToolCall[]
  thinkingContent?: string
}

function loadMessagesForConversation(conversationId: string): ChatMessage[] {
  try {
    const stored = localStorage.getItem(chatStorageKey(conversationId))
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

function saveMessagesForConversation(conversationId: string, messages: ChatMessage[]): void {
  try {
    const toStore = messages.slice(-MAX_STORED_MESSAGES)
    const serialized: StoredMessage[] = toStore.map((m) => ({
      ...m,
      timestamp: m.timestamp.toISOString(),
    }))
    localStorage.setItem(chatStorageKey(conversationId), JSON.stringify(serialized))
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
  request_id?: string
  content: string
  done: boolean
  tool_calls_count?: number
}

interface ChatError {
  type: 'chat_error'
  message_id?: string
  request_id?: string
  error: string
}

interface ToolStatusMessage {
  type: 'tool_status'
  message_id: string
  request_id?: string
  tool_call_id: string
  status: 'calling' | 'completed' | 'error'
  tool_name?: string
  server_name?: string
  arguments?: Record<string, unknown>
  result?: unknown
  error?: string
}

interface ChatThinkingMessage {
  type: 'chat_thinking'
  message_id: string
  request_id?: string
  conversation_id: string
  content?: string
}

interface ModelSwitchedMessage {
  type: 'model_switched'
  conversation_id: string
  old_model: string
  new_model: string
}

interface ToolResultMessage {
  type: 'tool_result'
  request_id: string
  result: unknown
}

interface ErrorMessage {
  type: 'error'
  request_id?: string
  message: string
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

// Migrate from old single-key storage to per-conversation storage
function migrateOldStorage(conversationId: string): void {
  const OLD_KEY = 'gobby-chat-history'
  try {
    const old = localStorage.getItem(OLD_KEY)
    if (old) {
      localStorage.setItem(chatStorageKey(conversationId), old)
      localStorage.removeItem(OLD_KEY)
      console.log('Migrated old chat history to per-conversation storage')
    }
  } catch (e) {
    console.error('Failed to migrate old chat history:', e)
  }
}

export function useChat() {
  const conversationIdRef = useRef<string>(loadConversationId())
  const [conversationId, setConversationId] = useState<string>(conversationIdRef.current)

  // Run migration once on first load
  const migrated = useRef(false)
  if (!migrated.current) {
    migrateOldStorage(conversationIdRef.current)
    migrated.current = true
  }

  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    loadMessagesForConversation(conversationIdRef.current)
  )
  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isThinking, setIsThinking] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)

  // Track pending command request IDs for tool_result routing
  const pendingCommandsRef = useRef<Map<string, { server: string; tool: string }>>(new Map())

  // Track the active chat request to filter stale stream chunks from cancelled requests
  const activeRequestIdRef = useRef<string | null>(null)

  /** Returns true if the chunk belongs to the currently active request. */
  function isActiveRequest(requestId?: string): boolean {
    return requestId === activeRequestIdRef.current
  }

  // Refs for handlers to avoid stale closures in WebSocket callbacks
  const handleChatStreamRef = useRef<(chunk: ChatStreamChunk) => void>(() => {})
  const handleChatErrorRef = useRef<(error: ChatError) => void>(() => {})
  const handleToolStatusRef = useRef<(status: ToolStatusMessage) => void>(() => {})
  const handleChatThinkingRef = useRef<(msg: ChatThinkingMessage) => void>(() => {})
  const handleModelSwitchedRef = useRef<(msg: ModelSwitchedMessage) => void>(() => {})
  const handleToolResultRef = useRef<(msg: ToolResultMessage) => void>(() => {})
  const handleErrorRef = useRef<(msg: ErrorMessage) => void>(() => {})

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

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

      ws.send(JSON.stringify({
        type: 'subscribe',
        events: ['chat_stream', 'chat_error', 'tool_status', 'chat_thinking'],
      }))
    }

    ws.onclose = () => {
      console.log('WebSocket disconnected')
      setIsConnected(false)
      setIsStreaming(false)
      setIsThinking(false)
      activeRequestIdRef.current = null

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
        } else if (data.type === 'chat_thinking') {
          handleChatThinkingRef.current(data as unknown as ChatThinkingMessage)
        } else if (data.type === 'model_switched') {
          handleModelSwitchedRef.current(data as unknown as ModelSwitchedMessage)
        } else if (data.type === 'tool_result') {
          handleToolResultRef.current(data as unknown as ToolResultMessage)
        } else if (data.type === 'error' && (data as unknown as ErrorMessage).request_id) {
          handleErrorRef.current(data as unknown as ErrorMessage)
        } else if (data.type === 'connection_established') {
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
    if (!isActiveRequest(chunk.request_id)) {
      console.debug('Dropping stale chat_stream chunk, request_id:', chunk.request_id)
      return
    }

    if (chunk.content) {
      setIsThinking(false)
    }

    setMessages((prev) => {
      const existingIndex = prev.findIndex((m) => m.id === chunk.message_id)

      if (existingIndex >= 0) {
        const updated = [...prev]
        updated[existingIndex] = {
          ...updated[existingIndex],
          content: updated[existingIndex].content + chunk.content,
        }
        return updated
      } else {
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
      setIsThinking(false)
    }
  }, [])

  // Handle chat errors
  const handleChatError = useCallback((error: ChatError) => {
    if (!isActiveRequest(error.request_id)) {
      console.debug('Dropping stale chat_error, request_id:', error.request_id)
      return
    }

    setIsStreaming(false)
    setIsThinking(false)
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
    if (!isActiveRequest(status.request_id)) {
      console.debug('Dropping stale tool_status, request_id:', status.request_id)
      return
    }

    if (status.status === 'calling') {
      setIsThinking(false)
    }

    setMessages((prev) => {
      const idx = prev.findIndex((m) => m.id === status.message_id)
      if (idx < 0) return prev

      const updated = [...prev]
      const toolCalls = [...(updated[idx].toolCalls || [])]
      const existingIdx = toolCalls.findIndex((t) => t.id === status.tool_call_id)

      if (existingIdx >= 0) {
        const existing = toolCalls[existingIdx]
        const merged: ToolCall = {
          ...existing,
          status: status.status,
          result: status.result,
          error: status.error,
        }
        toolCalls[existingIdx] = merged
      } else {
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

  // Handle thinking events
  const handleChatThinking = useCallback((msg: ChatThinkingMessage) => {
    if (!isActiveRequest(msg.request_id)) {
      console.debug('Dropping stale chat_thinking, request_id:', msg.request_id)
      return
    }

    setIsThinking(true)
    setMessages((prev) => {
      const existingIndex = prev.findIndex((m) => m.id === msg.message_id)
      if (existingIndex >= 0) {
        const updated = [...prev]
        updated[existingIndex] = {
          ...updated[existingIndex],
          thinkingContent: (updated[existingIndex].thinkingContent || '') + (msg.content || ''),
        }
        return updated
      } else {
        return [...prev, {
          id: msg.message_id,
          role: 'assistant' as const,
          content: '',
          timestamp: new Date(),
          thinkingContent: msg.content || '',
        }]
      }
    })
  }, [])

  // Handle model switch notifications
  const handleModelSwitched = useCallback((msg: ModelSwitchedMessage) => {
    setMessages((prev) => [
      ...prev,
      {
        id: `model-switch-${Date.now()}`,
        role: 'system' as const,
        content: `Model switched from ${msg.old_model} to ${msg.new_model}`,
        timestamp: new Date(),
      },
    ])
  }, [])

  // Handle tool_result for slash commands
  const handleToolResult = useCallback((msg: ToolResultMessage) => {
    const pending = pendingCommandsRef.current.get(msg.request_id)
    if (!pending) return
    pendingCommandsRef.current.delete(msg.request_id)

    const resultStr = typeof msg.result === 'string'
      ? msg.result
      : JSON.stringify(msg.result, null, 2)

    setMessages((prev) => [
      ...prev,
      {
        id: `cmd-result-${msg.request_id}`,
        role: 'system' as const,
        content: `**/${pending.server}.${pending.tool}**\n\`\`\`json\n${resultStr}\n\`\`\``,
        timestamp: new Date(),
      },
    ])
  }, [])

  // Handle error responses for slash commands
  const handleError = useCallback((msg: ErrorMessage) => {
    if (!msg.request_id) return
    const pending = pendingCommandsRef.current.get(msg.request_id)
    if (!pending) return
    pendingCommandsRef.current.delete(msg.request_id)

    setMessages((prev) => [
      ...prev,
      {
        id: `cmd-error-${msg.request_id}`,
        role: 'system' as const,
        content: `Error running /${pending.server}.${pending.tool}: ${msg.message}`,
        timestamp: new Date(),
      },
    ])
  }, [])

  // Keep refs updated to avoid stale closures
  useEffect(() => {
    handleChatStreamRef.current = handleChatStream
    handleChatErrorRef.current = handleChatError
    handleToolStatusRef.current = handleToolStatus
    handleChatThinkingRef.current = handleChatThinking
    handleModelSwitchedRef.current = handleModelSwitched
    handleToolResultRef.current = handleToolResult
    handleErrorRef.current = handleError
  }, [handleChatStream, handleChatError, handleToolStatus, handleChatThinking, handleModelSwitched, handleToolResult, handleError])

  // Persist messages to localStorage (per-conversation)
  useEffect(() => {
    saveMessagesForConversation(conversationIdRef.current, messages)
  }, [messages])

  // Switch to a different conversation
  const switchConversation = useCallback((id: string) => {
    // Save current conversation's messages before switching
    saveMessagesForConversation(conversationIdRef.current, messages)

    conversationIdRef.current = id
    setConversationId(id)
    saveConversationId(id)

    // Load messages for the target conversation
    const loaded = loadMessagesForConversation(id)
    setMessages(loaded)

    // Reset streaming state
    activeRequestIdRef.current = null
    setIsStreaming(false)
    setIsThinking(false)
  }, [messages])

  // Start a new chat conversation
  const startNewChat = useCallback(() => {
    // Save current messages before switching
    saveMessagesForConversation(conversationIdRef.current, messages)

    const newId = uuid()
    conversationIdRef.current = newId
    setConversationId(newId)
    saveConversationId(newId)
    setMessages([])

    activeRequestIdRef.current = null
    setIsStreaming(false)
    setIsThinking(false)
  }, [messages])

  // Resume a CLI session (e.g., Claude) — sets the conversation ID
  // so the next message triggers server-side resume
  const resumeSession = useCallback((externalId: string) => {
    saveMessagesForConversation(conversationIdRef.current, messages)

    conversationIdRef.current = externalId
    setConversationId(externalId)
    saveConversationId(externalId)

    // Load any existing messages for this conversation (may be empty for CLI sessions)
    const loaded = loadMessagesForConversation(externalId)
    setMessages(loaded.length > 0 ? loaded : [{
      id: `system-resume-${Date.now()}`,
      role: 'system' as const,
      content: 'Resuming session. Send a message to continue.',
      timestamp: new Date(),
    }])

    activeRequestIdRef.current = null
    setIsStreaming(false)
    setIsThinking(false)
  }, [messages])

  // Clear chat history
  const clearHistory = useCallback(() => {
    setMessages([])
    localStorage.removeItem(chatStorageKey(conversationIdRef.current))
    activeRequestIdRef.current = null
    // Start a fresh conversation
    const newId = uuid()
    conversationIdRef.current = newId
    setConversationId(newId)
    localStorage.removeItem(CONVERSATION_ID_KEY)
  }, [])

  // Stop the current streaming response
  const stopStreaming = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({
      type: 'stop_chat',
      conversation_id: conversationIdRef.current,
    }))
    activeRequestIdRef.current = null
    setIsStreaming(false)
    setIsThinking(false)
  }, [])

  // Send a message (allowed even while streaming — cancels the active stream)
  const sendMessage = useCallback((content: string, model?: string | null, files?: QueuedFile[], projectId?: string | null): boolean => {
    console.log('sendMessage called:', content, 'model:', model, 'files:', files?.length)
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) {
      console.error('WebSocket not connected, state:', wsRef.current?.readyState)
      return false
    }

    const messageId = `user-${uuid()}`
    const requestId = uuid()
    activeRequestIdRef.current = requestId

    setMessages((prev) => [
      ...prev,
      {
        id: messageId,
        role: 'user',
        content,
        timestamp: new Date(),
      },
    ])

    saveConversationId(conversationIdRef.current)

    const payload: Record<string, unknown> = {
      type: 'chat_message',
      content,
      message_id: messageId,
      conversation_id: conversationIdRef.current,
      request_id: requestId,
    }

    if (model) {
      payload.model = model
    }

    if (projectId) {
      payload.project_id = projectId
    }

    if (files && files.length > 0) {
      const contentBlocks: Array<Record<string, unknown>> = []
      for (const qf of files) {
        if (qf.file.type.startsWith('image/') && qf.base64) {
          contentBlocks.push({
            type: 'image',
            source: {
              type: 'base64',
              media_type: qf.file.type,
              data: qf.base64,
            },
          })
        } else if (qf.base64) {
          contentBlocks.push({
            type: 'text',
            text: `[File: ${qf.file.name}]\n${atob(qf.base64)}`,
          })
        }
      }
      if (content) {
        contentBlocks.push({ type: 'text', text: content })
      }
      payload.content_blocks = contentBlocks
    }

    console.log('Sending WebSocket message:', payload)
    wsRef.current.send(JSON.stringify(payload))

    setIsStreaming(true)
    setIsThinking(true)
    return true
  }, [])

  // Execute a slash command directly (no LLM round-trip)
  const executeCommand = useCallback((server: string, tool: string, args: Record<string, string> = {}) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return

    const requestId = uuid()

    pendingCommandsRef.current.set(requestId, { server, tool })

    setMessages((prev) => [
      ...prev,
      {
        id: `cmd-${requestId}`,
        role: 'user' as const,
        content: `/${server}.${tool}${Object.keys(args).length ? ' ' + Object.entries(args).map(([k, v]) => `${k}=${v}`).join(' ') : ''}`,
        timestamp: new Date(),
      },
    ])

    wsRef.current.send(JSON.stringify({
      type: 'tool_call',
      request_id: requestId,
      mcp: server,
      tool,
      args,
    }))
  }, [])

  // Respond to an AskUserQuestion pending in the backend
  const respondToQuestion = useCallback((toolCallId: string, answers: Record<string, string>) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({
      type: 'ask_user_response',
      conversation_id: conversationIdRef.current,
      tool_call_id: toolCallId,
      answers,
    }))
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
    conversationId,
    isConnected,
    isStreaming,
    isThinking,
    sendMessage,
    stopStreaming,
    clearHistory,
    executeCommand,
    respondToQuestion,
    switchConversation,
    startNewChat,
    resumeSession,
  }
}
