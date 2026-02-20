import { useState, useMemo } from 'react'
import { useSourceControl } from '../hooks/useSourceControl'
import { useSessions } from '../hooks/useSessions'
import { SourceControlOverview } from './source-control/SourceControlOverview'
import { BranchesView } from './source-control/BranchesView'
import { PullRequestsView } from './source-control/PullRequestsView'
import { WorktreesView } from './source-control/WorktreesView'
import { ClonesView } from './source-control/ClonesView'
import { CICDView } from './source-control/CICDView'

export type SubTab = 'overview' | 'branches' | 'prs' | 'worktrees' | 'clones' | 'cicd'

const TABS: { key: SubTab; label: string; requiresGitHub?: boolean }[] = [
  { key: 'overview', label: 'Overview' },
  { key: 'branches', label: 'Branches' },
  { key: 'prs', label: 'Pull Requests', requiresGitHub: true },
  { key: 'worktrees', label: 'Worktrees' },
  { key: 'clones', label: 'Clones' },
  { key: 'cicd', label: 'CI/CD', requiresGitHub: true },
]

const HIDDEN_PROJECTS = new Set(['_orphaned', '_migrated'])

export function GitHubPage() {
  const sc = useSourceControl()
  const { projects } = useSessions()
  const [activeTab, setActiveTab] = useState<SubTab>('overview')

  const projectOptions = useMemo(
    () =>
      projects
        .filter((p) => !HIDDEN_PROJECTS.has(p.name))
        .map((p) => ({
          id: p.id,
          name: p.name === '_personal' ? 'Personal' : p.name,
        })),
    [projects]
  )

  return (
    <main className="sc-page">
      <div className="sc-page__toolbar">
        <div className="sc-page__toolbar-left">
          <h2 className="sc-page__title">GitHub</h2>
          {sc.status?.current_branch && (
            <span className="sc-page__branch-badge">{sc.status.current_branch}</span>
          )}
        </div>
        <div className="sc-page__toolbar-right">
          <select
            className="sc-page__project-select"
            value={sc.projectId || ''}
            onChange={(e) => sc.setProjectId(e.target.value || null)}
          >
            <option value="">All Projects</option>
            {projectOptions.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            className="sc-page__refresh-btn"
            onClick={sc.refresh}
            title="Refresh"
            aria-label="Refresh"
          >
            <RefreshIcon />
          </button>
        </div>
      </div>

      <div className="sc-page__tabs">
        {TABS.map((tab) => {
          const disabled = tab.requiresGitHub && !sc.status?.github_available
          return (
          <button
            key={tab.key}
            className={`sc-page__tab ${activeTab === tab.key ? 'sc-page__tab--active' : ''}`}
            onClick={() => !disabled && setActiveTab(tab.key)}
            disabled={disabled}
            title={disabled ? 'Requires GitHub' : undefined}
          >
            {tab.label}
            {tab.key === 'prs' && sc.prs.length > 0 && (
              <span className="sc-page__tab-badge">{sc.prs.length}</span>
            )}
            {tab.key === 'worktrees' && sc.worktrees.length > 0 && (
              <span className="sc-page__tab-badge">{sc.worktrees.length}</span>
            )}
          </button>
        )})}
      </div>

      <div className="sc-page__content">
        {sc.isLoading && !sc.status ? (
          <div className="sc-page__loading">Loading...</div>
        ) : (
          {
            overview: (
              <SourceControlOverview
                status={sc.status}
                prs={sc.prs}
                worktrees={sc.worktrees}
                ciRuns={sc.ciRuns}
                onNavigate={setActiveTab}
                fetchCommits={sc.fetchCommits}
              />
            ),
            branches: (
              <BranchesView
                branches={sc.branches}
                currentBranch={sc.status?.current_branch || null}
                fetchCommits={sc.fetchCommits}
                fetchDiff={sc.fetchDiff}
              />
            ),
            prs: (
              <PullRequestsView
                prs={sc.prs}
                githubAvailable={sc.status?.github_available || false}
                fetchPrs={sc.fetchPrs}
                fetchPrDetail={sc.fetchPrDetail}
              />
            ),
            worktrees: (
              <WorktreesView
                worktrees={sc.worktrees}
                onDelete={sc.deleteWorktree}
                onSync={sc.syncWorktree}
                onCleanup={sc.cleanupWorktrees}
              />
            ),
            clones: (
              <ClonesView
                clones={sc.clones}
                onDelete={sc.deleteClone}
                onSync={sc.syncClone}
              />
            ),
            cicd: (
              <CICDView
                runs={sc.ciRuns}
                githubAvailable={sc.status?.github_available || false}
              />
            ),
          }[activeTab] ?? null
        )}
      </div>
    </main>
  )
}

function RefreshIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <polyline points="1 20 1 14 7 14" />
      <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15" />
    </svg>
  )
}
