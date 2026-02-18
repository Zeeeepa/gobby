import { useState, useEffect, useCallback, useRef } from 'react'

// =============================================================================
// Types
// =============================================================================

export interface SourceControlStatus {
  github_available: boolean
  github_repo: string | null
  current_branch: string | null
  branch_count: number
  worktree_count: number
  clone_count: number
}

export interface GitBranch {
  name: string
  is_current: boolean
  is_remote: boolean
  ahead: number
  behind: number
  last_commit_date: string
  worktree_id: string | null
}

export interface GitCommit {
  sha: string
  short_sha: string
  message: string
  author: string
  date: string
}

export interface PullRequest {
  number: number
  title: string
  state: 'open' | 'closed' | 'merged'
  author: string
  head_branch: string
  base_branch: string
  created_at: string
  updated_at: string
  draft: boolean
  checks_status: 'pending' | 'success' | 'failure' | null
  linked_task_id: string | null
}

export interface WorktreeInfo {
  id: string
  branch_name: string
  worktree_path: string
  status: string
  task_id: string | null
  agent_session_id: string | null
  project_id: string
  base_branch: string
  created_at: string
  updated_at: string
  merged_at: string | null
}

export interface CloneInfo {
  id: string
  branch_name: string
  clone_path: string
  remote_url: string | null
  status: string
  task_id: string | null
  project_id: string
  base_branch: string
  created_at: string
  updated_at: string
}

export interface CIWorkflowRun {
  id: number
  name: string
  status: string
  conclusion: string | null
  branch: string
  event: string
  created_at: string
  html_url: string
}

export interface DiffResult {
  diff_stat: string
  files: { status: string; path: string }[]
  patch: string
}

// =============================================================================
// Constants
// =============================================================================

const LOCAL_POLL_MS = 5000
const GITHUB_POLL_MS = 30000

function getBaseUrl(): string {
  return ''
}

// =============================================================================
// Hook
// =============================================================================

export function useSourceControl() {
  const [status, setStatus] = useState<SourceControlStatus | null>(null)
  const [branches, setBranches] = useState<GitBranch[]>([])
  const [prs, setPrs] = useState<PullRequest[]>([])
  const [worktrees, setWorktrees] = useState<WorktreeInfo[]>([])
  const [clones, setClones] = useState<CloneInfo[]>([])
  const [ciRuns, setCiRuns] = useState<CIWorkflowRun[]>([])

  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [projectId, setProjectId] = useState<string | null>(null)

  const localPollRef = useRef<number | null>(null)
  const githubPollRef = useRef<number | null>(null)

  const buildParams = useCallback(
    (extra?: Record<string, string>) => {
      const params = new URLSearchParams()
      if (projectId) params.set('project_id', projectId)
      if (extra) {
        for (const [k, v] of Object.entries(extra)) params.set(k, v)
      }
      return params.toString()
    },
    [projectId]
  )

  // --- Fetch functions ---

  const fetchStatus = useCallback(async () => {
    try {
      const r = await fetch(`${getBaseUrl()}/api/source-control/status?${buildParams()}`)
      if (r.ok) {
        setStatus(await r.json())
        setError(null)
      }
    } catch (e) {
      const message = e instanceof Error ? e.message : String(e)
      setError(message)
      console.error('Failed to fetch source control status:', e)
    }
  }, [buildParams])

  const fetchBranches = useCallback(async () => {
    try {
      const r = await fetch(`${getBaseUrl()}/api/source-control/branches?${buildParams()}`)
      if (r.ok) {
        const data = await r.json()
        setBranches(data.branches || [])
      }
    } catch (e) {
      console.error('Failed to fetch branches:', e)
    }
  }, [buildParams])

  const fetchPrs = useCallback(
    async (state = 'open') => {
      try {
        const r = await fetch(
          `${getBaseUrl()}/api/source-control/prs?${buildParams({ state })}`
        )
        if (r.ok) {
          const data = await r.json()
          setPrs(data.prs || [])
        }
      } catch (e) {
        console.error('Failed to fetch PRs:', e)
      }
    },
    [buildParams]
  )

  const fetchWorktrees = useCallback(async () => {
    try {
      const r = await fetch(`${getBaseUrl()}/api/source-control/worktrees?${buildParams()}`)
      if (r.ok) {
        const data = await r.json()
        setWorktrees(data.worktrees || [])
      }
    } catch (e) {
      console.error('Failed to fetch worktrees:', e)
    }
  }, [buildParams])

  const fetchClones = useCallback(async () => {
    try {
      const r = await fetch(`${getBaseUrl()}/api/source-control/clones?${buildParams()}`)
      if (r.ok) {
        const data = await r.json()
        setClones(data.clones || [])
      }
    } catch (e) {
      console.error('Failed to fetch clones:', e)
    }
  }, [buildParams])

  const fetchCiRuns = useCallback(async () => {
    try {
      const r = await fetch(`${getBaseUrl()}/api/source-control/cicd/runs?${buildParams()}`)
      if (r.ok) {
        const data = await r.json()
        setCiRuns(data.runs || [])
      }
    } catch (e) {
      console.error('Failed to fetch CI/CD runs:', e)
    }
  }, [buildParams])

  // --- On-demand fetchers ---

  const fetchCommits = useCallback(
    async (branchName: string, limit = 20): Promise<GitCommit[]> => {
      try {
        const r = await fetch(
          `${getBaseUrl()}/api/source-control/branches/${encodeURIComponent(branchName)}/commits?${buildParams({ limit: String(limit) })}`
        )
        if (r.ok) {
          const data = await r.json()
          return data.commits || []
        }
      } catch (e) {
        console.error('Failed to fetch commits:', e)
      }
      return []
    },
    [buildParams]
  )

  const fetchDiff = useCallback(
    async (base: string, head: string): Promise<DiffResult | null> => {
      try {
        const r = await fetch(
          `${getBaseUrl()}/api/source-control/diff?${buildParams({ base, head })}`
        )
        if (r.ok) return await r.json()
      } catch (e) {
        console.error('Failed to fetch diff:', e)
      }
      return null
    },
    [buildParams]
  )

  const fetchPrDetail = useCallback(
    async (number: number): Promise<Record<string, unknown> | null> => {
      try {
        const r = await fetch(
          `${getBaseUrl()}/api/source-control/prs/${number}?${buildParams()}`
        )
        if (r.ok) {
          const data = await r.json()
          return data.pr || null
        }
      } catch (e) {
        console.error('Failed to fetch PR detail:', e)
      }
      return null
    },
    [buildParams]
  )

  // --- Actions ---

  const deleteWorktree = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        const r = await fetch(`${getBaseUrl()}/api/source-control/worktrees/${id}`, {
          method: 'DELETE',
        })
        if (r.ok) {
          fetchWorktrees()
          fetchStatus()
          return true
        }
      } catch (e) {
        console.error('Failed to delete worktree:', e)
      }
      return false
    },
    [fetchWorktrees, fetchStatus]
  )

  const cleanupWorktrees = useCallback(
    async (hours = 24, dryRun = false): Promise<WorktreeInfo[]> => {
      try {
        const r = await fetch(
          `${getBaseUrl()}/api/source-control/worktrees/cleanup?${buildParams({
            hours: String(hours),
            dry_run: String(dryRun),
          })}`,
          { method: 'POST' }
        )
        if (r.ok) {
          const data = await r.json()
          if (!dryRun) {
            fetchWorktrees()
            fetchStatus()
          }
          return data.candidates || []
        }
      } catch (e) {
        console.error('Failed to cleanup worktrees:', e)
      }
      return []
    },
    [buildParams, fetchWorktrees, fetchStatus]
  )

  const syncWorktree = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        const r = await fetch(`${getBaseUrl()}/api/source-control/worktrees/${id}/sync`, {
          method: 'POST',
        })
        if (r.ok) {
          fetchWorktrees()
          return true
        }
      } catch (e) {
        console.error('Failed to sync worktree:', e)
      }
      return false
    },
    [fetchWorktrees]
  )

  const deleteClone = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        const r = await fetch(`${getBaseUrl()}/api/source-control/clones/${id}`, {
          method: 'DELETE',
        })
        if (r.ok) {
          fetchClones()
          fetchStatus()
          return true
        }
      } catch (e) {
        console.error('Failed to delete clone:', e)
      }
      return false
    },
    [fetchClones, fetchStatus]
  )

  const syncClone = useCallback(
    async (id: string): Promise<boolean> => {
      try {
        const r = await fetch(`${getBaseUrl()}/api/source-control/clones/${id}/sync`, {
          method: 'POST',
        })
        if (r.ok) {
          fetchClones()
          return true
        }
      } catch (e) {
        console.error('Failed to sync clone:', e)
      }
      return false
    },
    [fetchClones]
  )

  // --- Fetch all local data ---

  const fetchLocal = useCallback(async () => {
    await Promise.all([fetchStatus(), fetchBranches(), fetchWorktrees(), fetchClones()])
    setIsLoading(false)
  }, [fetchStatus, fetchBranches, fetchWorktrees, fetchClones])

  // --- Fetch GitHub data ---

  const fetchGitHub = useCallback(async () => {
    await Promise.all([fetchPrs(), fetchCiRuns()])
  }, [fetchPrs, fetchCiRuns])

  // --- Refresh all ---

  const refresh = useCallback(async () => {
    setIsLoading(true)
    await Promise.all([fetchLocal(), fetchGitHub()])
  }, [fetchLocal, fetchGitHub])

  // --- Effects ---

  // Local data: initial fetch + polling (5s)
  useEffect(() => {
    setIsLoading(true)
    fetchLocal()
    localPollRef.current = window.setInterval(fetchLocal, LOCAL_POLL_MS)
    return () => {
      if (localPollRef.current) window.clearInterval(localPollRef.current)
    }
  }, [fetchLocal])

  // GitHub data: initial fetch + polling (30s)
  useEffect(() => {
    fetchGitHub()
    githubPollRef.current = window.setInterval(fetchGitHub, GITHUB_POLL_MS)
    return () => {
      if (githubPollRef.current) window.clearInterval(githubPollRef.current)
    }
  }, [fetchGitHub])

  return {
    // Data
    status,
    branches,
    prs,
    worktrees,
    clones,
    ciRuns,

    // State
    isLoading,
    error,
    projectId,
    setProjectId,

    // On-demand
    fetchCommits,
    fetchDiff,
    fetchPrDetail,
    fetchPrs,

    // Actions
    deleteWorktree,
    cleanupWorktrees,
    syncWorktree,
    deleteClone,
    syncClone,
    refresh,
  }
}
