import { useState, useEffect, useRef } from 'react'
import type { SourceControlStatus, PullRequest, WorktreeInfo, CIWorkflowRun, GitCommit } from '../../hooks/useSourceControl'
import type { SubTab } from '../GitHubPage'
import { StatusBadge } from './StatusBadge'

interface Props {
  status: SourceControlStatus | null
  prs: PullRequest[]
  worktrees: WorktreeInfo[]
  ciRuns: CIWorkflowRun[]
  onNavigate: (tab: SubTab) => void
  fetchCommits: (branch: string, limit?: number) => Promise<GitCommit[]>
}

export function SourceControlOverview({ status, prs, worktrees, ciRuns, onNavigate, fetchCommits }: Props) {
  const [recentCommits, setRecentCommits] = useState<GitCommit[]>([])
  const fetchCommitsRef = useRef(fetchCommits)
  fetchCommitsRef.current = fetchCommits

  useEffect(() => {
    if (status?.current_branch) {
      fetchCommitsRef.current(status.current_branch, 5)
        .then(setRecentCommits)
        .catch((e) => console.error('Failed to fetch recent commits:', e))
    }
  }, [status?.current_branch])

  const staleWorktrees = worktrees.filter((w) => w.status === 'stale')
  const activeWorktrees = worktrees.filter((w) => w.status === 'active')
  const latestRun = ciRuns[0]

  return (
    <div className="sc-overview">
      <div className="sc-overview__cards">
        <button className="sc-overview__card" onClick={() => onNavigate('branches')}>
          <div className="sc-overview__card-value">{status?.branch_count ?? 0}</div>
          <div className="sc-overview__card-label">Branches</div>
          {status?.current_branch && (
            <span className="sc-overview__card-badge">{status.current_branch}</span>
          )}
        </button>

        <button className="sc-overview__card" onClick={() => onNavigate('prs')}>
          <div className="sc-overview__card-value">
            {status?.github_available ? prs.length : '\u2014'}
          </div>
          <div className="sc-overview__card-label">Open PRs</div>
          {!status?.github_available && (
            <span className="sc-overview__card-badge sc-overview__card-badge--muted">
              No GitHub
            </span>
          )}
        </button>

        <button className="sc-overview__card" onClick={() => onNavigate('worktrees')}>
          <div className="sc-overview__card-value">
            {activeWorktrees.length} / {worktrees.length}
          </div>
          <div className="sc-overview__card-label">Worktrees</div>
          {staleWorktrees.length > 0 && (
            <span className="sc-overview__card-badge sc-overview__card-badge--warning">
              {staleWorktrees.length} stale
            </span>
          )}
        </button>

        <button className="sc-overview__card" onClick={() => onNavigate('cicd')}>
          <div className="sc-overview__card-value">
            {status?.github_available && latestRun ? (
              <StatusBadge status={latestRun.conclusion || latestRun.status} />
            ) : (
              '\u2014'
            )}
          </div>
          <div className="sc-overview__card-label">CI Status</div>
          {!status?.github_available && (
            <span className="sc-overview__card-badge sc-overview__card-badge--muted">
              No GitHub
            </span>
          )}
        </button>
      </div>

      <div className="sc-overview__recent">
        <h3 className="sc-overview__section-title">Recent Activity</h3>

        {recentCommits.length > 0 && (
          <div className="sc-overview__section">
            <h4 className="sc-overview__subsection-title">
              Recent Commits on {status?.current_branch}
            </h4>
            <div className="sc-overview__list">
              {recentCommits.map((c) => (
                <div key={c.sha} className="sc-overview__commit">
                  <code className="sc-overview__commit-sha">{c.short_sha}</code>
                  <span className="sc-overview__commit-msg">{c.message}</span>
                  <span className="sc-overview__commit-author">{c.author}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {prs.length > 0 && (
          <div className="sc-overview__section">
            <h4 className="sc-overview__subsection-title">Open Pull Requests</h4>
            <div className="sc-overview__list">
              {prs.slice(0, 3).map((pr) => (
                <button type="button" key={pr.number} className="sc-overview__pr" onClick={() => onNavigate('prs')}>
                  <span className="sc-overview__pr-number">#{pr.number}</span>
                  <span className="sc-overview__pr-title">{pr.title}</span>
                  <span className="sc-overview__pr-author">{pr.author}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {staleWorktrees.length > 0 && (
          <div className="sc-overview__section">
            <h4 className="sc-overview__subsection-title sc-overview__subsection-title--warning">
              Stale Worktrees
            </h4>
            <div className="sc-overview__list">
              {staleWorktrees.map((wt) => (
                <button type="button" key={wt.id} className="sc-overview__stale-wt" onClick={() => onNavigate('worktrees')}>
                  <span>{wt.branch_name}</span>
                  <StatusBadge status="stale" />
                </button>
              ))}
            </div>
          </div>
        )}

        {recentCommits.length === 0 && prs.length === 0 && staleWorktrees.length === 0 && (
          <p className="sc-overview__empty">No recent activity</p>
        )}
      </div>
    </div>
  )
}
