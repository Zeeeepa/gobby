import { useState, useCallback } from 'react'
import { useCronJobs } from '../hooks/useCronJobs'
import type { CronJob, CronRun, CreateCronJobRequest } from '../hooks/useCronJobs'
import './CronJobsPage.css'

// =============================================================================
// Helpers
// =============================================================================

function formatSchedule(job: CronJob): string {
  if (job.schedule_type === 'cron' && job.cron_expr) {
    return job.cron_expr
  }
  if (job.schedule_type === 'interval' && job.interval_seconds) {
    const s = job.interval_seconds
    if (s >= 3600) return `Every ${Math.floor(s / 3600)}h${s % 3600 ? ` ${Math.floor((s % 3600) / 60)}m` : ''}`
    if (s >= 60) return `Every ${Math.floor(s / 60)}m`
    return `Every ${s}s`
  }
  if (job.schedule_type === 'once' && job.run_at) {
    return `Once at ${new Date(job.run_at).toLocaleString()}`
  }
  return job.schedule_type
}

function formatRelativeTime(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime()
  if (diff < 0) return 'in the future'
  const mins = Math.floor(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hours = Math.floor(mins / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

function formatDuration(startedAt: string | null, completedAt: string | null): string {
  if (!startedAt || !completedAt) return '-'
  const ms = new Date(completedAt).getTime() - new Date(startedAt).getTime()
  if (ms < 1000) return `${ms}ms`
  const secs = Math.floor(ms / 1000)
  if (secs < 60) return `${secs}s`
  const mins = Math.floor(secs / 60)
  return `${mins}m ${secs % 60}s`
}

function getStatusDotClass(job: CronJob): string {
  if (!job.enabled) return 'inactive'
  if (job.consecutive_failures > 0) return 'failing'
  return 'active'
}

// =============================================================================
// Create Job Dialog
// =============================================================================

interface CreateDialogProps {
  onSubmit: (req: CreateCronJobRequest) => void
  onClose: () => void
}

function CreateJobDialog({ onSubmit, onClose }: CreateDialogProps) {
  const [name, setName] = useState('')
  const [scheduleType, setScheduleType] = useState('cron')
  const [cronExpr, setCronExpr] = useState('0 7 * * *')
  const [intervalSeconds, setIntervalSeconds] = useState('300')
  const [actionType, setActionType] = useState('shell')
  const [actionConfigStr, setActionConfigStr] = useState('{\n  "command": "echo",\n  "args": ["hello"]\n}')
  const [timezone, setTimezone] = useState('UTC')
  const [description, setDescription] = useState('')

  const handleSubmit = () => {
    if (!name.trim()) return
    let actionConfig: Record<string, unknown>
    try {
      actionConfig = JSON.parse(actionConfigStr)
    } catch {
      alert('Invalid JSON in action config')
      return
    }

    const req: CreateCronJobRequest = {
      name: name.trim(),
      action_type: actionType,
      action_config: actionConfig,
      schedule_type: scheduleType,
      timezone,
    }
    if (description.trim()) req.description = description.trim()
    if (scheduleType === 'cron') {
      if (!cronExpr.trim()) return
      req.cron_expr = cronExpr
    }
    if (scheduleType === 'interval') {
      const parsed = parseInt(intervalSeconds, 10)
      if (isNaN(parsed) || parsed <= 0) return
      req.interval_seconds = parsed
    }

    onSubmit(req)
  }

  return (
    <div className="cron-dialog-overlay" onClick={onClose}>
      <div className="cron-dialog" role="dialog" aria-modal="true" aria-labelledby="cron-dialog-title" onClick={e => e.stopPropagation()}>
        <h3 id="cron-dialog-title">Create Cron Job</h3>

        <div className="cron-form-group">
          <label className="cron-form-label">Name</label>
          <input
            className="cron-form-input"
            value={name}
            onChange={e => setName(e.target.value)}
            placeholder="My Scheduled Job"
            autoFocus
          />
        </div>

        <div className="cron-form-group">
          <label className="cron-form-label">Description</label>
          <input
            className="cron-form-input"
            value={description}
            onChange={e => setDescription(e.target.value)}
            placeholder="Optional description"
          />
        </div>

        <div className="cron-form-group">
          <label className="cron-form-label">Schedule Type</label>
          <select
            className="cron-form-select"
            value={scheduleType}
            onChange={e => setScheduleType(e.target.value)}
          >
            <option value="cron">Cron Expression</option>
            <option value="interval">Fixed Interval</option>
            <option value="once">One-shot</option>
          </select>
        </div>

        {scheduleType === 'cron' && (
          <div className="cron-form-group">
            <label className="cron-form-label">Cron Expression</label>
            <input
              className="cron-form-input"
              value={cronExpr}
              onChange={e => setCronExpr(e.target.value)}
              placeholder="0 7 * * *"
            />
          </div>
        )}

        {scheduleType === 'interval' && (
          <div className="cron-form-group">
            <label className="cron-form-label">Interval (seconds)</label>
            <input
              className="cron-form-input"
              type="number"
              value={intervalSeconds}
              onChange={e => setIntervalSeconds(e.target.value)}
              min="10"
            />
          </div>
        )}

        <div className="cron-form-group">
          <label className="cron-form-label">Timezone</label>
          <input
            className="cron-form-input"
            value={timezone}
            onChange={e => setTimezone(e.target.value)}
            placeholder="UTC"
          />
        </div>

        <div className="cron-form-group">
          <label className="cron-form-label">Action Type</label>
          <select
            className="cron-form-select"
            value={actionType}
            onChange={e => {
              setActionType(e.target.value)
              if (e.target.value === 'shell') {
                setActionConfigStr('{\n  "command": "echo",\n  "args": ["hello"]\n}')
              } else if (e.target.value === 'agent_spawn') {
                setActionConfigStr('{\n  "prompt": "...",\n  "provider": "claude",\n  "model": "sonnet",\n  "mode": "headless"\n}')
              } else {
                setActionConfigStr('{\n  "pipeline_name": "my-pipeline",\n  "inputs": {}\n}')
              }
            }}
          >
            <option value="shell">Shell Command</option>
            <option value="agent_spawn">Agent Spawn</option>
            <option value="pipeline">Pipeline</option>
          </select>
        </div>

        <div className="cron-form-group">
          <label className="cron-form-label">Action Config (JSON)</label>
          <textarea
            className="cron-form-textarea"
            value={actionConfigStr}
            onChange={e => setActionConfigStr(e.target.value)}
            rows={5}
          />
        </div>

        <div className="cron-dialog-actions">
          <button className="cron-btn" onClick={onClose}>Cancel</button>
          <button className="cron-btn primary" onClick={handleSubmit} disabled={!name.trim()}>
            Create Job
          </button>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Run History Table
// =============================================================================

function RunHistoryTable({ runs, isLoading }: { runs: CronRun[]; isLoading: boolean }) {
  if (isLoading) {
    return <div className="cron-runs-empty">Loading runs...</div>
  }
  if (runs.length === 0) {
    return <div className="cron-runs-empty">No runs yet</div>
  }

  return (
    <table className="cron-runs-table">
      <thead>
        <tr>
          <th>Triggered</th>
          <th>Status</th>
          <th>Duration</th>
          <th>Output</th>
        </tr>
      </thead>
      <tbody>
        {runs.map(run => (
          <tr key={run.id}>
            <td title={run.triggered_at}>{formatRelativeTime(run.triggered_at)}</td>
            <td>
              <span className={`cron-run-status ${run.status}`}>
                {run.status}
              </span>
            </td>
            <td>{formatDuration(run.started_at, run.completed_at)}</td>
            <td style={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
              {run.error || run.output || '-'}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  )
}

// =============================================================================
// Job Detail Panel
// =============================================================================

interface JobDetailProps {
  job: CronJob
  runs: CronRun[]
  isRunsLoading: boolean
  onToggle: () => void
  onRunNow: () => void
  onDelete: () => void
}

function JobDetail({ job, runs, isRunsLoading, onToggle, onRunNow, onDelete }: JobDetailProps) {
  const [confirmDelete, setConfirmDelete] = useState(false)

  return (
    <div className="cron-detail">
      <div className="cron-detail-header">
        <div>
          <h2 className="cron-detail-title">{job.name}</h2>
          {job.description && <p className="cron-detail-description">{job.description}</p>}
        </div>
        <div className="cron-detail-actions">
          <button className="cron-btn primary" onClick={onRunNow}>Run Now</button>
          <button className="cron-btn" onClick={onToggle}>
            {job.enabled ? 'Disable' : 'Enable'}
          </button>
          {confirmDelete ? (
            <>
              <button className="cron-btn danger" onClick={onDelete}>Confirm</button>
              <button className="cron-btn" onClick={() => setConfirmDelete(false)}>Cancel</button>
            </>
          ) : (
            <button className="cron-btn danger" onClick={() => setConfirmDelete(true)}>Delete</button>
          )}
        </div>
      </div>

      <div className="cron-info-grid">
        <div className="cron-info-card">
          <div className="cron-info-label">Schedule</div>
          <div className="cron-info-value">
            <code>{formatSchedule(job)}</code>
          </div>
        </div>
        <div className="cron-info-card">
          <div className="cron-info-label">Timezone</div>
          <div className="cron-info-value">{job.timezone}</div>
        </div>
        <div className="cron-info-card">
          <div className="cron-info-label">Status</div>
          <div className="cron-info-value">
            {job.enabled ? 'Active' : 'Disabled'}
            {job.consecutive_failures > 0 && ` (${job.consecutive_failures} failures)`}
          </div>
        </div>
        <div className="cron-info-card">
          <div className="cron-info-label">Action Type</div>
          <div className="cron-info-value">
            <span className={`cron-action-badge ${job.action_type}`}>{job.action_type}</span>
          </div>
        </div>
        <div className="cron-info-card">
          <div className="cron-info-label">Next Run</div>
          <div className="cron-info-value">
            {job.next_run_at ? new Date(job.next_run_at).toLocaleString() : '-'}
          </div>
        </div>
        <div className="cron-info-card">
          <div className="cron-info-label">Last Run</div>
          <div className="cron-info-value">
            {job.last_run_at ? formatRelativeTime(job.last_run_at) : 'Never'}
            {job.last_status && ` (${job.last_status})`}
          </div>
        </div>
      </div>

      <div className="cron-config-section">
        <h4>Action Config</h4>
        <pre className="cron-config-pre">
          {JSON.stringify(job.action_config, null, 2)}
        </pre>
      </div>

      <div className="cron-runs-section">
        <h4>Recent Runs</h4>
        <RunHistoryTable runs={runs} isLoading={isRunsLoading} />
      </div>
    </div>
  )
}

// =============================================================================
// Main Page Component
// =============================================================================

export function CronJobsPage() {
  const {
    jobs, selectedJob, selectJob, runs, filters, setFilters,
    isLoading, isRunsLoading, createJob, deleteJob, toggleJob, runNow, refresh,
  } = useCronJobs()

  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)

  const handleCreate = useCallback(async (req: CreateCronJobRequest) => {
    try {
      const job = await createJob(req)
      if (job) {
        setShowCreateDialog(false)
        selectJob(job)
      }
    } catch (e) {
      console.error('Failed to create job:', e)
      alert('Failed to create job')
    }
  }, [createJob, selectJob])

  const handleToggle = useCallback(async () => {
    try {
      if (selectedJob) await toggleJob(selectedJob.id)
    } catch (e) {
      console.error('Failed to toggle job:', e)
      alert('Failed to toggle job')
    }
  }, [selectedJob, toggleJob])

  const handleRunNow = useCallback(async () => {
    try {
      if (selectedJob) await runNow(selectedJob.id)
    } catch (e) {
      console.error('Failed to run job:', e)
      alert('Failed to run job')
    }
  }, [selectedJob, runNow])

  const handleDelete = useCallback(async () => {
    try {
      if (selectedJob) await deleteJob(selectedJob.id)
    } catch (e) {
      console.error('Failed to delete job:', e)
      alert('Failed to delete job')
    }
  }, [selectedJob, deleteJob])

  return (
    <div className="cron-page">
      {/* Left panel: job browser */}
      <div className={`cron-browser ${sidebarOpen ? '' : 'collapsed'}`}>
        <div className="cron-sidebar-header">
          {sidebarOpen && <span className="cron-sidebar-title">Cron Jobs</span>}
          <div className="cron-sidebar-actions">
            {sidebarOpen && (
              <>
                <button
                  className="terminals-action-btn"
                  onClick={() => setShowCreateDialog(true)}
                  title="Create job"
                >
                  <PlusIcon />
                </button>
                <button
                  className="terminals-action-btn"
                  onClick={refresh}
                  title="Refresh"
                  disabled={isLoading}
                >
                  <RefreshIcon />
                </button>
              </>
            )}
            <button
              className="terminals-sidebar-toggle"
              onClick={() => setSidebarOpen(!sidebarOpen)}
              title={sidebarOpen ? 'Collapse' : 'Expand'}
            >
              {sidebarOpen ? '\u25C0' : '\u25B6'}
            </button>
          </div>
        </div>

        {sidebarOpen && (
          <>
            <div className="cron-filter-bar">
              <input
                className="cron-filter-input"
                type="text"
                placeholder="Search jobs..."
                value={filters.search}
                onChange={e => setFilters({ ...filters, search: e.target.value })}
              />
              <div className="cron-filter-row">
                <select
                  className="cron-filter-select"
                  value={filters.enabled === null ? '' : String(filters.enabled)}
                  onChange={e => {
                    const val = e.target.value
                    setFilters({ ...filters, enabled: val === '' ? null : val === 'true' })
                  }}
                >
                  <option value="">All Jobs</option>
                  <option value="true">Enabled</option>
                  <option value="false">Disabled</option>
                </select>
              </div>
            </div>

            <div className="cron-job-list">
              {jobs.length === 0 && !isLoading && (
                <div className="cron-runs-empty">No cron jobs found</div>
              )}
              {isLoading && jobs.length === 0 && (
                <div className="cron-runs-empty">Loading...</div>
              )}

              {jobs.map(job => (
                <div
                  key={job.id}
                  className={`cron-job-item ${selectedJob?.id === job.id ? 'selected' : ''} ${!job.enabled ? 'disabled' : ''}`}
                  onClick={() => selectJob(job)}
                >
                  <div className="cron-job-item-header">
                    <span className={`cron-job-status-dot ${getStatusDotClass(job)}`} />
                    <span className="cron-job-name">{job.name}</span>
                  </div>
                  <div className="cron-job-item-meta">
                    <span className={`cron-action-badge ${job.action_type}`}>{job.action_type}</span>
                    <span>{formatSchedule(job)}</span>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>

      {/* Right panel: job detail or empty state */}
      <div className="cron-main">
        {selectedJob ? (
          <JobDetail
            job={selectedJob}
            runs={runs}
            isRunsLoading={isRunsLoading}
            onToggle={handleToggle}
            onRunNow={handleRunNow}
            onDelete={handleDelete}
          />
        ) : (
          <div className="cron-empty">
            <CronIcon size={48} />
            <h3>Select a cron job</h3>
            <p>Choose a job from the list to view details and run history.</p>
            {jobs.length === 0 && !isLoading && (
              <button className="cron-btn primary" onClick={() => setShowCreateDialog(true)}>
                Create Your First Job
              </button>
            )}
          </div>
        )}
      </div>

      {showCreateDialog && (
        <CreateJobDialog
          onSubmit={handleCreate}
          onClose={() => setShowCreateDialog(false)}
        />
      )}
    </div>
  )
}

// =============================================================================
// Icons
// =============================================================================

function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
  )
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" />
      <line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

function CronIcon({ size = 18 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <polyline points="12 6 12 12 16 14" />
    </svg>
  )
}
