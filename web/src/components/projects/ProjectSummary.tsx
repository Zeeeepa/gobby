import { useState, useEffect } from 'react'
import type { ProjectWithStats } from '../../hooks/useProjects'

interface ProjectSummaryProps {
  project: ProjectWithStats
}

interface TaskStats {
  open: number
  in_progress: number
  needs_review: number
  escalated: number
  closed: number
  review_approved: number
}

const STATUS_COLORS: Record<string, string> = {
  open: 'var(--accent)',
  in_progress: '#f59e0b',
  needs_review: '#8b5cf6',
  escalated: '#ef4444',
  closed: '#22c55e',
  review_approved: '#06b6d4',
}

const STATUS_LABELS: Record<string, string> = {
  open: 'Open',
  in_progress: 'In Progress',
  needs_review: 'Needs Review',
  escalated: 'Escalated',
  closed: 'Closed',
  review_approved: 'Approved',
}

export function ProjectSummary({ project }: ProjectSummaryProps) {
  const [taskStats, setTaskStats] = useState<TaskStats | null>(null)
  const [taskTotal, setTaskTotal] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/tasks?project_id=${project.id}&limit=0`, { signal: controller.signal })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (!data) return
        setTaskStats(data.stats || null)
        setTaskTotal(data.total || 0)
      })
      .catch(e => { if (e.name !== 'AbortError') console.debug('Task stats fetch failed:', e) })
    return () => controller.abort()
  }, [project.id])

  const activeStatuses = taskStats
    ? (['open', 'in_progress', 'needs_review', 'escalated', 'closed', 'review_approved'] as const).filter(s => (taskStats[s] || 0) > 0)
    : []

  return (
    <div className="projects-summary">
      <div className="projects-overview-grid">
        {/* Activity stats row */}
        <div className="projects-overview-stats-row">
          <div className="projects-summary-stat">
            <span className="projects-summary-stat-value">{project.session_count}</span>
            <span className="projects-summary-stat-label">Sessions</span>
          </div>
          <div className="projects-summary-stat">
            <span className="projects-summary-stat-value">{project.open_task_count}</span>
            <span className="projects-summary-stat-label">Open Tasks</span>
          </div>
          <div className="projects-summary-stat">
            <span className="projects-summary-stat-value">{taskTotal}</span>
            <span className="projects-summary-stat-label">Total Tasks</span>
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

        {/* Task status breakdown */}
        {taskStats && activeStatuses.length > 0 && (
          <div className="projects-summary-section">
            <h3 className="projects-summary-heading">Task Breakdown</h3>
            <div className="projects-overview-task-bar">
              {activeStatuses.map(status => {
                const count = taskStats[status] || 0
                const pct = taskTotal > 0 ? (count / taskTotal) * 100 : 0
                return (
                  <div
                    key={status}
                    className="projects-overview-task-segment"
                    style={{ width: `${Math.max(pct, 2)}%`, backgroundColor: STATUS_COLORS[status] }}
                    title={`${STATUS_LABELS[status]}: ${count}`}
                  />
                )
              })}
            </div>
            <div className="projects-overview-task-legend">
              {activeStatuses.map(status => (
                <div key={status} className="projects-overview-task-legend-item">
                  <span className="projects-overview-task-dot" style={{ backgroundColor: STATUS_COLORS[status] }} />
                  <span className="projects-overview-task-legend-label">{STATUS_LABELS[status]}</span>
                  <span className="projects-overview-task-legend-count">{taskStats[status] || 0}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Two-column layout for Details + Integrations */}
        <div className="projects-overview-two-col">
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
              <dt>GitHub</dt>
              <dd>
                {project.github_url ? (
                  <a href={project.github_url} target="_blank" rel="noopener noreferrer" className="projects-summary-link">
                    {project.github_repo || project.github_url}
                  </a>
                ) : (
                  <span className="projects-summary-empty">Not linked</span>
                )}
              </dd>

              <dt>Linear Team</dt>
              <dd>{project.linear_team_id || <span className="projects-summary-empty">Not linked</span>}</dd>
            </dl>
          </div>
        </div>
      </div>
    </div>
  )
}
