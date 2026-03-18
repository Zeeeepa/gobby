import { useState, useEffect, useCallback, useRef } from 'react'
import type { GobbySession } from './useSessions'
import { useWebSocketEvent } from './useWebSocketEvent'

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
          setMessages(data.messages || [])
          setTotalMessages(data.total_count || 0)
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
  useWebSocketEvent('session_message', useCallback((data: Record<string, unknown>) => {
    const msgSessionId = data.session_id as string | undefined
    if (!msgSessionId || msgSessionId !== sessionIdRef.current) return

    const msg = data.message as Record<string, unknown> | undefined
    if (!msg) return

    const newMessage: SessionMessage = {
      id: String(msg.id ?? msg.index ?? `ws-${Date.now()}`),
      role: (msg.role as string) ?? 'assistant',
      content: (msg.content as string) ?? '',
      content_type: msg.content_type as string | undefined,
      tool_name: msg.tool_name as string | undefined,
      tool_input: msg.tool_input as string | undefined,
      tool_result: msg.tool_result as string | undefined,
      tool_use_id: msg.tool_use_id as string | undefined,
      timestamp: (msg.timestamp as string) ?? new Date().toISOString(),
      message_index: msg.index as number | undefined,
    }

    setMessages((prev) => {
      // Deduplicate by id or message_index
      if (newMessage.message_index !== undefined &&
          prev.some((m) => m.message_index === newMessage.message_index)) {
        return prev
      }
      if (prev.some((m) => m.id === newMessage.id)) return prev
      return [...prev, newMessage]
    })
    setTotalMessages((prev) => prev + 1)
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
