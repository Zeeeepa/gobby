import { useState, useEffect, useCallback } from 'react'
import type { GobbySession } from './useSessions'

export interface SessionMessage {
  id: string
  role: string
  content: string
  content_type?: string
  tool_name?: string
  tool_input?: string
  tool_result?: string
  timestamp: string
  message_index?: number
}

function getBaseUrl(): string {
  return ''
}

export function useSessionDetail(sessionId: string | null) {
  const [session, setSession] = useState<GobbySession | null>(null)
  const [messages, setMessages] = useState<SessionMessage[]>([])
  const [totalMessages, setTotalMessages] = useState(0)
  const [isLoading, setIsLoading] = useState(false)
  const [offset, setOffset] = useState(0)

  const LIMIT = 50

  // Fetch session detail
  useEffect(() => {
    if (!sessionId) {
      setSession(null)
      setMessages([])
      setTotalMessages(0)
      setOffset(0)
      return
    }

    let cancelled = false
    setIsLoading(true)

    async function fetchDetail() {
      const baseUrl = getBaseUrl()
      try {
        const [sessionRes, messagesRes] = await Promise.all([
          fetch(`${baseUrl}/sessions/${sessionId}`),
          fetch(`${baseUrl}/sessions/${sessionId}/messages?limit=${LIMIT}&offset=0`),
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
          setOffset(LIMIT)
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

  const loadMore = useCallback(async () => {
    if (!sessionId || isLoading) return

    const baseUrl = getBaseUrl()
    try {
      const res = await fetch(`${baseUrl}/sessions/${sessionId}/messages?limit=${LIMIT}&offset=${offset}`)
      if (res.ok) {
        const data = await res.json()
        setMessages((prev) => [...prev, ...(data.messages || [])])
        setOffset((prev) => prev + LIMIT)
      }
    } catch (e) {
      console.error('Failed to load more messages:', e)
    }
  }, [sessionId, offset, isLoading])

  const hasMore = offset < totalMessages

  const [isGeneratingSummary, setIsGeneratingSummary] = useState(false)

  const generateSummary = useCallback(async () => {
    if (!sessionId || isGeneratingSummary) return

    const baseUrl = getBaseUrl()
    setIsGeneratingSummary(true)
    try {
      const res = await fetch(`${baseUrl}/sessions/${sessionId}/generate-summary`, {
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

  return { session, messages, isLoading, totalMessages, hasMore, loadMore, generateSummary, isGeneratingSummary }
}
