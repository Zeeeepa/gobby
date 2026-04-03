import { useState, useCallback } from 'react'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface SpawnParams {
  task_id: string
  agent_name?: string
  prompt?: string
  mode?: 'interactive' | 'web_chat' | 'headless'
  isolation?: 'none' | 'worktree' | 'clone'
  provider?: string
  model?: string
  workflow?: string
  branch_name?: string
  base_branch?: string
  timeout?: number
  max_turns?: number
}

export interface SpawnResult {
  success: boolean
  run_id?: string
  child_session_id?: string
  conversation_id?: string
  mode: string
  isolation?: string
  branch_name?: string
  pid?: number
  error?: string
}

export interface BatchResult {
  results: SpawnResult[]
  succeeded: number
  failed: number
}

export interface CategoryDefaults {
  agent_name: string
  mode: 'interactive' | 'web_chat' | 'headless'
  isolation: 'none' | 'worktree' | 'clone'
  model?: string
}

export interface AgentDefinition {
  definition: {
    name: string
    description?: string
    role?: string
    mode?: string
    provider?: string
    model?: string
    isolation?: string
  }
  source: string
  db_id: string
}

export interface PromptPreview {
  prompt: string
  preamble: string | null
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useAgentSpawn() {
  const [spawning, setSpawning] = useState(false)
  const [lastResult, setLastResult] = useState<SpawnResult | null>(null)

  const spawn = useCallback(async (params: SpawnParams): Promise<SpawnResult> => {
    setSpawning(true)
    setLastResult(null)
    try {
      const res = await fetch('/api/agents/spawn', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      })
      const data = await res.json()
      if (!res.ok) {
        const result: SpawnResult = {
          success: false,
          mode: params.mode || 'interactive',
          error: data.detail || 'Spawn failed',
        }
        setLastResult(result)
        return result
      }
      const result: SpawnResult = { success: true, ...data }
      setLastResult(result)
      return result
    } catch (e) {
      const result: SpawnResult = {
        success: false,
        mode: params.mode || 'interactive',
        error: e instanceof Error ? e.message : 'Network error',
      }
      setLastResult(result)
      return result
    } finally {
      setSpawning(false)
    }
  }, [])

  const spawnBatch = useCallback(async (spawns: SpawnParams[]): Promise<BatchResult> => {
    setSpawning(true)
    try {
      const res = await fetch('/api/agents/spawn/batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ spawns }),
      })
      const data = await res.json()
      if (!res.ok) {
        return { results: [], succeeded: 0, failed: spawns.length }
      }
      return data
    } catch {
      return { results: [], succeeded: 0, failed: spawns.length }
    } finally {
      setSpawning(false)
    }
  }, [])

  const getDefaults = useCallback(async (projectId: string): Promise<Record<string, CategoryDefaults>> => {
    try {
      const res = await fetch(`/api/agents/launch-defaults?project_id=${encodeURIComponent(projectId)}`)
      if (res.ok) {
        const data = await res.json()
        return data.defaults || {}
      }
    } catch {
      // ignore
    }
    return {}
  }, [])

  const saveDefaults = useCallback(async (
    projectId: string,
    category: string,
    defaults: CategoryDefaults,
  ): Promise<void> => {
    try {
      await fetch('/api/agents/launch-defaults', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          category,
          ...defaults,
        }),
      })
    } catch {
      // ignore
    }
  }, [])

  const fetchDefinitions = useCallback(async (projectId?: string): Promise<AgentDefinition[]> => {
    try {
      const params = projectId ? `?project_id=${encodeURIComponent(projectId)}` : ''
      const res = await fetch(`/api/agents/definitions${params}`)
      if (res.ok) {
        const data = await res.json()
        return data.definitions || []
      }
    } catch {
      // ignore
    }
    return []
  }, [])

  const previewPrompt = useCallback(async (taskId: string, agentName: string = 'default'): Promise<PromptPreview | null> => {
    try {
      const params = new URLSearchParams({ task_id: taskId, agent_name: agentName })
      const res = await fetch(`/api/agents/spawn/prompt-preview?${params}`)
      if (res.ok) {
        const data = await res.json()
        return { prompt: data.prompt, preamble: data.preamble }
      }
    } catch {
      // ignore
    }
    return null
  }, [])

  return {
    spawn,
    spawnBatch,
    spawning,
    lastResult,
    getDefaults,
    saveDefaults,
    fetchDefinitions,
    previewPrompt,
  }
}
