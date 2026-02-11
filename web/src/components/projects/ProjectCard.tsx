import type { ProjectWithStats } from '../../hooks/useProjects'

interface ProjectCardProps {
  project: ProjectWithStats
  onClick: () => void
}

function formatRelativeTime(dateStr: string | null): string {
  if (!dateStr) return 'No activity'
  const diff = Date.now() - new Date(dateStr).getTime()
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 30) return `${days}d ago`
  return `${Math.floor(days / 30)}mo ago`
}

export function ProjectCard({ project, onClick }: ProjectCardProps) {
  return (
    <button className="projects-card" onClick={onClick}>
      <div className="projects-card-header">
        <span className="projects-card-name">{project.display_name}</span>
        <div className="projects-card-badges">
          {project.github_repo && (
            <span className="projects-card-badge projects-card-badge--github" title={project.github_repo}>
              <GithubIcon />
            </span>
          )}
          {project.linear_team_id && (
            <span className="projects-card-badge projects-card-badge--linear" title="Linear linked">
              <LinearIcon />
            </span>
          )}
        </div>
      </div>

      {project.repo_path && (
        <div className="projects-card-path" title={project.repo_path}>
          {project.repo_path.replace(/^\/Users\/[^/]+\//, '~/')}
        </div>
      )}

      <div className="projects-card-stats">
        <span className="projects-card-stat">
          <SessionIcon />
          {project.session_count}
        </span>
        <span className="projects-card-stat">
          <TaskIcon />
          {project.open_task_count}
        </span>
        <span className="projects-card-activity">
          {formatRelativeTime(project.last_activity_at)}
        </span>
      </div>
    </button>
  )
}

function GithubIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor">
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.31 3.435 9.795 8.205 11.385.6.105.825-.255.825-.57 0-.285-.015-1.23-.015-2.235-3.015.555-3.795-.735-4.035-1.41-.135-.345-.72-1.41-1.23-1.695-.42-.225-1.02-.78-.015-.795.945-.015 1.62.87 1.845 1.23 1.08 1.815 2.805 1.305 3.495.99.105-.78.42-1.305.765-1.605-2.67-.3-5.46-1.335-5.46-5.925 0-1.305.465-2.385 1.23-3.225-.12-.3-.54-1.53.12-3.18 0 0 1.005-.315 3.3 1.23.96-.27 1.98-.405 3-.405s2.04.135 3 .405c2.295-1.56 3.3-1.23 3.3-1.23.66 1.65.24 2.88.12 3.18.765.84 1.23 1.905 1.23 3.225 0 4.605-2.805 5.625-5.475 5.925.435.375.81 1.095.81 2.22 0 1.605-.015 2.895-.015 3.3 0 .315.225.69.825.57A12.02 12.02 0 0024 12c0-6.63-5.37-12-12-12z" />
    </svg>
  )
}

function LinearIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
      <path d="M3 17l4 4M3 12l9 9M3 7l14 14M8 3l13 13M13 3l8 8M18 3l3 3" />
    </svg>
  )
}

function SessionIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="2" y="3" width="20" height="14" rx="2" ry="2" />
      <line x1="8" y1="21" x2="16" y2="21" />
      <line x1="12" y1="17" x2="12" y2="21" />
    </svg>
  )
}

function TaskIcon() {
  return (
    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 11l3 3L22 4" />
      <path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11" />
    </svg>
  )
}
