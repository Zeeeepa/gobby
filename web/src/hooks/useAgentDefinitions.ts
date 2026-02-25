import { useState, useEffect, useCallback, useMemo } from 'react'

export interface AgentDefInfo {
  definition: {
    name: string
    description?: string | null
    role?: string | null
    mode?: string
    provider?: string
    model?: string | null
    isolation?: string | null
  }
  source: string
  db_id: string | null
}

export function useAgentDefinitions(projectId?: string | null) {
  const [definitions, setDefinitions] = useState<AgentDefInfo[]>([])
  const [loading, setLoading] = useState(false)

  const fetchDefs = useCallback(async () => {
    setLoading(true)
    try {
      const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
      const res = await fetch(`/api/agents/definitions${params}`)
      if (res.ok) {
        const data = await res.json()
        setDefinitions(data.definitions || [])
      }
    } catch {
      // ignore
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    fetchDefs()
  }, [fetchDefs])

  const globalDefs = useMemo(
    () => definitions.filter((d) => d.source === 'installed' || d.source === 'template'),
    [definitions],
  )

  const projectDefs = useMemo(
    () => definitions.filter((d) => d.source === 'project'),
    [definitions],
  )

  const hasGlobal = globalDefs.length > 0
  const hasProject = projectDefs.length > 0
  const showScopeToggle = hasGlobal && hasProject

  return {
    definitions,
    globalDefs,
    projectDefs,
    hasGlobal,
    hasProject,
    showScopeToggle,
    loading,
    refresh: fetchDefs,
  }
}
