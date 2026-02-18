import { useState, useEffect } from 'react'
import type { GitCommit, DiffResult } from '../../hooks/useSourceControl'
import { DiffViewer } from './DiffViewer'

interface Props {
  branchName: string
  currentBranch: string | null
  fetchCommits: (branch: string, limit?: number) => Promise<GitCommit[]>
  fetchDiff: (base: string, head: string) => Promise<DiffResult | null>
  onClose: () => void
}

export function BranchDetail({ branchName, currentBranch, fetchCommits, fetchDiff, onClose }: Props) {
  const [commits, setCommits] = useState<GitCommit[]>([])
  const [diff, setDiff] = useState<DiffResult | null>(null)
  const [showDiff, setShowDiff] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    setDiff(null)
    setShowDiff(false)
    fetchCommits(branchName, 20)
      .then((c) => {
        setCommits(c)
      })
      .catch((e) => {
        console.error('Failed to fetch commits:', e)
      })
      .finally(() => {
        setLoading(false)
      })
  }, [branchName, fetchCommits])

  const handleViewDiff = async () => {
    if (diff) {
      setShowDiff(!showDiff)
      return
    }
    const base = currentBranch || 'main'
    const result = await fetchDiff(base, branchName)
    setDiff(result)
    setShowDiff(true)
  }

  return (
    <div className="sc-detail-panel">
      <div className="sc-detail-panel__header">
        <h3 className="sc-detail-panel__title">{branchName}</h3>
        <button className="sc-detail-panel__close" onClick={onClose}>
          &times;
        </button>
      </div>

      <div className="sc-detail-panel__actions">
        <button className="sc-btn sc-btn--sm" onClick={handleViewDiff}>
          {showDiff ? 'Hide Diff' : `Diff vs ${currentBranch || 'main'}`}
        </button>
      </div>

      {showDiff && diff && (
        <div className="sc-detail-panel__diff">
          <DiffViewer diff={diff} />
        </div>
      )}

      <div className="sc-detail-panel__body">
        <h4 className="sc-detail-panel__subtitle">Recent Commits</h4>
        {loading ? (
          <p className="sc-text-muted">Loading...</p>
        ) : commits.length === 0 ? (
          <p className="sc-text-muted">No commits found</p>
        ) : (
          <div className="sc-commit-list">
            {commits.map((c) => (
              <div key={c.sha} className="sc-commit-list__item">
                <code className="sc-commit-list__sha">{c.short_sha}</code>
                <div className="sc-commit-list__content">
                  <span className="sc-commit-list__msg">{c.message}</span>
                  <span className="sc-commit-list__meta">
                    {c.author} &middot; {new Date(c.date).toLocaleDateString()}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
