import { useState, useEffect, useCallback } from 'react'
import type { GobbySession } from './useSessions'

export interface SessionMessage {
  id: string
  role: string
  content: string
  timestamp: string
  tool_calls?: unknown[]
}

function getBaseUrl(): string {
  const isSecure = window.location.protocol === 'https:'
  return isSecure ? '' : `http://${window.location.hostname}:60887`
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
        }

        if (messagesRes.ok) {
          const data = await messagesRes.json()
          setMessages(data.messages || [])
          setTotalMessages(data.total_count || 0)
          setOffset(LIMIT)
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

  return { session, messages, isLoading, totalMessages, hasMore, loadMore }
}
