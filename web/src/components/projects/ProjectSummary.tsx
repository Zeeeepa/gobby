import type { ProjectWithStats } from '../../hooks/useProjects'

interface ProjectSummaryProps {
  project: ProjectWithStats
}

export function ProjectSummary({ project }: ProjectSummaryProps) {
  return (
    <div className="projects-summary">
      <div className="projects-summary-grid">
        <div className="projects-summary-section">
          <h3 className="projects-summary-heading">Details</h3>
          <dl className="projects-summary-dl">
            <dt>Name</dt>
            <dd>{project.display_name}</dd>

            <dt>Repository Path</dt>
            <dd>{project.repo_path || <span className="projects-summary-empty">Not configured</span>}</dd>

            <dt>Created</dt>
            <dd>{new Date(project.created_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}</dd>

            <dt>Last Updated</dt>
            <dd>{new Date(project.updated_at).toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })}</dd>
          </dl>
        </div>

        <div className="projects-summary-section">
          <h3 className="projects-summary-heading">Integrations</h3>
          <dl className="projects-summary-dl">
            <dt>GitHub URL</dt>
            <dd>
              {project.github_url ? (
                <a href={project.github_url} target="_blank" rel="noopener noreferrer" className="projects-summary-link">
                  {project.github_url}
                </a>
              ) : (
                <span className="projects-summary-empty">Not linked</span>
              )}
            </dd>

            <dt>GitHub Repo</dt>
            <dd>{project.github_repo || <span className="projects-summary-empty">Not set</span>}</dd>

            <dt>Linear Team</dt>
            <dd>{project.linear_team_id || <span className="projects-summary-empty">Not linked</span>}</dd>
          </dl>
        </div>

        <div className="projects-summary-section">
          <h3 className="projects-summary-heading">Activity</h3>
          <div className="projects-summary-stats">
            <div className="projects-summary-stat">
              <span className="projects-summary-stat-value">{project.session_count}</span>
              <span className="projects-summary-stat-label">Sessions</span>
            </div>
            <div className="projects-summary-stat">
              <span className="projects-summary-stat-value">{project.open_task_count}</span>
              <span className="projects-summary-stat-label">Open Tasks</span>
            </div>
            <div className="projects-summary-stat">
              <span className="projects-summary-stat-value">
                {project.last_activity_at
                  ? new Date(project.last_activity_at).toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
                  : '—'}
              </span>
              <span className="projects-summary-stat-label">Last Activity</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
