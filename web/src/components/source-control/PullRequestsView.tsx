import { useState } from 'react'
import type { PullRequest } from '../../hooks/useSourceControl'
import { StatusBadge } from './StatusBadge'
import { PullRequestDetail } from './PullRequestDetail'
import { GitHubUnavailable } from './GitHubUnavailable'

interface Props {
  prs: PullRequest[]
  githubAvailable: boolean
  fetchPrs: (state?: string) => Promise<void>
  fetchPrDetail: (number: number) => Promise<Record<string, unknown> | null>
}

type PrFilter = 'open' | 'closed' | 'all'

export function PullRequestsView({ prs, githubAvailable, fetchPrs, fetchPrDetail }: Props) {
  const [filter, setFilter] = useState<PrFilter>('open')
  const [selectedPr, setSelectedPr] = useState<number | null>(null)
  const [fetchError, setFetchError] = useState<string | null>(null)
  const [filterLoading, setFilterLoading] = useState(false)

  if (!githubAvailable) {
    return <GitHubUnavailable />
  }

  const handleFilterChange = (f: PrFilter) => {
    setFilter(f)
    setSelectedPr(null)
    setFetchError(null)
    setFilterLoading(true)
    fetchPrs(f === 'all' ? 'all' : f)
      .catch((e) => {
        setFetchError(e instanceof Error ? e.message : 'Failed to fetch pull requests')
      })
      .finally(() => setFilterLoading(false))
  }

  return (
    <div className="sc-prs">
      {fetchError && (
        <p className="sc-text-muted" style={{ color: 'var(--color-error)', padding: '8px 0' }}>{fetchError}</p>
      )}
      <div className="sc-prs__main">
        <div className="sc-filter-chips">
          {(['open', 'closed', 'all'] as PrFilter[]).map((f) => (
            <button
              key={f}
              className={`sc-filter-chip ${filter === f ? 'sc-filter-chip--active' : ''}`}
              onClick={() => handleFilterChange(f)}
              disabled={filterLoading}
            >
              {f}
            </button>
          ))}
        </div>

        {prs.length === 0 ? (
          <p className="sc-text-muted sc-prs__empty">No pull requests found</p>
        ) : (
          <table className="sc-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Title</th>
                <th>Author</th>
                <th>Branch</th>
                <th>Status</th>
                <th>Updated</th>
              </tr>
            </thead>
            <tbody>
              {prs.map((pr) => (
                <tr
                  key={pr.number}
                  className={`sc-table__row ${selectedPr === pr.number ? 'sc-table__row--selected' : ''}`}
                  onClick={() => setSelectedPr(selectedPr === pr.number ? null : pr.number)}
                >
                  <td className="sc-text-muted">{pr.number}</td>
                  <td className="sc-table__cell--name">
                    {pr.draft && <span className="sc-prs__draft-label">Draft</span>}
                    {pr.title}
                  </td>
                  <td className="sc-text-muted">{pr.author}</td>
                  <td>
                    <code className="sc-prs__branch">{pr.head_branch}</code>
                  </td>
                  <td>
                    <StatusBadge status={pr.draft ? 'draft' : pr.state} />
                  </td>
                  <td className="sc-text-muted">
                    {(() => {
                      const d = new Date(pr.updated_at)
                      return isNaN(d.getTime()) ? '-' : d.toLocaleDateString()
                    })()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {selectedPr !== null && (
        <PullRequestDetail
          prNumber={selectedPr}
          summary={prs.find((p) => p.number === selectedPr) || null}
          fetchDetail={fetchPrDetail}
          onClose={() => setSelectedPr(null)}
        />
      )}
    </div>
  )
}
