import type { CIWorkflowRun } from '../../hooks/useSourceControl'
import { StatusBadge } from './StatusBadge'
import { GitHubUnavailable } from './GitHubUnavailable'

interface Props {
  runs: CIWorkflowRun[]
  githubAvailable: boolean
}

export function CICDView({ runs, githubAvailable }: Props) {
  if (!githubAvailable) {
    return <GitHubUnavailable />
  }

  return (
    <div className="sc-cicd">
      {runs.length === 0 ? (
        <p className="sc-text-muted sc-cicd__empty">No workflow runs found</p>
      ) : (
        <table className="sc-table">
          <thead>
            <tr>
              <th>Workflow</th>
              <th>Branch</th>
              <th>Status</th>
              <th>Conclusion</th>
              <th>Event</th>
              <th>Created</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="sc-table__row">
                <td className="sc-table__cell--name">{run.name}</td>
                <td>
                  <code className="sc-cicd__branch">{run.branch}</code>
                </td>
                <td>
                  <StatusBadge status={run.status} />
                </td>
                <td>
                  {run.conclusion ? (
                    <StatusBadge status={run.conclusion} />
                  ) : (
                    <span className="sc-text-muted">&mdash;</span>
                  )}
                </td>
                <td className="sc-text-muted">{run.event}</td>
                <td className="sc-text-muted">
                  {new Date(run.created_at).toLocaleDateString()}
                </td>
                <td>
                  {run.html_url && (
                    <a
                      href={run.html_url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="sc-btn sc-btn--sm"
                    >
                      View
                    </a>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
