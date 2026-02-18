import { useState } from 'react'
import type { GitBranch, GitCommit, DiffResult } from '../../hooks/useSourceControl'
import { BranchDetail } from './BranchDetail'

interface Props {
  branches: GitBranch[]
  currentBranch: string | null
  fetchCommits: (branch: string, limit?: number) => Promise<GitCommit[]>
  fetchDiff: (base: string, head: string) => Promise<DiffResult | null>
}

export function BranchesView({ branches, currentBranch, fetchCommits, fetchDiff }: Props) {
  const [selectedBranch, setSelectedBranch] = useState<string | null>(null)
  const [showRemote, setShowRemote] = useState(false)

  const localBranches = branches.filter((b) => !b.is_remote)
  const remoteBranches = branches.filter((b) => b.is_remote)

  return (
    <div className="sc-branches">
      <div className="sc-branches__main">
        <table className="sc-table">
          <thead>
            <tr>
              <th>Branch</th>
              <th>Status</th>
              <th>Ahead / Behind</th>
              <th>Worktree</th>
              <th>Last Commit</th>
            </tr>
          </thead>
          <tbody>
            {localBranches.map((b) => (
              <tr
                key={b.name}
                className={`sc-table__row ${b.is_current ? 'sc-table__row--current' : ''} ${selectedBranch === b.name ? 'sc-table__row--selected' : ''}`}
                onClick={() => setSelectedBranch(selectedBranch === b.name ? null : b.name)}
              >
                <td className="sc-table__cell--name">
                  {b.is_current && <span className="sc-branches__current-dot" />}
                  {b.name}
                </td>
                <td>{b.is_current ? 'current' : 'local'}</td>
                <td>
                  {b.ahead > 0 && <span className="sc-branches__ahead">+{b.ahead}</span>}
                  {b.behind > 0 && <span className="sc-branches__behind">-{b.behind}</span>}
                  {b.ahead === 0 && b.behind === 0 && <span className="sc-text-muted">even</span>}
                </td>
                <td>
                  {b.worktree_id && (
                    <span className="sc-badge sc-badge--sm sc-badge--worktree">
                      worktree
                    </span>
                  )}
                </td>
                <td className="sc-text-muted">
                  {b.last_commit_date ? new Date(b.last_commit_date).toLocaleDateString() : ''}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {remoteBranches.length > 0 && (
          <>
            <button
              className="sc-branches__toggle-remote"
              onClick={() => setShowRemote(!showRemote)}
            >
              {showRemote ? 'Hide' : 'Show'} remote branches ({remoteBranches.length})
            </button>
            {showRemote && (
              <table className="sc-table sc-table--remote">
                <tbody>
                  {remoteBranches.map((b) => (
                    <tr
                      key={b.name}
                      className={`sc-table__row ${selectedBranch === b.name ? 'sc-table__row--selected' : ''}`}
                      onClick={() => setSelectedBranch(selectedBranch === b.name ? null : b.name)}
                    >
                      <td className="sc-table__cell--name sc-text-muted">
                        origin/{b.name}
                      </td>
                      <td>remote</td>
                      <td />
                      <td />
                      <td className="sc-text-muted">
                        {b.last_commit_date ? new Date(b.last_commit_date).toLocaleDateString() : ''}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </>
        )}
      </div>

      {selectedBranch && (
        <BranchDetail
          branchName={selectedBranch}
          currentBranch={currentBranch}
          fetchCommits={fetchCommits}
          fetchDiff={fetchDiff}
          onClose={() => setSelectedBranch(null)}
        />
      )}
    </div>
  )
}
