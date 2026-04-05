import { useState, useCallback, useMemo } from 'react'
import { useCronJobs } from '../hooks/useCronJobs'
import type { CronJob, CronRun, CreateCronJobRequest, UpdateCronJobRequest } from '../hooks/useCronJobs'
import { SidebarPanel } from './shared/SidebarPanel'
import './CronJobsPage.css'

// =============================================================================
// Helpers
// =============================================================================

function getDefaultActionConfig(actionType: string): string {
  switch (actionType) {
    case 'shell':
      return '{\n  "command": "echo",\n  "args": ["hello"]\n}'
    case 'agent_spawn':
      return '{\n  "prompt": "...",\n  "provider": "claude",\n  "model": "sonnet"\n}'
    case 'pipeline':
      return '{\n  "pipeline_name": "my-pipeline",\n  "inputs": {}\n}'
    default:
      return '{}'
  }
}

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

  const isFormValid = useMemo(() => {
    if (!name.trim()) return false
    try { JSON.parse(actionConfigStr) } catch { return false }
    if (scheduleType === 'cron' && !cronExpr.trim()) return false
    if (scheduleType === 'interval') {
      const parsed = parseInt(intervalSeconds, 10)
      if (isNaN(parsed) || parsed < 10) return false
    }
    return true
  }, [name, actionConfigStr, scheduleType, cronExpr, intervalSeconds])

  const handleSubmit = () => {
    if (!isFormValid) return
    const actionConfig = JSON.parse(actionConfigStr) as Record<string, unknown>

    const req: CreateCronJobRequest = {
      name: name.trim(),
      action_type: actionType,
      action_config: actionConfig,
      schedule_type: scheduleType,
      timezone,
    }
    if (description.trim()) req.description = description.trim()
    if (scheduleType === 'cron') {
      req.cron_expr = cronExpr
    }
    if (scheduleType === 'interval') {
      req.interval_seconds = parseInt(intervalSeconds, 10)
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
              setActionConfigStr(getDefaultActionConfig(e.target.value))
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
            className="cron-form-textarea cron-form-json"
            value={actionConfigStr}
            onChange={e => setActionConfigStr(e.target.value)}
            rows={5}
          />
        </div>

        <div className="cron-dialog-actions">
          <button className="cron-btn" onClick={onClose}>Cancel</button>
          <button className="cron-btn primary" onClick={handleSubmit} disabled={!isFormValid}>
            Create Job
          </button>
        </div>
      </div>
    </div>
  )
}

// =============================================================================
// Edit Job Sidebar
// =============================================================================

interface EditJobSidebarProps {
  job: CronJob
  onSave: (req: UpdateCronJobRequest) => Promise<void>
  onClose: () => void
}

function EditJobSidebar({ job, onSave, onClose }: EditJobSidebarProps) {
  const [name, setName] = useState(job.name)
  const [description, setDescription] = useState(job.description || '')
  const [scheduleType, setScheduleType] = useState(job.schedule_type)
  const [cronExpr, setCronExpr] = useState(job.cron_expr || '0 7 * * *')
  const [intervalSeconds, setIntervalSeconds] = useState(String(job.interval_seconds || 300))
  const [timezone, setTimezone] = useState(job.timezone)
  const [actionType, setActionType] = useState(job.action_type)
  const [actionConfigStr, setActionConfigStr] = useState(JSON.stringify(job.action_config, null, 2))
  const [isSaving, setIsSaving] = useState(false)

  const isFormValid = useMemo(() => {
    if (!name.trim()) return false
    try { JSON.parse(actionConfigStr) } catch { return false }
    if (scheduleType === 'cron' && !cronExpr.trim()) return false
    if (scheduleType === 'interval') {
      const parsed = parseInt(intervalSeconds, 10)
      if (isNaN(parsed) || parsed < 10) return false
    }
    return true
  }, [name, actionConfigStr, scheduleType, cronExpr, intervalSeconds])

  const handleSave = async () => {
    if (!isFormValid || isSaving) return
    setIsSaving(true)
    try {
      const actionConfig = JSON.parse(actionConfigStr) as Record<string, unknown>
      const req: UpdateCronJobRequest = {
        name: name.trim(),
        description: description.trim() || undefined,
        schedule_type: scheduleType,
        timezone,
        action_type: actionType,
        action_config: actionConfig,
      }
      if (scheduleType === 'cron') req.cron_expr = cronExpr
      if (scheduleType === 'interval') req.interval_seconds = parseInt(intervalSeconds, 10)

      await onSave(req)
    } catch (e) {
      console.error('Failed to save job:', e)
      alert('Failed to save job')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <SidebarPanel
      isOpen
      onClose={onClose}
      title={`Edit: ${job.name}`}
      width={480}
      footer={
        <div className="cron-dialog-actions">
          <button className="cron-btn" onClick={onClose}>Cancel</button>
          <button className="cron-btn primary" onClick={handleSave} disabled={!isFormValid || isSaving}>
            {isSaving ? 'Saving...' : 'Save'}
          </button>
        </div>
      }
    >
      <div className="cron-form-group">
        <label className="cron-form-label">Name</label>
        <input className="cron-form-input" value={name} onChange={e => setName(e.target.value)} />
      </div>

      <div className="cron-form-group">
        <label className="cron-form-label">Description</label>
        <input className="cron-form-input" value={description} onChange={e => setDescription(e.target.value)} placeholder="Optional description" />
      </div>

      <div className="cron-form-group">
        <label className="cron-form-label">Schedule Type</label>
        <select className="cron-form-select" value={scheduleType} onChange={e => setScheduleType(e.target.value as CronJob['schedule_type'])}>
          <option value="cron">Cron Expression</option>
          <option value="interval">Fixed Interval</option>
          <option value="once">One-shot</option>
        </select>
      </div>

      {scheduleType === 'cron' && (
        <div className="cron-form-group">
          <label className="cron-form-label">Cron Expression</label>
          <input className="cron-form-input" value={cronExpr} onChange={e => setCronExpr(e.target.value)} placeholder="0 7 * * *" />
        </div>
      )}

      {scheduleType === 'interval' && (
        <div className="cron-form-group">
          <label className="cron-form-label">Interval (seconds)</label>
          <input className="cron-form-input" type="number" value={intervalSeconds} onChange={e => setIntervalSeconds(e.target.value)} min="10" />
        </div>
      )}

      <div className="cron-form-group">
        <label className="cron-form-label">Timezone</label>
        <input className="cron-form-input" value={timezone} onChange={e => setTimezone(e.target.value)} />
      </div>

      <div className="cron-form-group">
        <label className="cron-form-label">Action Type</label>
        <select className="cron-form-select" value={actionType} onChange={e => {
          const newType = e.target.value as CronJob['action_type']
          setActionType(newType)
          setActionConfigStr(getDefaultActionConfig(newType))
        }}>
          <option value="shell">Shell Command</option>
          <option value="agent_spawn">Agent Spawn</option>
          <option value="pipeline">Pipeline</option>
        </select>
      </div>

      <div className="cron-form-group">
        <label className="cron-form-label">Action Config (JSON)</label>
        <textarea className="cron-form-textarea cron-form-json" value={actionConfigStr} onChange={e => setActionConfigStr(e.target.value)} rows={8} />
      </div>
    </SidebarPanel>
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
  onEdit: () => void
  onDelete: () => void
}

function JobDetail({ job, runs, isRunsLoading, onToggle, onRunNow, onEdit, onDelete }: JobDetailProps) {
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
          <button className="cron-btn" onClick={onEdit}>Edit</button>
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
// Mobile Cron Drawer (top bar, replaces sidebar on small screens)
// =============================================================================

function MobileCronDrawer({
  jobs, selectedJob, onSelectJob, isLoading,
  filters, onFiltersChange,
  onCreateClick, onRefresh,
}: {
  jobs: CronJob[]
  selectedJob: CronJob | null
  onSelectJob: (job: CronJob) => void
  isLoading: boolean
  filters: { search: string; enabled: boolean | null }
  onFiltersChange: (f: { search: string; enabled: boolean | null }) => void
  onCreateClick: () => void
  onRefresh: () => void
}) {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className={`mobile-cron-drawer ${isOpen ? '' : 'collapsed'}`}>
      <div
        className="mobile-cron-drawer-header"
        onClick={() => setIsOpen(!isOpen)}
        role="button"
        tabIndex={0}
        onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); setIsOpen(!isOpen) } }}
      >
        <span className="mobile-cron-drawer-title">
          <CronIcon size={14} />
          {isOpen ? 'Cron Jobs' : (selectedJob?.name || 'Cron Jobs')}
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <button
            type="button"
            className="mobile-drawer-action"
            onClick={(e) => { e.stopPropagation(); onCreateClick() }}
            title="Create job"
          >
            <PlusIcon />
          </button>
          <button
            type="button"
            className="mobile-drawer-action"
            onClick={(e) => { e.stopPropagation(); onRefresh() }}
            title="Refresh"
            disabled={isLoading}
          >
            <RefreshIcon />
          </button>
          <span>{isOpen ? '\u25B2' : '\u25BC'}</span>
        </div>
      </div>

      {isOpen && (
        <div className="mobile-cron-drawer-content">
          <div className="cron-filter-bar">
            <input
              className="cron-filter-input"
              type="text"
              placeholder="Search jobs..."
              value={filters.search}
              onChange={e => onFiltersChange({ ...filters, search: e.target.value })}
            />
          </div>
          <div className="mobile-cron-drawer-list">
            {jobs.length === 0 && !isLoading && (
              <div className="mobile-cron-drawer-empty">No cron jobs found</div>
            )}
            {isLoading && jobs.length === 0 && (
              <div className="mobile-cron-drawer-empty">Loading...</div>
            )}
            {jobs.map(job => (
              <div
                key={job.id}
                className={`cron-job-item ${selectedJob?.id === job.id ? 'selected' : ''} ${!job.enabled ? 'disabled' : ''}`}
                onClick={() => { onSelectJob(job); setIsOpen(false) }}
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
        </div>
      )}
    </div>
  )
}

// =============================================================================
// Main Page Component
// =============================================================================

export function CronJobsPage({ projectId }: { projectId?: string | null }) {
  const {
    jobs, selectedJob, selectJob, runs, filters, setFilters,
    isLoading, isRunsLoading, createJob, updateJob, deleteJob, toggleJob, runNow, refresh,
  } = useCronJobs(projectId)

  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [showCreateDialog, setShowCreateDialog] = useState(false)
  const [editingJob, setEditingJob] = useState<CronJob | null>(null)

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

  const handleEditSave = useCallback(async (req: UpdateCronJobRequest) => {
    if (!editingJob) return
    const updated = await updateJob(editingJob.id, req)
    if (updated) {
      setEditingJob(null)
    } else {
      throw new Error('Failed to save job')
    }
  }, [editingJob, updateJob])

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
      {/* Mobile drawer (hidden on desktop via CSS) */}
      <MobileCronDrawer
        jobs={jobs}
        selectedJob={selectedJob}
        onSelectJob={selectJob}
        isLoading={isLoading}
        filters={filters}
        onFiltersChange={setFilters}
        onCreateClick={() => setShowCreateDialog(true)}
        onRefresh={refresh}
      />

      {/* Left panel: job browser (hidden on mobile via CSS) */}
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
            onEdit={() => setEditingJob(selectedJob)}
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

      {editingJob && (
        <EditJobSidebar
          key={editingJob.id}
          job={editingJob}
          onSave={handleEditSave}
          onClose={() => setEditingJob(null)}
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
