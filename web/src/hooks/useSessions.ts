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
}

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
  const isSecure = window.location.protocol === 'https:'
  return isSecure ? '' : `http://${window.location.hostname}:60887`
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
  const intervalRef = useRef<number | null>(null)

  const fetchSessions = useCallback(async () => {
    try {
      const baseUrl = getBaseUrl()
      const params = new URLSearchParams({ limit: '200' })
      if (filters.source) params.set('source', filters.source)
      if (filters.projectId) params.set('project_id', filters.projectId)

      const response = await fetch(`${baseUrl}/sessions?${params}`)
      if (response.ok) {
        const data = await response.json()
        setSessions(data.sessions || [])
      }
    } catch (e) {
      console.error('Failed to fetch sessions:', e)
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
    }
  }, [])

  // Fetch on mount and when server-side filters change
  useEffect(() => {
    fetchSessions()
    fetchProjects()
  }, [fetchSessions, fetchProjects])

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
    refresh,
  }
}
