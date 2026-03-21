import { useState, useMemo, useCallback } from 'react'
import './ProjectsPage.css'
import { TabBar } from '../shared/TabBar'
import { useProjects } from '../../hooks/useProjects'
import type { ProjectWithStats } from '../../hooks/useProjects'
import { useSourceControl } from '../../hooks/useSourceControl'
import { ProjectOverview } from './ProjectOverview'
import { ProjectCard } from './ProjectCard'
import { ProjectSettings } from './ProjectSettings'
import { ProjectSummary } from './ProjectSummary'
import { SourceControlOverview } from '../source-control/SourceControlOverview'
import { BranchesView } from '../source-control/BranchesView'
import { PullRequestsView } from '../source-control/PullRequestsView'
import { WorktreesView } from '../source-control/WorktreesView'
import { ClonesView } from '../source-control/ClonesView'
import { CICDView } from '../source-control/CICDView'

type ProjectsTab = 'overview' | 'branches' | 'prs' | 'worktrees' | 'clones' | 'cicd' | 'settings'
type OverviewFilter = 'total' | 'active' | 'tasks' | null
type ViewMode = 'cards' | 'list'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'branches', label: 'Branches' },
  { id: 'prs', label: 'Pull Requests' },
  { id: 'worktrees', label: 'Worktrees' },
  { id: 'clones', label: 'Clones' },
  { id: 'cicd', label: 'CI/CD' },
  { id: 'settings', label: 'Settings' },
]

interface ProjectsPageProps {
  projectId?: string | null
}

function CardsIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <rect x="1" y="1" width="5" height="5" rx="1" />
      <rect x="8" y="1" width="5" height="5" rx="1" />
      <rect x="1" y="8" width="5" height="5" rx="1" />
      <rect x="8" y="8" width="5" height="5" rx="1" />
    </svg>
  )
}

function ListIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <line x1="3" y1="3" x2="11" y2="3" />
      <line x1="3" y1="7" x2="11" y2="7" />
      <line x1="3" y1="11" x2="11" y2="11" />
    </svg>
  )
}

export function ProjectsPage({ projectId }: ProjectsPageProps = {}) {
  const [activeTab, setActiveTab] = useState<ProjectsTab>('overview')
  const {
    projects,
    allProjects,
    isLoading,
    selectedProject,
    searchText,
    setSearchText,
    selectProject,
    deselectProject,
    updateProject,
    deleteProject,
    refresh,
    totalSessions,
    totalOpenTasks,
  } = useProjects()

  const sc = useSourceControl(projectId ?? null)

  const [viewMode, setViewMode] = useState<ViewMode>('cards')
  const [overviewFilter, setOverviewFilter] = useState<OverviewFilter>(null)

  const displayProjects = useMemo(() => {
    if (!overviewFilter) return projects
    if (overviewFilter === 'active') return projects.filter(p => p.session_count > 0)
    if (overviewFilter === 'tasks') return projects.filter(p => p.open_task_count > 0)
    return projects
  }, [projects, overviewFilter])

  // Find the project matching the global selector for settings
  const activeProject = useMemo(() => {
    if (selectedProject) return selectedProject
    if (projectId) return allProjects.find(p => p.id === projectId) ?? null
    return null
  }, [selectedProject, projectId, allProjects])

  const handleSave = useCallback(async (fields: Record<string, string | null>) => {
    if (!activeProject) return false
    return updateProject(activeProject.id, fields)
  }, [activeProject, updateProject])

  const handleDelete = useCallback(async () => {
    if (!activeProject) return false
    return deleteProject(activeProject.id)
  }, [activeProject, deleteProject])

  const renderOverviewTab = () => (
    <div className="projects-overview-tab">
      {/* Project cards toolbar */}
      <div className="projects-toolbar">
        <div className="projects-toolbar-left">
          <span className="projects-toolbar-count">{allProjects.length} projects</span>
        </div>
        <div className="projects-toolbar-right">
          <div className="projects-view-toggle">
            <button
              className={`projects-view-btn ${viewMode === 'cards' ? 'active' : ''}`}
              onClick={() => setViewMode('cards')}
              title="Card view"
            >
              <CardsIcon />
            </button>
            <button
              className={`projects-view-btn ${viewMode === 'list' ? 'active' : ''}`}
              onClick={() => setViewMode('list')}
              title="List view"
            >
              <ListIcon />
            </button>
          </div>
          <input
            className="projects-search"
            type="text"
            placeholder="Search..."
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
          />
          <button
            className="projects-toolbar-btn"
            onClick={refresh}
            title="Refresh"
            disabled={isLoading}
          >
            &#x21bb;
          </button>
        </div>
      </div>

      {/* Stats */}
      <ProjectOverview
        projects={allProjects}
        totalSessions={totalSessions}
        totalOpenTasks={totalOpenTasks}
        activeFilter={overviewFilter}
        onFilter={f => setOverviewFilter(f as OverviewFilter)}
      />

      {/* Project cards/list */}
      <div className="projects-content">
        {isLoading && displayProjects.length === 0 ? (
          <div className="projects-loading">Loading projects...</div>
        ) : displayProjects.length === 0 ? (
          <div className="projects-empty">
            {searchText ? 'No projects match your search.' : 'No projects found.'}
          </div>
        ) : viewMode === 'cards' ? (
          <div className="projects-grid">
            {displayProjects.map(p => (
              <ProjectCard
                key={p.id}
                project={p}
                onClick={() => selectProject(p.id)}
              />
            ))}
          </div>
        ) : (
          <div className="projects-list">
            {displayProjects.map(p => (
              <ProjectListRow
                key={p.id}
                project={p}
                onClick={() => selectProject(p.id)}
              />
            ))}
          </div>
        )}
      </div>

      {/* Selected project detail */}
      {selectedProject && (
        <div className="projects-selected-detail">
          <div className="projects-selected-header">
            <button className="projects-selected-close" onClick={deselectProject}>&times;</button>
            <span className="projects-selected-name">{selectedProject.display_name}</span>
          </div>
          <ProjectSummary project={selectedProject} />
        </div>
      )}
    </div>
  )

  const renderSettingsTab = () => {
    if (!activeProject) {
      return (
        <div className="projects-empty">
          Select a project from the header to configure settings.
        </div>
      )
    }
    return (
      <ProjectSettings
        project={activeProject}
        onSave={handleSave}
        onDelete={handleDelete}
      />
    )
  }

  return (
    <main className="projects-page">
      <div className="projects-page-header">
        <div className="projects-page-title-row">
          <h2 className="projects-page-title">Projects</h2>
          {sc.status?.current_branch && (
            <span className="sc-page__branch-badge">{sc.status.current_branch}</span>
          )}
        </div>
        <TabBar
          tabs={TABS}
          activeTab={activeTab}
          onTabChange={(id) => setActiveTab(id as ProjectsTab)}
        />
      </div>

      <div className="projects-page-content">
        {activeTab === 'overview' && renderOverviewTab()}

        {activeTab === 'branches' && (
          <BranchesView
            branches={sc.branches}
            currentBranch={sc.status?.current_branch || null}
            fetchCommits={sc.fetchCommits}
            fetchDiff={sc.fetchDiff}
          />
        )}

        {activeTab === 'prs' && (
          <PullRequestsView
            prs={sc.prs}
            githubAvailable={sc.status?.github_available || false}
            fetchPrs={sc.fetchPrs}
            fetchPrDetail={sc.fetchPrDetail}
          />
        )}

        {activeTab === 'worktrees' && (
          <WorktreesView
            worktrees={sc.worktrees}
            onDelete={sc.deleteWorktree}
            onSync={sc.syncWorktree}
            onCleanup={sc.cleanupWorktrees}
          />
        )}

        {activeTab === 'clones' && (
          <ClonesView
            clones={sc.clones}
            onDelete={sc.deleteClone}
            onSync={sc.syncClone}
          />
        )}

        {activeTab === 'cicd' && (
          <CICDView
            runs={sc.ciRuns}
            githubAvailable={sc.status?.github_available || false}
          />
        )}

        {activeTab === 'settings' && renderSettingsTab()}
      </div>
    </main>
  )
}

function ProjectListRow({ project, onClick }: { project: ProjectWithStats; onClick: () => void }) {
  return (
    <button className="projects-list-row" onClick={onClick}>
      <span className="projects-list-name">{project.display_name}</span>
      <span className="projects-list-path">
        {project.repo_path?.replace(/^\/Users\/[^/]+\//, '~/') ?? ''}
      </span>
      <span className="projects-list-stat">{project.session_count} sessions</span>
      <span className="projects-list-stat">{project.open_task_count} tasks</span>
      <span className="projects-list-activity">
        {project.last_activity_at
          ? new Date(project.last_activity_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
          : '—'}
      </span>
    </button>
  )
}
