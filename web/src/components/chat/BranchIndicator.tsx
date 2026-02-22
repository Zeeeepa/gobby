import { useState, useEffect, useRef, useCallback } from 'react'
import type { WorktreeInfo } from '../../hooks/useSourceControl'

interface BranchIndicatorProps {
  currentBranch: string | null
  worktreePath: string | null
  projectId: string | null
  onWorktreeChange: (worktreePath: string, worktreeId?: string) => void
}

export function BranchIndicator({
  currentBranch,
  worktreePath,
  projectId,
  onWorktreeChange,
}: BranchIndicatorProps) {
  const [isOpen, setIsOpen] = useState(false)
  const [worktrees, setWorktrees] = useState<WorktreeInfo[]>([])
  const [mainRepoPath, setMainRepoPath] = useState<string | null>(null)
  // Local branch state fetched eagerly from API (before any WS session_info)
  const [apiBranch, setApiBranch] = useState<string | null>(null)
  const containerRef = useRef<HTMLDivElement>(null)

  // Eagerly fetch current branch from source-control status API on mount / project change
  useEffect(() => {
    let stale = false
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    fetch(`/api/source-control/status?${params}`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (stale || !data) return
        if (data.current_branch) setApiBranch(data.current_branch)
        if (data.repo_path) setMainRepoPath(data.repo_path)
      })
      .catch(() => {})
    return () => { stale = true }
  }, [projectId])

  // Click-outside-close
  useEffect(() => {
    if (!isOpen) return
    const handleClick = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [isOpen])

  // Fetch worktrees when dropdown opens
  const fetchWorktrees = useCallback(async () => {
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    try {
      const r = await fetch(`/api/source-control/worktrees?${params}`)
      if (r.ok) {
        const data = await r.json()
        setWorktrees(data.worktrees || [])
      }
    } catch (e) {
      console.error('Failed to fetch worktrees:', e)
    }

    // Refresh main repo path too
    try {
      const r = await fetch(`/api/source-control/status?${params}`)
      if (r.ok) {
        const data = await r.json()
        if (data.repo_path) setMainRepoPath(data.repo_path)
        if (data.current_branch) setApiBranch(data.current_branch)
      }
    } catch {
      // non-critical
    }
  }, [projectId])

  const handleToggle = () => {
    if (!isOpen) fetchWorktrees()
    setIsOpen(!isOpen)
  }

  const handleSelect = (path: string, id?: string) => {
    onWorktreeChange(path, id)
    setIsOpen(false)
  }

  // Prefer WS-provided branch (accurate to subprocess CWD), fall back to API
  const effectiveBranch = currentBranch ?? apiBranch
  if (!effectiveBranch) return null

  const isDetached = effectiveBranch.startsWith('detached:')
  const displayBranch = isDetached ? effectiveBranch.replace('detached:', '') : effectiveBranch

  return (
    <div className="relative" ref={containerRef}>
      <button
        onClick={handleToggle}
        className="flex items-center gap-1 px-1.5 py-0.5 rounded text-xs text-muted-foreground hover:bg-muted/60 transition-colors"
        title={worktreePath ?? 'Current branch'}
        aria-haspopup="listbox"
        aria-expanded={isOpen}
      >
        <BranchIcon />
        <span className={isDetached ? 'italic' : ''}>
          {displayBranch}
        </span>
        <ChevronIcon />
      </button>

      {isOpen && (
        <div
          className="absolute left-0 top-full mt-1 w-64 rounded-md border border-border bg-background shadow-lg z-20"
          role="listbox"
          aria-label="Switch worktree"
        >
          {/* Main repo */}
          {mainRepoPath && (
            <button
              role="option"
              aria-selected={worktreePath === mainRepoPath}
              className={`w-full text-left px-3 py-1.5 text-xs hover:bg-muted flex items-center gap-2 ${
                worktreePath === mainRepoPath ? 'bg-accent/20 text-accent' : ''
              }`}
              onClick={() => handleSelect(mainRepoPath)}
            >
              <BranchIcon />
              <div className="min-w-0">
                <div className="font-medium truncate">main repo</div>
                <div className="text-muted-foreground/60 truncate">{mainRepoPath}</div>
              </div>
            </button>
          )}

          {/* Worktrees */}
          {worktrees.length > 0 && (
            <div className="border-t border-border">
              {worktrees.map((wt) => {
                const isActive = worktreePath === wt.worktree_path
                return (
                  <button
                    key={wt.id}
                    role="option"
                    aria-selected={isActive}
                    className={`w-full text-left px-3 py-1.5 text-xs hover:bg-muted flex items-center gap-2 ${
                      isActive ? 'bg-accent/20 text-accent' : ''
                    }`}
                    onClick={() => handleSelect(wt.worktree_path, wt.id)}
                    title={wt.worktree_path}
                  >
                    <WorktreeIcon />
                    <div className="min-w-0">
                      <div className="font-medium truncate">{wt.branch_name}</div>
                      <div className="text-muted-foreground/60 truncate">{wt.worktree_path}</div>
                    </div>
                  </button>
                )
              })}
            </div>
          )}

          {!mainRepoPath && worktrees.length === 0 && (
            <div className="px-3 py-2 text-xs text-muted-foreground">No worktrees found</div>
          )}
        </div>
      )}
    </div>
  )
}

function BranchIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
      <line x1="6" y1="3" x2="6" y2="15" />
      <circle cx="18" cy="6" r="3" />
      <circle cx="6" cy="18" r="3" />
      <path d="M18 9a9 9 0 0 1-9 9" />
    </svg>
  )
}

function WorktreeIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0">
      <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z" />
    </svg>
  )
}

function ChevronIcon() {
  return (
    <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 opacity-50">
      <polyline points="6 9 12 15 18 9" />
    </svg>
  )
}
