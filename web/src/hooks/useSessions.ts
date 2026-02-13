import { useState, useEffect, useCallback, useMemo, useRef } from 'react'

export interface GobbySession {
  id: string
  ref: string
  external_id: string
  source: string
  project_id: string
  title: string | null
  status: string
  model: string | null
  message_count: number
  created_at: string
  updated_at: string
  seq_num: number | null
  summary_markdown: string | null
  git_branch: string | null
  usage_input_tokens: number
  usage_output_tokens: number
  usage_total_cost_usd: number
  had_edits: boolean
  agent_depth: number
  parent_session_id: string | null
  tasks_closed?: number
  memories_created?: number
  commit_count?: number
}

export const KNOWN_SOURCES = ['claude', 'gemini', 'codex', 'claude_sdk_web_chat'] as const

export interface SessionFilters {
  source: string | null
  projectId: string | null
  search: string
  sortOrder: 'newest' | 'oldest'
}

export interface ProjectInfo {
  id: string
  name: string
  repo_path: string
}

const POLL_INTERVAL = 30000

function getBaseUrl(): string {
  return ''
}

export function useSessions() {
  const [sessions, setSessions] = useState<GobbySession[]>([])
  const [projects, setProjects] = useState<ProjectInfo[]>([])
  const [filters, setFilters] = useState<SessionFilters>({
    source: null,
    projectId: null,
    search: '',
    sortOrder: 'newest',
  })
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<Error | null>(null)
  const intervalRef = useRef<number | null>(null)

  const fetchSessions = useCallback(async () => {
    setError(null)
    try {
      const baseUrl = getBaseUrl()
      const params = new URLSearchParams({ limit: '200' })
      if (filters.source) params.set('source', filters.source)
      if (filters.projectId) params.set('project_id', filters.projectId)

      const response = await fetch(`${baseUrl}/sessions?${params}`)
      if (response.ok) {
        const data = await response.json()
        setSessions(Array.isArray(data.sessions) ? data.sessions : [])
      } else {
        throw new Error(`Failed to fetch sessions: ${response.status}`)
      }
    } catch (e) {
      console.error('Failed to fetch sessions:', e)
      setError(e instanceof Error ? e : new Error(String(e)))
    } finally {
      setIsLoading(false)
    }
  }, [filters.source, filters.projectId])

  const fetchProjects = useCallback(async () => {
    try {
      const baseUrl = getBaseUrl()
      const response = await fetch(`${baseUrl}/api/files/projects`)
      if (response.ok) {
        const data = await response.json()
        setProjects(data)
      }
    } catch (e) {
      console.error('Failed to fetch projects:', e)
      setError(e instanceof Error ? e : new Error(String(e)))
    }
  }, [])

  // Fetch sessions on mount and when server-side filters change
  useEffect(() => {
    fetchSessions()
  }, [fetchSessions])

  // Fetch projects only once on mount
  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  // Poll for updates
  useEffect(() => {
    intervalRef.current = window.setInterval(fetchSessions, POLL_INTERVAL)
    return () => {
      if (intervalRef.current) window.clearInterval(intervalRef.current)
    }
  }, [fetchSessions])

  // Client-side filtering and sorting
  const filteredSessions = useMemo(() => {
    let result = sessions

    // Client-side search filter
    if (filters.search) {
      const query = filters.search.toLowerCase()
      result = result.filter(
        (s) =>
          (s.title && s.title.toLowerCase().includes(query)) ||
          s.ref.toLowerCase().includes(query) ||
          s.external_id.toLowerCase().includes(query)
      )
    }

    // Sort
    result = [...result].sort((a, b) => {
      const aTime = new Date(a.updated_at).getTime()
      const bTime = new Date(b.updated_at).getTime()
      return filters.sortOrder === 'newest' ? bTime - aTime : aTime - bTime
    })

    return result
  }, [sessions, filters.search, filters.sortOrder])

  const refresh = useCallback(() => {
    setIsLoading(true)
    fetchSessions()
  }, [fetchSessions])

  return {
    sessions,
    filteredSessions,
    projects,
    filters,
    setFilters,
    isLoading,
    error,
    refresh,
  }
}
