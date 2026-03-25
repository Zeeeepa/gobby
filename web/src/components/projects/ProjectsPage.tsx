import { useState, useMemo, useCallback } from 'react'
import './ProjectsPage.css'
import { TabBar } from '../shared/TabBar'
import { useProjects } from '../../hooks/useProjects'
import { useSourceControl } from '../../hooks/useSourceControl'
import { CodeGraphExplorer } from '../code-graph/CodeGraphExplorer'
import { ProjectSettings } from './ProjectSettings'
import { ProjectSummary } from './ProjectSummary'
import { BranchesView } from '../source-control/BranchesView'
import { PullRequestsView } from '../source-control/PullRequestsView'
import { IssuesView } from '../source-control/IssuesView'
import { WorktreesView } from '../source-control/WorktreesView'
import { ClonesView } from '../source-control/ClonesView'
import { CICDView } from '../source-control/CICDView'

type ProjectsTab = 'overview' | 'graph' | 'branches' | 'worktrees' | 'clones' | 'issues' | 'prs' | 'cicd' | 'settings'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'graph', label: 'Graph' },
  { id: 'branches', label: 'Branches' },
  { id: 'worktrees', label: 'Worktrees' },
  { id: 'clones', label: 'Clones' },
  { id: 'issues', label: 'Issues' },
  { id: 'prs', label: 'PR' },
  { id: 'cicd', label: 'CI/CD' },
  { id: 'settings', label: 'Settings' },
]

interface ProjectsPageProps {
  projectId?: string | null
}

export function ProjectsPage({ projectId }: ProjectsPageProps = {}) {
  const [activeTab, setActiveTab] = useState<ProjectsTab>('overview')
  const {
    allProjects,
    isLoading: _isLoading,
    selectedProject,
    updateProject,
    deleteProject,
  } = useProjects()

  const sc = useSourceControl(projectId ?? null)

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
          <h2 className="projects-page-title">Project</h2>
        </div>
        <TabBar
          tabs={TABS}
          activeTab={activeTab}
          onTabChange={(id) => setActiveTab(id as ProjectsTab)}
        />
      </div>

      <div className="projects-page-content">
        {activeTab === 'overview' && (
          activeProject ? (
            <ProjectSummary project={activeProject} />
          ) : (
            <div className="projects-empty">
              Select a project from the header to view overview.
            </div>
          )
        )}

        {activeTab === 'graph' && (
          <CodeGraphExplorer projectId={projectId ?? null} />
        )}

        {activeTab === 'branches' && (
          <BranchesView
            branches={sc.branches}
            currentBranch={sc.status?.current_branch || null}
            fetchCommits={sc.fetchCommits}
            fetchDiff={sc.fetchDiff}
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

        {activeTab === 'issues' && (
          <IssuesView
            issues={sc.issues}
            githubAvailable={sc.status?.github_available || false}
            fetchIssues={sc.fetchIssues}
            fetchIssueDetail={sc.fetchIssueDetail}
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
