import { useState, useEffect, useCallback, useRef } from 'react'
import type { GobbySession } from './useSessions'
import { useWebSocketEvent } from './useWebSocketEvent'
import type { ContentBlock, TokenUsage } from '../types/chat'

export interface SessionMessage {
  id: string
  role: string
  content: string
  content_type?: string
  tool_name?: string
  tool_input?: string
  tool_result?: string
  tool_use_id?: string
  timestamp: string
  message_index?: number
  content_blocks?: ContentBlock[]
  model?: string | null
  usage?: TokenUsage | null
}

function getBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || ''
}

export function useSessionDetail(sessionId: string | null) {
  const [session, setSession] = useState<GobbySession | null>(null)
  const [messages, setMessages] = useState<SessionMessage[]>([])
  const [totalMessages, setTotalMessages] = useState(0)
  const [isLoading, setIsLoading] = useState(false)

  // Fetch session detail and all messages
  useEffect(() => {
    if (!sessionId) {
      setSession(null)
      setMessages([])
      setTotalMessages(0)
      return
    }

    let cancelled = false
    setIsLoading(true)

    async function fetchDetail() {
      const baseUrl = getBaseUrl()
      try {
        const [sessionRes, messagesRes] = await Promise.all([
          fetch(`${baseUrl}/api/sessions/${sessionId}`),
          fetch(`${baseUrl}/api/sessions/${sessionId}/messages?limit=10000&offset=0`),
        ])

        if (cancelled) return

        if (sessionRes.ok) {
          const data = await sessionRes.json()
          setSession(data.session || null)
        } else {
          console.warn(`Session fetch returned ${sessionRes.status}`)
        }

        if (messagesRes.ok) {
          const data = await messagesRes.json()
          const rawMessages = data.messages || []
          // Map RenderedMessage shape: content_blocks, model, usage are top-level
          const mapped: SessionMessage[] = rawMessages.map((m: Record<string, unknown>) => ({
            id: String(m.id ?? m.message_index ?? `hist-${Math.random()}`),
            role: (m.role as string) ?? 'assistant',
            content: (m.content as string) ?? '',
            timestamp: (m.timestamp as string) ?? '',
            content_blocks: m.content_blocks as ContentBlock[] | undefined,
            model: m.model as string | null | undefined,
            usage: m.usage as TokenUsage | null | undefined,
            // Legacy fields (may be absent in new shape)
            content_type: m.content_type as string | undefined,
            tool_name: m.tool_name as string | undefined,
            message_index: m.message_index as number | undefined,
          }))
          setMessages(mapped)
          setTotalMessages(data.total_count || mapped.length)
        } else {
          console.warn(`Messages fetch returned ${messagesRes.status}`)
        }
      } catch (e) {
        console.error('Failed to fetch session detail:', e)
      } finally {
        if (!cancelled) setIsLoading(false)
      }
    }

    fetchDetail()
    return () => { cancelled = true }
  }, [sessionId])

  // Track current sessionId in a ref for the WebSocket handler
  const sessionIdRef = useRef(sessionId)
  sessionIdRef.current = sessionId

  // Subscribe to real-time session_message events via WebSocket
  // Broadcasts are now RenderedMessage-shaped with content_blocks.
  // Uses upsert semantics: replace existing message with same ID, append if new.
  useWebSocketEvent('session_message', useCallback((data: Record<string, unknown>) => {
    const msgSessionId = data.session_id as string | undefined
    if (!msgSessionId || msgSessionId !== sessionIdRef.current) return

    const msg = data.message as Record<string, unknown> | undefined
    if (!msg) return

    const newMessage: SessionMessage = {
      id: String(msg.id ?? msg.index ?? `ws-${Date.now()}`),
      role: (msg.role as string) ?? 'assistant',
      content: (msg.content as string) ?? '',
      timestamp: (msg.timestamp as string) ?? new Date().toISOString(),
      content_blocks: msg.content_blocks as ContentBlock[] | undefined,
      model: msg.model as string | null | undefined,
      usage: msg.usage as TokenUsage | null | undefined,
    }

    setMessages((prev) => {
      const existingIdx = prev.findIndex((m) => m.id === newMessage.id)
      if (existingIdx >= 0) {
        // Upsert: replace existing message (in-progress turn update)
        const updated = [...prev]
        updated[existingIdx] = newMessage
        return updated
      }
      // Only increment total for genuinely new messages, not upserts
      setTotalMessages((p) => p + 1)
      return [...prev, newMessage]
    })
  }, []))

  const hasMore = false

  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false)

  const generateSummary = useCallback(async () => {
    if (!sessionId || isGeneratingSummary) return

    const baseUrl = getBaseUrl()
    setIsGeneratingSummary(true)
    try {
      const res = await fetch(`${baseUrl}/api/sessions/${sessionId}/generate-summary`, {
        method: 'POST',
      })
      if (res.ok) {
        const data = await res.json()
        if (data.summary_markdown) {
          setSession((prev) =>
            prev ? { ...prev, summary_markdown: data.summary_markdown } : prev
          )
        }
      } else {
        const err = await res.json().catch(() => null)
        console.error('Failed to generate summary:', err?.detail || res.statusText)
      }
    } catch (e) {
      console.error('Failed to generate summary:', e)
    } finally {
      setIsGeneratingSummary(false)
    }
  }, [sessionId, isGeneratingSummary])

  // loadMore kept as no-op for interface compatibility
  const loadMore = useCallback(() => {}, [])

  return { session, messages, isLoading, totalMessages, hasMore, loadMore, generateSummary, isGeneratingSummary }
}
