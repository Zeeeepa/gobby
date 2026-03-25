import { useState, useMemo, useCallback } from 'react'
import './ProjectsPage.css'
import { TabBar } from '../shared/TabBar'
import { useProjects } from '../../hooks/useProjects'
import { useSourceControl } from '../../hooks/useSourceControl'
import { useFilesContext } from '../../contexts/FilesContext'
import { FilesPage } from '../FilesPage'
import { CodeGraphExplorer } from '../code-graph/CodeGraphExplorer'
import { ProjectSettings } from './ProjectSettings'
import { BranchesView } from '../source-control/BranchesView'
import { PullRequestsView } from '../source-control/PullRequestsView'
import { WorktreesView } from '../source-control/WorktreesView'
import { ClonesView } from '../source-control/ClonesView'
import { CICDView } from '../source-control/CICDView'

type ProjectsTab = 'code' | 'branches' | 'prs' | 'worktrees' | 'clones' | 'cicd' | 'settings'
type CodeSubTab = 'editor' | 'graph'

const TABS = [
  { id: 'code', label: 'Project' },
  { id: 'branches', label: 'Branches' },
  { id: 'prs', label: 'Pull Requests' },
  { id: 'worktrees', label: 'Worktrees' },
  { id: 'clones', label: 'Clones' },
  { id: 'cicd', label: 'CI/CD' },
  { id: 'settings', label: 'Settings' },
]

const CODE_SUB_TABS = [
  { id: 'editor', label: 'File Editor' },
  { id: 'graph', label: 'Code Graph' },
]

interface ProjectsPageProps {
  projectId?: string | null
}

export function ProjectsPage({ projectId }: ProjectsPageProps = {}) {
  const [activeTab, setActiveTab] = useState<ProjectsTab>('code')
  const [codeSubTab, setCodeSubTab] = useState<CodeSubTab>('editor')
  const {
    allProjects,
    isLoading: _isLoading,
    selectedProject,
    updateProject,
    deleteProject,
  } = useProjects()

  const sc = useSourceControl(projectId ?? null)
  const files = useFilesContext()

  // Scope file tree to the selected project
  const scopedProjects = useMemo(
    () => projectId ? files.projects.filter(p => p.id === projectId) : files.projects,
    [projectId, files.projects]
  )

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

  const renderCodeTab = () => (
    <div className="code-page">
      <div className="code-page-header">
        <TabBar
          tabs={CODE_SUB_TABS}
          activeTab={codeSubTab}
          onTabChange={(id) => setCodeSubTab(id as CodeSubTab)}
        />
      </div>
      <div className="code-page-content">
        {codeSubTab === 'editor' && (
          scopedProjects.length > 0 ? (
            <FilesPage
              projects={scopedProjects}
              expandedDirs={files.expandedDirs}
              expandedProjects={files.expandedProjects}
              openFiles={files.openFiles}
              activeFileIndex={files.activeFileIndex}
              loadingDirs={files.loadingDirs}
              gitStatuses={files.gitStatuses}
              onExpandProject={files.expandProject}
              onExpandDir={files.expandDir}
              onOpenFile={files.openFile}
              onCloseFile={files.closeFile}
              onSetActiveFile={files.setActiveFileIndex}
              getImageUrl={files.getImageUrl}
              onToggleEditing={files.toggleEditing}
              onCancelEditing={files.cancelEditing}
              onUpdateEditContent={files.updateEditContent}
              onSaveFile={files.saveFile}
              onFetchDiff={files.fetchDiff}
            />
          ) : (
            <div className="code-page-empty">
              {projectId
                ? 'No files found for this project. Try refreshing or check the repo path.'
                : 'Select a project to browse files.'}
            </div>
          )
        )}
        {codeSubTab === 'graph' && (
          <CodeGraphExplorer projectId={projectId ?? null} />
        )}
      </div>
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
        </div>
        <TabBar
          tabs={TABS}
          activeTab={activeTab}
          onTabChange={(id) => setActiveTab(id as ProjectsTab)}
        />
      </div>

      <div className="projects-page-content">
        {activeTab === 'code' && renderCodeTab()}

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

