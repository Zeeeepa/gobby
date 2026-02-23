import { useState, useEffect, useCallback, useRef } from 'react'
import type { ChatMessage, ToolCall, ChatMode } from '../types/chat'
import type { QueuedFile } from '../types/chat'

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
  session_ref?: string
  sdk_session_id?: string
  usage?: {
    input_tokens: number
    output_tokens: number
    cache_read_input_tokens?: number
    cache_creation_input_tokens?: number
    total_input_tokens?: number
  }
  context_window?: number
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
  status: 'calling' | 'completed' | 'error' | 'pending_approval'
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

interface VoiceTranscriptionMessage {
  type: 'voice_transcription'
  text: string
  request_id: string
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
  useEffect(() => {
    migrateOldStorage(conversationIdRef.current)
  }, [])

  const [messages, setMessages] = useState<ChatMessage[]>(() =>
    loadMessagesForConversation(conversationIdRef.current)
  )
  const messagesRef = useRef(messages)
  messagesRef.current = messages
  const [isConnected, setIsConnected] = useState(false)
  const [isStreaming, setIsStreaming] = useState(false)
  const [isThinking, setIsThinking] = useState(false)

  // Session ref tracking (e.g. "#158")
  const [sessionRef, setSessionRef] = useState<string | null>(null)

  // Branch/worktree tracking
  const [currentBranch, setCurrentBranch] = useState<string | null>(null)
  const [worktreePath, setWorktreePath] = useState<string | null>(null)

  // Plan mode approval tracking
  const [planPendingApproval, setPlanPendingApproval] = useState(false)
  const currentModeRef = useRef<ChatMode>('accept_edits')

  // Callback for backend-initiated mode changes (e.g. agent EnterPlanMode)
  const onModeChangedRef = useRef<((mode: ChatMode) => void) | null>(null)
  const setOnModeChanged = useCallback((fn: (mode: ChatMode) => void) => {
    onModeChangedRef.current = fn
  }, [])

  // Context usage tracking — accumulated across turns.
  // totalInputTokens = uncached + cacheRead + cacheCreation (the real context size).
  const [contextUsage, setContextUsage] = useState<{
    totalInputTokens: number
    outputTokens: number
    contextWindow: number | null
    // Per-category breakdown for tooltip
    uncachedInputTokens: number
    cacheReadTokens: number
    cacheCreationTokens: number
  }>({ totalInputTokens: 0, outputTokens: 0, contextWindow: null, uncachedInputTokens: 0, cacheReadTokens: 0, cacheCreationTokens: 0 })
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
  const handleVoiceMessageRef = useRef<(data: Record<string, unknown>) => void>(() => {})

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const wsUrl = `${wsProtocol}//${window.location.host}/ws`

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
        } else if (data.type === 'voice_transcription' || data.type === 'voice_audio_chunk' || data.type === 'voice_status') {
          // When STT transcription arrives, inject it as a user message and
          // register the request_id so the assistant's response stream is accepted.
          if (data.type === 'voice_transcription') {
            const voiceMsg = data as unknown as VoiceTranscriptionMessage
            const text = typeof voiceMsg.text === 'string' ? voiceMsg.text : ''
            const reqId = typeof voiceMsg.request_id === 'string' ? voiceMsg.request_id : ''
            if (text && reqId) {
              activeRequestIdRef.current = reqId
              setMessages((prev) => [
                ...prev,
                {
                  id: `user-voice-${reqId}`,
                  role: 'user' as const,
                  content: text,
                  timestamp: new Date(),
                },
              ])
              setIsStreaming(true)
              setIsThinking(true)
            }
          }
          handleVoiceMessageRef.current(data as Record<string, unknown>)
        } else if (data.type === 'mode_changed') {
          const newMode = (data as Record<string, unknown>).mode as ChatMode | undefined
          if (newMode) {
            currentModeRef.current = newMode
            setPlanPendingApproval(false)
            onModeChangedRef.current?.(newMode)
          }
        } else if (data.type === 'session_info') {
          const info = data as Record<string, unknown>
          const ref = info.session_ref as string | undefined
          if (ref) setSessionRef(ref)
          const branch = info.current_branch as string | undefined
          if (branch !== undefined) setCurrentBranch(branch)
          const wtPath = info.worktree_path as string | undefined
          if (wtPath !== undefined) setWorktreePath(wtPath)
        } else if (data.type === 'worktree_switched') {
          const wt = data as Record<string, unknown>
          setCurrentBranch((wt.new_branch as string) ?? null)
          setWorktreePath((wt.worktree_path as string) ?? null)
        } else if (data.type === 'session_continued') {
          console.log('Session continued:', data)
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
      // Show plan approval UI if we just finished streaming in plan mode
      if (currentModeRef.current === 'plan') {
        setPlanPendingApproval(true)
      }
      // Pick up session_ref from done message (fallback if session_info was missed)
      if (chunk.session_ref) {
        setSessionRef(chunk.session_ref)
      }
      // Adopt SDK session_id as the canonical conversation ID
      if (chunk.sdk_session_id && chunk.sdk_session_id !== conversationIdRef.current) {
        conversationIdRef.current = chunk.sdk_session_id
        setConversationId(chunk.sdk_session_id)
        saveConversationId(chunk.sdk_session_id)
      }
      // Update context usage from usage data in done message.
      // Each turn sends the full conversation to Claude, so the latest turn's
      // total_input_tokens IS the current context size — replace, don't accumulate.
      // Output tokens are genuinely incremental, so those accumulate.
      if (chunk.usage) {
        const u = chunk.usage
        // Prefer total_input_tokens from backend; fall back to sum of parts
        const turnTotal = u.total_input_tokens
          ?? ((u.input_tokens ?? 0) + (u.cache_read_input_tokens ?? 0) + (u.cache_creation_input_tokens ?? 0))
        setContextUsage((prev) => ({
          // Input tokens: REPLACE with latest turn's values (each turn sends
          // the full conversation, so the latest total IS the current context size)
          totalInputTokens: turnTotal,
          uncachedInputTokens: u.input_tokens ?? 0,
          cacheReadTokens: u.cache_read_input_tokens ?? 0,
          cacheCreationTokens: u.cache_creation_input_tokens ?? 0,
          // Output tokens: ACCUMULATE (genuinely incremental per turn)
          outputTokens: prev.outputTokens + (u.output_tokens ?? 0),
          contextWindow: chunk.context_window ?? prev.contextWindow,
        }))
      } else if (chunk.context_window) {
        setContextUsage((prev) => ({ ...prev, contextWindow: chunk.context_window ?? prev.contextWindow }))
      }
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
      if (idx < 0) {
        // Tool status arrived before any text/thinking — create the message
        const newCall: ToolCall = {
          id: status.tool_call_id,
          tool_name: status.tool_name || 'unknown',
          server_name: status.server_name || 'builtin',
          status: status.status,
          arguments: status.arguments,
          result: status.result,
          error: status.error,
        }
        return [...prev, {
          id: status.message_id,
          role: 'assistant' as const,
          content: '',
          timestamp: new Date(),
          toolCalls: [newCall],
        }]
      }

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
  const switchConversation = useCallback((id: string, dbSessionId?: string) => {
    if (!id) return
    // Skip if already on this conversation with messages loaded
    if (id === conversationIdRef.current && messagesRef.current.length > 0 && !dbSessionId) return

    // Stop partial streaming first
    activeRequestIdRef.current = null
    setIsStreaming(false)
    setIsThinking(false)
    setSessionRef(null)
    setCurrentBranch(null)
    setWorktreePath(null)
    setContextUsage({ totalInputTokens: 0, outputTokens: 0, contextWindow: null, uncachedInputTokens: 0, cacheReadTokens: 0, cacheCreationTokens: 0 })

    // Save current conversation's messages before switching (explicit save)
    if (conversationIdRef.current) {
      saveMessagesForConversation(conversationIdRef.current, messagesRef.current)
    }

    conversationIdRef.current = id
    setConversationId(id)
    saveConversationId(id)

    // Load cached messages for instant display (no flash)
    const cached = loadMessagesForConversation(id)
    if (cached.length > 0) {
      setMessages(cached)
    }

    // Always fetch from server when dbSessionId is available (replaces stale cache)
    if (dbSessionId) {
      if (cached.length === 0) setMessages([])
      const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
      fetch(`${baseUrl}/sessions/${dbSessionId}/messages?limit=100&offset=0`)
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          if (!data?.messages?.length || conversationIdRef.current !== id) return
          const mapped: ChatMessage[] = data.messages
            .filter((m: { role: string }) => m.role === 'user' || m.role === 'assistant')
            .map((m: { id: string; role: string; content: string; timestamp: string; message_index?: number }, i: number) => ({
              id: m.id || `msg-${m.message_index ?? i}`,
              role: m.role as 'user' | 'assistant',
              content: m.content,
              timestamp: new Date(m.timestamp),
            }))
          if (mapped.length > 0) {
            setMessages(mapped)
            saveMessagesForConversation(id, mapped)
          }
        })
        .catch(err => console.error('Failed to fetch session messages:', err))

      // Hydrate context usage from persisted session data
      fetch(`${baseUrl}/sessions/${dbSessionId}`)
        .then(res => res.ok ? res.json() : null)
        .then(data => {
          const s = data?.session
          if (!s || conversationIdRef.current !== id) return
          if (s.usage_input_tokens > 0 || s.usage_output_tokens > 0 || s.context_window) {
            const totalIn = s.usage_input_tokens ?? 0
            const cacheRead = s.usage_cache_read_tokens ?? 0
            const cacheCreation = s.usage_cache_creation_tokens ?? 0
            setContextUsage({
              totalInputTokens: totalIn,
              outputTokens: s.usage_output_tokens ?? 0,
              contextWindow: s.context_window ?? null,
              uncachedInputTokens: totalIn - cacheRead - cacheCreation,
              cacheReadTokens: cacheRead,
              cacheCreationTokens: cacheCreation,
            })
          }
        })
        .catch(() => {})
    } else if (cached.length === 0) {
      setMessages([])
    }
  }, [])

  // Start a new chat conversation
  const startNewChat = useCallback(() => {
    // Save current messages before switching
    saveMessagesForConversation(conversationIdRef.current, messagesRef.current)

    const newId = uuid()
    conversationIdRef.current = newId
    setConversationId(newId)
    saveConversationId(newId)
    setMessages([])
    setSessionRef(null)
    setCurrentBranch(null)
    setWorktreePath(null)
    setContextUsage({ totalInputTokens: 0, outputTokens: 0, contextWindow: null, uncachedInputTokens: 0, cacheReadTokens: 0, cacheCreationTokens: 0 })

    activeRequestIdRef.current = null
    setIsStreaming(false)
    setIsThinking(false)
  }, [])

  // Resume a CLI session (e.g., Claude) — sets the conversation ID
  // so the next message triggers server-side resume
  const resumeSession = useCallback((externalId: string) => {
    saveMessagesForConversation(conversationIdRef.current, messagesRef.current)

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
  }, [])

  // Continue a CLI/external session in the web chat UI with full history
  const continueSessionInChat = useCallback(async (
    sourceDbSessionId: string,
    projectId?: string,
  ): Promise<string> => {
    const newConversationId = uuid()

    // Save current conversation, switch to new one
    saveMessagesForConversation(conversationIdRef.current, messagesRef.current)
    conversationIdRef.current = newConversationId
    setConversationId(newConversationId)
    saveConversationId(newConversationId)
    activeRequestIdRef.current = null
    setIsStreaming(false)
    setIsThinking(false)
    setMessages([])

    // Fetch source session's messages for display
    const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
    try {
      const res = await fetch(`${baseUrl}/sessions/${sourceDbSessionId}/messages?limit=100`)
      if (res.ok) {
        const data = await res.json()
        const mapped: ChatMessage[] = (data.messages || [])
          .filter((m: { role: string }) => m.role === 'user' || m.role === 'assistant')
          .map((m: { id?: string; role: string; content: string; timestamp: string; message_index?: number }, i: number) => ({
            id: m.id || `history-${i}`,
            role: m.role as 'user' | 'assistant',
            content: m.content,
            timestamp: new Date(m.timestamp),
          }))
        if (mapped.length > 0) {
          setMessages(mapped)
          saveMessagesForConversation(newConversationId, mapped)
        }
      }
    } catch (err) {
      console.error('Failed to fetch source session messages:', err)
    }

    // Hydrate context usage from source session
    try {
      const sessionRes = await fetch(`${baseUrl}/sessions/${sourceDbSessionId}`)
      if (sessionRes.ok) {
        const sessionData = await sessionRes.json()
        const s = sessionData?.session
        if (s && (s.usage_input_tokens > 0 || s.usage_output_tokens > 0 || s.context_window)) {
          const totalIn = s.usage_input_tokens ?? 0
          const cacheRead = s.usage_cache_read_tokens ?? 0
          const cacheCreation = s.usage_cache_creation_tokens ?? 0
          setContextUsage({
            totalInputTokens: totalIn,
            outputTokens: s.usage_output_tokens ?? 0,
            contextWindow: s.context_window ?? null,
            uncachedInputTokens: totalIn - cacheRead - cacheCreation,
            cacheReadTokens: cacheRead,
            cacheCreationTokens: cacheCreation,
          })
        }
      }
    } catch {
      // Best-effort — don't block continuation
    }

    // Tell backend to prepare the continuation session
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'continue_in_chat',
        conversation_id: newConversationId,
        source_session_id: sourceDbSessionId,
        project_id: projectId,
      }))
    }

    return newConversationId
  }, [])

  // Clear chat history — notifies backend to teardown session, then resets frontend
  const clearHistory = useCallback(() => {
    const oldConversationId = conversationIdRef.current
    // Notify backend to generate summary + teardown session
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'clear_chat',
        conversation_id: oldConversationId,
      }))
    }
    // Reset frontend state
    setMessages([])
    setContextUsage({ totalInputTokens: 0, outputTokens: 0, contextWindow: null, uncachedInputTokens: 0, cacheReadTokens: 0, cacheCreationTokens: 0 })
    localStorage.removeItem(chatStorageKey(oldConversationId))
    activeRequestIdRef.current = null
    // Start a fresh conversation
    const newId = uuid()
    conversationIdRef.current = newId
    setConversationId(newId)
    saveConversationId(newId)
  }, [])

  // Delete a conversation from backend and clean up local state
  const deleteConversation = useCallback((id: string, sessionId?: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      const payload: Record<string, unknown> = {
        type: 'delete_chat',
        conversation_id: id,
      }
      if (sessionId !== undefined) {
        payload.session_id = sessionId
      }
      wsRef.current.send(JSON.stringify(payload))
    }
    localStorage.removeItem(chatStorageKey(id))
    // If deleting the active conversation, start a new one
    if (id === conversationIdRef.current) {
      const newId = uuid()
      conversationIdRef.current = newId
      setConversationId(newId)
      saveConversationId(newId)
      setMessages([])
      activeRequestIdRef.current = null
      setIsStreaming(false)
      setIsThinking(false)
    }
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

  // Send mode change to backend
  const sendMode = useCallback((mode: ChatMode) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    currentModeRef.current = mode
    setPlanPendingApproval(false)
    wsRef.current.send(JSON.stringify({
      type: 'set_mode',
      mode,
      conversation_id: conversationIdRef.current,
    }))
  }, [])

  // Notify backend that the project changed — stops the CLI subprocess
  // so the next chat_message recreates it with the correct CWD.
  const sendProjectChange = useCallback((projectId: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({
      type: 'set_project',
      project_id: projectId,
      conversation_id: conversationIdRef.current,
    }))
  }, [])

  // Notify backend that the worktree changed — stops the CLI subprocess
  // so the next chat_message recreates it with the correct CWD.
  const sendWorktreeChange = useCallback((worktreePath: string, worktreeId?: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({
      type: 'set_worktree',
      worktree_path: worktreePath,
      worktree_id: worktreeId,
      conversation_id: conversationIdRef.current,
    }))
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

  // Respond to a tool approval request
  const respondToApproval = useCallback((toolCallId: string, decision: 'approve' | 'reject' | 'approve_always') => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({
      type: 'tool_approval_response',
      conversation_id: conversationIdRef.current,
      tool_call_id: toolCallId,
      decision,
    }))
  }, [])

  // Approve the current plan — tells backend to unlock write tools
  const approvePlan = useCallback(() => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({
      type: 'plan_approval_response',
      conversation_id: conversationIdRef.current,
      decision: 'approve',
    }))
    setPlanPendingApproval(false)
  }, [])

  // Request changes to the plan with feedback
  const requestPlanChanges = useCallback((feedback: string) => {
    if (!wsRef.current || wsRef.current.readyState !== WebSocket.OPEN) return
    wsRef.current.send(JSON.stringify({
      type: 'plan_approval_response',
      conversation_id: conversationIdRef.current,
      decision: 'request_changes',
      feedback,
    }))
    setPlanPendingApproval(false)
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
    sessionRef,
    currentBranch,
    worktreePath,
    isConnected,
    isStreaming,
    isThinking,
    contextUsage,
    sendMessage,
    sendMode,
    sendProjectChange,
    sendWorktreeChange,
    stopStreaming,
    clearHistory,
    deleteConversation,
    executeCommand,
    respondToQuestion,
    respondToApproval,
    planPendingApproval,
    approvePlan,
    requestPlanChanges,
    switchConversation,
    startNewChat,
    resumeSession,
    continueSessionInChat,
    setOnModeChanged,
    wsRef,
    handleVoiceMessageRef,
  }
}
