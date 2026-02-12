import { useState, useCallback } from 'react'
import type { ProjectWithStats } from '../../hooks/useProjects'

interface ProjectSettingsProps {
  project: ProjectWithStats
  onSave: (fields: Record<string, string | null>) => Promise<boolean>
  onDelete: () => Promise<boolean>
}

export function ProjectSettings({ project, onSave, onDelete }: ProjectSettingsProps) {
  const [githubUrl, setGithubUrl] = useState(project.github_url ?? '')
  const [githubRepo, setGithubRepo] = useState(project.github_repo ?? '')
  const [linearTeamId, setLinearTeamId] = useState(project.linear_team_id ?? '')
  const [saving, setSaving] = useState(false)
  const [deleting, setDeleting] = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [message, setMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)

  const isProtected = ['_personal', '_orphaned', '_migrated', 'gobby'].includes(project.name)

  const handleSave = useCallback(async () => {
    setSaving(true)
    setMessage(null)
    const ok = await onSave({
      github_url: githubUrl || null,
      github_repo: githubRepo || null,
      linear_team_id: linearTeamId || null,
    })
    setSaving(false)
    setMessage(ok
      ? { type: 'success', text: 'Settings saved' }
      : { type: 'error', text: 'Failed to save settings' }
    )
    if (ok) setTimeout(() => setMessage(null), 3000)
  }, [githubUrl, githubRepo, linearTeamId, onSave])

  const handleDelete = useCallback(async () => {
    if (!confirmDelete) {
      setConfirmDelete(true)
      return
    }
    setDeleting(true)
    const ok = await onDelete()
    setDeleting(false)
    if (!ok) {
      setMessage({ type: 'error', text: 'Failed to delete project' })
      setConfirmDelete(false)
    }
  }, [confirmDelete, onDelete])

  return (
    <div className="projects-settings">
      <div className="projects-settings-section">
        <h3 className="projects-settings-heading">Integrations</h3>

        <label className="projects-settings-label">
          GitHub URL
          <input
            type="url"
            className="projects-settings-input"
            value={githubUrl}
            onChange={e => setGithubUrl(e.target.value)}
            placeholder="https://github.com/owner/repo"
          />
        </label>

        <label className="projects-settings-label">
          GitHub Repo (owner/repo)
          <input
            type="text"
            className="projects-settings-input"
            value={githubRepo}
            onChange={e => setGithubRepo(e.target.value)}
            placeholder="owner/repo"
          />
        </label>

        <label className="projects-settings-label">
          Linear Team ID
          <input
            type="text"
            className="projects-settings-input"
            value={linearTeamId}
            onChange={e => setLinearTeamId(e.target.value)}
            placeholder="team-id"
          />
        </label>

        <div className="projects-settings-actions">
          <button
            className="projects-settings-save"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? 'Saving...' : 'Save Changes'}
          </button>
          {message && (
            <span className={`projects-settings-message projects-settings-message--${message.type}`}>
              {message.text}
            </span>
          )}
        </div>
      </div>

      {!isProtected && (
        <div className="projects-settings-section projects-settings-danger">
          <h3 className="projects-settings-heading">Danger Zone</h3>
          <p className="projects-settings-desc">
            Deleting a project removes it from the list. Sessions and tasks remain in the database.
          </p>
          <button
            className={`projects-settings-delete ${confirmDelete ? 'projects-settings-delete--confirm' : ''}`}
            onClick={handleDelete}
            disabled={deleting}
          >
            {deleting ? 'Deleting...' : confirmDelete ? 'Click again to confirm' : 'Delete Project'}
          </button>
        </div>
      )}
    </div>
  )
}
