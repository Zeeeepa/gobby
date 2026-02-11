import { useState, useEffect, useCallback, useRef } from 'react'

export interface MemoryCrossRef {
  source_id: string
  target_id: string
  similarity: number
  created_at: string
}

export interface MemoryGraphData {
  memories: GobbyMemory[]
  crossrefs: MemoryCrossRef[]
}

export interface GobbyMemory {
  id: string
  memory_type: string
  content: string
  created_at: string
  updated_at: string
  project_id: string | null
  source_type: string | null
  source_session_id: string | null
  importance: number
  access_count: number
  last_accessed_at: string | null
  tags: string[] | null
  mem0_id: string | null
}

export interface KnowledgeEntity {
  name: string
  type: string
  properties: Record<string, unknown>
}

export interface KnowledgeRelationship {
  source: string
  target: string
  type: string
  properties: Record<string, unknown>
}

export interface KnowledgeGraphData {
  entities: KnowledgeEntity[]
  relationships: KnowledgeRelationship[]
}

export interface MemoryFilters {
  projectId: string | null
  memoryType: string | null
  minImportance: number | null
  search: string
}

export interface MemoryStats {
  total_count: number
  by_type: Record<string, number>
  avg_importance: number
  project_id: string | null
}

interface CreateMemoryParams {
  content: string
  memory_type?: string
  importance?: number
  project_id?: string | null
  tags?: string[]
}

interface UpdateMemoryParams {
  content?: string
  importance?: number
  tags?: string[]
}

const DEBOUNCE_MS = 300

function getBaseUrl(): string {
  return ''
}

export function useMemory() {
  const [memories, setMemories] = useState<GobbyMemory[]>([])
  const [searchResults, setSearchResults] = useState<GobbyMemory[] | null>(null)
  const [stats, setStats] = useState<MemoryStats | null>(null)
  const [filters, setFilters] = useState<MemoryFilters>({
    projectId: null,
    memoryType: null,
    minImportance: null,
    search: '',
  })
  const [isLoading, setIsLoading] = useState(true)
  const debounceRef = useRef<number | null>(null)

  // Fetch memories list
  const fetchMemories = useCallback(async () => {
    try {
      const baseUrl = getBaseUrl()
      const params = new URLSearchParams({ limit: '100' })
      if (filters.projectId) params.set('project_id', filters.projectId)
      if (filters.memoryType) params.set('memory_type', filters.memoryType)
      if (filters.minImportance !== null) {
        params.set('min_importance', String(filters.minImportance))
      }

      const response = await fetch(`${baseUrl}/memories?${params}`)
      if (response.ok) {
        const data = await response.json()
        const items = (data.memories || []).map((m: Record<string, unknown>) => ({
          ...m,
          tags: Array.isArray(m.tags) ? m.tags
            : typeof m.tags === 'string' ? (m.tags as string).split(',').map((t: string) => t.trim()).filter(Boolean)
            : null,
        })) as GobbyMemory[]
        setMemories(items)
      }
    } catch (e) {
      console.error('Failed to fetch memories:', e)
    } finally {
      setIsLoading(false)
    }
  }, [filters.projectId, filters.memoryType, filters.minImportance])

  // Create memory
  const createMemory = useCallback(
    async (params: CreateMemoryParams): Promise<GobbyMemory | null> => {
      try {
        const baseUrl = getBaseUrl()
        const response = await fetch(`${baseUrl}/memories`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params),
        })
        if (response.ok) {
          const memory = await response.json()
          // Refresh list after creation
          await fetchMemories()
          return memory
        }
      } catch (e) {
        console.error('Failed to create memory:', e)
      }
      return null
    },
    [fetchMemories]
  )

  // Update memory
  const updateMemory = useCallback(
    async (memoryId: string, params: UpdateMemoryParams): Promise<GobbyMemory | null> => {
      try {
        const baseUrl = getBaseUrl()
        const response = await fetch(`${baseUrl}/memories/${memoryId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(params),
        })
        if (response.ok) {
          const memory = await response.json()
          await fetchMemories()
          return memory
        }
      } catch (e) {
        console.error('Failed to update memory:', e)
      }
      return null
    },
    [fetchMemories]
  )

  // Delete memory
  const deleteMemory = useCallback(
    async (memoryId: string): Promise<boolean> => {
      try {
        const baseUrl = getBaseUrl()
        const response = await fetch(`${baseUrl}/memories/${memoryId}`, {
          method: 'DELETE',
        })
        if (response.ok) {
          await fetchMemories()
          return true
        }
      } catch (e) {
        console.error('Failed to delete memory:', e)
      }
      return false
    },
    [fetchMemories]
  )

  // Search memories with debounce
  const searchMemories = useCallback(
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
          if (filters.projectId) params.set('project_id', filters.projectId)

          const response = await fetch(`${baseUrl}/memories/search?${params}`)
          if (response.ok) {
            const data = await response.json()
            setSearchResults(data.results || [])
          }
        } catch (e) {
          console.error('Failed to search memories:', e)
        }
      }, DEBOUNCE_MS)
    },
    [filters.projectId]
  )

  // Fetch stats
  const fetchStats = useCallback(async () => {
    try {
      const baseUrl = getBaseUrl()
      const params = new URLSearchParams()
      if (filters.projectId) params.set('project_id', filters.projectId)

      const response = await fetch(`${baseUrl}/memories/stats?${params}`)
      if (response.ok) {
        setStats(await response.json())
      }
    } catch (e) {
      console.error('Failed to fetch memory stats:', e)
    }
  }, [filters.projectId])

  // Fetch on mount and when filters change
  useEffect(() => {
    fetchMemories()
    fetchStats()
  }, [fetchMemories, fetchStats])

  // Cleanup debounce on unmount
  useEffect(() => {
    return () => {
      if (debounceRef.current) window.clearTimeout(debounceRef.current)
    }
  }, [])

  const refreshMemories = useCallback(() => {
    setIsLoading(true)
    fetchMemories()
    fetchStats()
  }, [fetchMemories, fetchStats])

  const fetchKnowledgeGraph = useCallback(async (limit = 500): Promise<KnowledgeGraphData | null> => {
    try {
      const baseUrl = getBaseUrl()
      const params = new URLSearchParams({ limit: String(limit) })
      const response = await fetch(`${baseUrl}/memories/graph/entities?${params}`)
      if (response.ok) {
        return await response.json()
      }
    } catch (e) {
      console.error('Failed to fetch knowledge graph:', e)
    }
    return null
  }, [])

  const fetchEntityNeighbors = useCallback(async (name: string): Promise<KnowledgeGraphData | null> => {
    try {
      const baseUrl = getBaseUrl()
      const response = await fetch(`${baseUrl}/memories/graph/entities/${encodeURIComponent(name)}/neighbors`)
      if (response.ok) {
        return await response.json()
      }
    } catch (e) {
      console.error('Failed to fetch entity neighbors:', e)
    }
    return null
  }, [])

  const fetchGraphData = useCallback(async (): Promise<MemoryGraphData | null> => {
    try {
      const baseUrl = getBaseUrl()
      const params = new URLSearchParams()
      if (filters.projectId) params.set('project_id', filters.projectId)

      const response = await fetch(`${baseUrl}/memories/graph?${params}`)
      if (response.ok) {
        const data = await response.json()
        return {
          memories: (data.memories || []).map((m: Record<string, unknown>) => ({
            ...m,
            tags: Array.isArray(m.tags) ? m.tags
              : typeof m.tags === 'string' ? (m.tags as string).split(',').map((t: string) => t.trim()).filter(Boolean)
              : null,
          })) as GobbyMemory[],
          crossrefs: data.crossrefs || [],
        }
      }
    } catch (e) {
      console.error('Failed to fetch graph data:', e)
    }
    return null
  }, [filters.projectId])

  return {
    memories,
    searchResults,
    stats,
    isLoading,
    filters,
    setFilters,
    createMemory,
    updateMemory,
    deleteMemory,
    searchMemories,
    refreshMemories,
    fetchGraphData,
    fetchKnowledgeGraph,
    fetchEntityNeighbors,
  }
}

export interface Mem0Status {
  configured: boolean
  url?: string
}

export interface Neo4jStatus {
  configured: boolean
  url?: string
}

export function useMem0Status() {
  const [mem0Status, setMem0Status] = useState<Mem0Status | null>(null)

  useEffect(() => {
    async function fetchStatus() {
      try {
        const baseUrl = getBaseUrl()
        const response = await fetch(`${baseUrl}/admin/status`)
        if (response.ok) {
          const data = await response.json()
          const mem0 = data.memory?.mem0
          if (mem0) {
            setMem0Status(mem0)
          }
        }
      } catch (e) {
        console.warn('Failed to fetch mem0 status:', e)
      }
    }
    fetchStatus()
  }, [])

  return mem0Status
}

export function useNeo4jStatus() {
  const [neo4jStatus, setNeo4jStatus] = useState<Neo4jStatus | null>(null)

  useEffect(() => {
    async function fetchStatus() {
      try {
        const baseUrl = getBaseUrl()
        const response = await fetch(`${baseUrl}/admin/status`)
        if (response.ok) {
          const data = await response.json()
          const neo4j = data.memory?.neo4j
          if (neo4j) {
            setNeo4jStatus(neo4j)
          }
        }
      } catch (e) {
        console.warn('Failed to fetch neo4j status:', e)
      }
    }
    fetchStatus()
  }, [])

  return neo4jStatus
}
