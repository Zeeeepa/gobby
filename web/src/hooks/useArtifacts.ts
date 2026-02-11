import { useState, useEffect, useCallback, useRef } from 'react'

// =============================================================================
// Types
// =============================================================================

export interface GobbyArtifact {
  id: string
  session_id: string
  artifact_type: string
  content: string
  created_at: string
  metadata: Record<string, unknown> | null
  source_file: string | null
  line_start: number | null
  line_end: number | null
  title: string | null
  task_id: string | null
  tags: string[]
}

export interface ArtifactFilters {
  sessionId: string | null
  artifactType: string | null
  taskId: string | null
  tag: string | null
  search: string
}

export interface ArtifactStats {
  total_count: number
  by_type: Record<string, number>
  by_session: Record<string, number>
}

// =============================================================================
// Helpers
// =============================================================================

const DEBOUNCE_MS = 300
const PAGE_SIZE = 50

function getBaseUrl(): string {
  return ''
}

// =============================================================================
// Hook
// =============================================================================

export function useArtifacts() {
  const [artifacts, setArtifacts] = useState<GobbyArtifact[]>([])
  const [searchResults, setSearchResults] = useState<GobbyArtifact[] | null>(null)
  const [selectedArtifact, setSelectedArtifact] = useState<GobbyArtifact | null>(null)
  const [stats, setStats] = useState<ArtifactStats | null>(null)
  const [filters, setFilters] = useState<ArtifactFilters>({
    sessionId: null,
    artifactType: null,
    taskId: null,
    tag: null,
    search: '',
  })
  const [isLoading, setIsLoading] = useState(true)
  const [hasMore, setHasMore] = useState(false)
  const debounceRef = useRef<number | null>(null)
  const offsetRef = useRef(0)

  // Fetch artifacts list
  const fetchArtifacts = useCallback(async (append = false) => {
    try {
      const baseUrl = getBaseUrl()
      const offset = append ? offsetRef.current : 0
      const params = new URLSearchParams({
        limit: String(PAGE_SIZE),
        offset: String(offset),
      })
      if (filters.sessionId) params.set('session_id', filters.sessionId)
      if (filters.artifactType) params.set('artifact_type', filters.artifactType)
      if (filters.taskId) params.set('task_id', filters.taskId)
      if (filters.tag) params.set('tag', filters.tag)

      const response = await fetch(`${baseUrl}/artifacts?${params}`)
      if (response.ok) {
        const data = await response.json()
        const fetched: GobbyArtifact[] = data.artifacts || []
        if (append) {
          setArtifacts(prev => [...prev, ...fetched])
        } else {
          setArtifacts(fetched)
        }
        offsetRef.current = offset + fetched.length
        setHasMore(fetched.length === PAGE_SIZE)
      }
    } catch (e) {
      console.error('Failed to fetch artifacts:', e)
    } finally {
      setIsLoading(false)
    }
  }, [filters.sessionId, filters.artifactType, filters.taskId, filters.tag])

  // Search artifacts with debounce
  const searchArtifacts = useCallback(
    (query: string) => {
      if (debounceRef.current) {
        window.clearTimeout(debounceRef.current)
      }

      if (!query.trim()) {
        setSearchResults(null)
        return
      }

      debounceRef.current = window.setTimeout(async () => {
        try {
          const baseUrl = getBaseUrl()
          const params = new URLSearchParams({ q: query })
          if (filters.sessionId) params.set('session_id', filters.sessionId)
          if (filters.artifactType) params.set('artifact_type', filters.artifactType)
          if (filters.taskId) params.set('task_id', filters.taskId)
          if (filters.tag) params.set('tag', filters.tag)

          const response = await fetch(`${baseUrl}/artifacts/search?${params}`)
          if (response.ok) {
            const data = await response.json()
            setSearchResults(data.artifacts || [])
          }
        } catch (e) {
          console.error('Failed to search artifacts:', e)
        }
      }, DEBOUNCE_MS)
    },
    [filters.sessionId, filters.artifactType, filters.taskId, filters.tag]
  )

  // Get single artifact
  const getArtifact = useCallback(async (artifactId: string): Promise<GobbyArtifact | null> => {
    try {
      const baseUrl = getBaseUrl()
      const response = await fetch(`${baseUrl}/artifacts/${encodeURIComponent(artifactId)}`)
      if (response.ok) {
        return await response.json()
      }
    } catch (e) {
      console.error('Failed to get artifact:', e)
    }
    return null
  }, [])

  // Delete artifact
  const deleteArtifact = useCallback(
    async (artifactId: string): Promise<boolean> => {
      try {
        const baseUrl = getBaseUrl()
        const response = await fetch(
          `${baseUrl}/artifacts/${encodeURIComponent(artifactId)}`,
          { method: 'DELETE' }
        )
        if (response.ok) {
          setArtifacts(prev => prev.filter(a => a.id !== artifactId))
          if (selectedArtifact?.id === artifactId) {
            setSelectedArtifact(null)
          }
          fetchStats()
          return true
        }
      } catch (e) {
        console.error('Failed to delete artifact:', e)
      }
      return false
    },
    [selectedArtifact]
  )

  // Add tag to artifact
  const addTag = useCallback(
    async (artifactId: string, tag: string): Promise<boolean> => {
      try {
        const baseUrl = getBaseUrl()
        const response = await fetch(
          `${baseUrl}/artifacts/${encodeURIComponent(artifactId)}/tags`,
          {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tag }),
          }
        )
        if (response.ok) {
          // Update local state
          setArtifacts(prev =>
            prev.map(a =>
              a.id === artifactId && !a.tags.includes(tag) ? { ...a, tags: [...a.tags, tag] } : a
            )
          )
          if (selectedArtifact?.id === artifactId) {
            setSelectedArtifact(prev =>
              prev && !prev.tags.includes(tag) ? { ...prev, tags: [...prev.tags, tag] } : prev
            )
          }
          return true
        }
      } catch (e) {
        console.error('Failed to add tag:', e)
      }
      return false
    },
    [selectedArtifact]
  )

  // Remove tag from artifact
  const removeTag = useCallback(
    async (artifactId: string, tag: string): Promise<boolean> => {
      try {
        const baseUrl = getBaseUrl()
        const response = await fetch(
          `${baseUrl}/artifacts/${encodeURIComponent(artifactId)}/tags/${encodeURIComponent(tag)}`,
          { method: 'DELETE' }
        )
        if (response.ok) {
          // Update local state
          setArtifacts(prev =>
            prev.map(a =>
              a.id === artifactId ? { ...a, tags: a.tags.filter(t => t !== tag) } : a
            )
          )
          if (selectedArtifact?.id === artifactId) {
            setSelectedArtifact(prev =>
              prev ? { ...prev, tags: prev.tags.filter(t => t !== tag) } : prev
            )
          }
          return true
        }
      } catch (e) {
        console.error('Failed to remove tag:', e)
      }
      return false
    },
    [selectedArtifact]
  )

  // Fetch stats
  const fetchStats = useCallback(async () => {
    try {
      const baseUrl = getBaseUrl()
      const params = new URLSearchParams()
      if (filters.sessionId) params.set('session_id', filters.sessionId)

      const response = await fetch(`${baseUrl}/artifacts/stats?${params}`)
      if (response.ok) {
        setStats(await response.json())
      }
    } catch (e) {
      console.error('Failed to fetch artifact stats:', e)
    }
  }, [filters.sessionId])

  // Get timeline for a session
  const getTimeline = useCallback(
    async (sessionId: string, artifactType?: string): Promise<GobbyArtifact[]> => {
      try {
        const baseUrl = getBaseUrl()
        const params = new URLSearchParams()
        if (artifactType) params.set('artifact_type', artifactType)

        const response = await fetch(
          `${baseUrl}/artifacts/timeline/${encodeURIComponent(sessionId)}?${params}`
        )
        if (response.ok) {
          const data = await response.json()
          return data.artifacts || []
        }
      } catch (e) {
        console.error('Failed to get artifact timeline:', e)
      }
      return []
    },
    []
  )

  // Load more (pagination)
  const loadMore = useCallback(() => {
    if (hasMore && !isLoading) {
      fetchArtifacts(true)
    }
  }, [hasMore, isLoading, fetchArtifacts])

  // Fetch on mount and when filters change
  useEffect(() => {
    setIsLoading(true)
    offsetRef.current = 0
    fetchArtifacts()
    fetchStats()
  }, [fetchArtifacts, fetchStats])

  // Handle search filter changes
  useEffect(() => {
    if (filters.search) {
      searchArtifacts(filters.search)
    } else {
      setSearchResults(null)
    }
  }, [filters.search, searchArtifacts])

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
    }
  }, [])

  const refreshArtifacts = useCallback(() => {
    setIsLoading(true)
    offsetRef.current = 0
    fetchArtifacts()
    fetchStats()
  }, [fetchArtifacts, fetchStats])

  return {
    artifacts,
    searchResults,
    selectedArtifact,
    setSelectedArtifact,
    stats,
    isLoading,
    hasMore,
    filters,
    setFilters,
    getArtifact,
    deleteArtifact,
    addTag,
    removeTag,
    getTimeline,
    loadMore,
    refreshArtifacts,
  }
}
