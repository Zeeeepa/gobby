import { useState, useMemo, useCallback } from 'react'
import { useTasks } from '../hooks/useTasks'
import type { GobbyTask, GobbyTaskDetail } from '../hooks/useTasks'
import { StatusDot, PriorityBadge, TypeBadge } from './tasks/TaskBadges'
import { TaskDetail } from './tasks/TaskDetail'
import { TaskCreateForm } from './tasks/TaskCreateForm'
import type { TaskCreateDefaults } from './tasks/TaskCreateForm'
import { KanbanBoard } from './tasks/KanbanBoard'
import { TaskTree } from './tasks/TaskTree'
import { PriorityBoard } from './tasks/PriorityBoard'
import { TaskOverview } from './tasks/TaskOverview'
import { AuditLog } from './tasks/AuditLog'
import { GanttChart } from './tasks/GanttChart'
import { DigestView } from './tasks/DigestView'

// =============================================================================
// Constants
// =============================================================================

type ViewMode = 'list' | 'tree' | 'kanban' | 'priority' | 'audit' | 'gantt' | 'digest'

const STATUS_OPTIONS = [
  'open', 'in_progress', 'needs_review', 'approved', 'closed', 'failed', 'escalated',
]

const TYPE_OPTIONS = ['task', 'bug', 'feature', 'epic', 'chore']

const PRIORITY_OPTIONS = [
  { value: 0, label: 'Critical' },
  { value: 1, label: 'High' },
  { value: 2, label: 'Medium' },
  { value: 3, label: 'Low' },
  { value: 4, label: 'Backlog' },
]

// =============================================================================
// View toggle icons
// =============================================================================

function ListIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="8" y1="6" x2="21" y2="6" /><line x1="8" y1="12" x2="21" y2="12" /><line x1="8" y1="18" x2="21" y2="18" />
      <line x1="3" y1="6" x2="3.01" y2="6" /><line x1="3" y1="12" x2="3.01" y2="12" /><line x1="3" y1="18" x2="3.01" y2="18" />
    </svg>
  )
}

function TreeIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 3v12" /><path d="M18 9a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" />
      <path d="M6 21a3 3 0 1 0 0-6 3 3 0 0 0 0 6z" /><path d="M15 6a9 9 0 0 0-9 9" />
    </svg>
  )
}

function KanbanIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="5" height="18" rx="1" /><rect x="10" y="3" width="5" height="12" rx="1" /><rect x="17" y="3" width="5" height="15" rx="1" />
    </svg>
  )
}

function PriorityIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4 15s1-1 4-1 5 2 8 2 4-1 4-1V3s-1 1-4 1-5-2-8-2-4 1-4 1z" />
      <line x1="4" y1="22" x2="4" y2="15" />
    </svg>
  )
}

function AuditIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" /><line x1="16" y1="17" x2="8" y2="17" /><polyline points="10 9 9 9 8 9" />
    </svg>
  )
}

function GanttIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="12" height="4" rx="1" />
      <rect x="7" y="10" width="14" height="4" rx="1" />
      <rect x="5" y="16" width="10" height="4" rx="1" />
    </svg>
  )
}

function DigestIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="3" width="18" height="18" rx="2" />
      <line x1="7" y1="8" x2="17" y2="8" />
      <line x1="7" y1="12" x2="13" y2="12" />
      <line x1="7" y1="16" x2="15" y2="16" />
    </svg>
  )
}

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
    </svg>
  )
}

// =============================================================================
// Role-based scope
// =============================================================================

type TaskScope = 'all' | 'mine'

const SCOPE_STORAGE_KEY = 'gobby-task-scope'
const IDENTITY_STORAGE_KEY = 'gobby-my-identity'

function getStoredScope(): TaskScope {
  try {
    const v = localStorage.getItem(SCOPE_STORAGE_KEY)
    if (v === 'mine') return 'mine'
  } catch { /* noop */ }
  return 'all'
}

function storeScope(scope: TaskScope) {
  try { localStorage.setItem(SCOPE_STORAGE_KEY, scope) } catch { /* noop */ }
}

function getStoredIdentity(): string {
  try { return localStorage.getItem(IDENTITY_STORAGE_KEY) || '' } catch { return '' }
}

function storeIdentity(id: string) {
  try { localStorage.setItem(IDENTITY_STORAGE_KEY, id) } catch { /* noop */ }
}

function matchesIdentity(task: GobbyTask, identity: string): boolean {
  if (!identity) return false
  const lower = identity.toLowerCase()
  // Match by assignee (session ID prefix or full match)
  if (task.assignee && task.assignee.toLowerCase().includes(lower)) return true
  // Match by agent_name
  if (task.agent_name && task.agent_name.toLowerCase().includes(lower)) return true
  return false
}

function ScopeToggle({
  scope,
  identity,
  onScopeChange,
  onIdentityChange,
}: {
  scope: TaskScope
  identity: string
  onScopeChange: (s: TaskScope) => void
  onIdentityChange: (id: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(identity)

  return (
    <div className="task-scope-toggle">
      <button
        className={`task-scope-btn ${scope === 'all' ? 'active' : ''}`}
        onClick={() => onScopeChange('all')}
      >
        All Tasks
      </button>
      <button
        className={`task-scope-btn ${scope === 'mine' ? 'active' : ''}`}
        onClick={() => onScopeChange('mine')}
      >
        My Tasks
      </button>
      {scope === 'mine' && (
        <div className="task-scope-identity">
          {editing ? (
            <input
              className="task-scope-identity-input"
              value={draft}
              onChange={e => setDraft(e.target.value)}
              onBlur={() => { onIdentityChange(draft.trim()); setEditing(false) }}
              onKeyDown={e => {
                if (e.key === 'Enter') { onIdentityChange(draft.trim()); setEditing(false) }
                if (e.key === 'Escape') { setDraft(identity); setEditing(false) }
              }}
              placeholder="Session ID or agent name..."
              autoFocus
            />
          ) : (
            <button
              className="task-scope-identity-badge"
              onClick={() => { setDraft(identity); setEditing(true) }}
              title="Click to change identity"
            >
              {identity || 'Set identity...'}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// =============================================================================
// TaskRow
// =============================================================================

function TaskRow({ task, onSelect }: { task: GobbyTask; onSelect: (id: string) => void }) {
  return (
    <tr className="tasks-row" onClick={() => onSelect(task.id)} style={{ cursor: 'pointer' }}>
      <td className="tasks-cell tasks-cell--status">
        <StatusDot status={task.status} />
      </td>
      <td className="tasks-cell tasks-cell--ref">
        <span className="tasks-ref">{task.ref}</span>
      </td>
      <td className="tasks-cell tasks-cell--title">{task.title}</td>
      <td className="tasks-cell tasks-cell--type">
        <TypeBadge type={task.type} />
      </td>
      <td className="tasks-cell tasks-cell--priority">
        <PriorityBadge priority={task.priority} />
      </td>
      <td className="tasks-cell tasks-cell--status-text">{task.status.replace(/_/g, ' ')}</td>
    </tr>
  )
}

// =============================================================================
// TasksPage
// =============================================================================

export function TasksPage() {
  const { tasks, total, stats, isLoading, filters, setFilters, refreshTasks, getTask, createTask, updateTask, closeTask, reopenTask, getDependencies, getSubtasks } = useTasks()
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [cloneDefaults, setCloneDefaults] = useState<TaskCreateDefaults | null>(null)
  const [scope, setScope] = useState<TaskScope>(getStoredScope)
  const [myIdentity, setMyIdentity] = useState(getStoredIdentity)

  const handleScopeChange = useCallback((s: TaskScope) => {
    setScope(s)
    storeScope(s)
  }, [])

  const handleIdentityChange = useCallback((id: string) => {
    setMyIdentity(id)
    storeIdentity(id)
  }, [])

  // Apply role-based scope filter
  const scopedTasks = useMemo(() => {
    if (scope !== 'mine' || !myIdentity) return tasks
    return tasks.filter(t => matchesIdentity(t, myIdentity))
  }, [tasks, scope, myIdentity])

  const hasActiveFilters = filters.status !== null || filters.priority !== null
    || filters.taskType !== null || filters.assignee !== null

  // Context-aware defaults for task creation
  const createDefaults = useMemo((): TaskCreateDefaults => {
    // Clone defaults take priority when set
    if (cloneDefaults) return cloneDefaults

    const defaults: TaskCreateDefaults = {}
    // Pre-fill type from active filter
    if (filters.taskType) defaults.taskType = filters.taskType
    // Pre-fill priority from active filter
    if (filters.priority !== null) defaults.priority = filters.priority
    // Pre-fill parent from selected task (if it's an epic/task)
    if (selectedTaskId) {
      const selected = tasks.find(t => t.id === selectedTaskId)
      if (selected && (selected.type === 'epic' || selected.type === 'task')) {
        defaults.parentTaskId = selectedTaskId
      }
    }
    return defaults
  }, [filters.taskType, filters.priority, selectedTaskId, tasks, cloneDefaults])

  const handleClone = useCallback((task: GobbyTaskDetail) => {
    setCloneDefaults({
      title: `[Clone] ${task.title}`,
      description: task.description || undefined,
      taskType: task.type,
      priority: task.priority,
      validationCriteria: task.validation_criteria || undefined,
      labels: task.labels || undefined,
      parentTaskId: task.parent_task_id || undefined,
    })
    setShowCreateForm(true)
  }, [])

  return (
    <main className="tasks-page">
      {/* Toolbar */}
      <div className="tasks-toolbar">
        <div className="tasks-toolbar-left">
          <h2 className="tasks-title">Tasks</h2>
          <span className="tasks-count">{scope === 'mine' && myIdentity ? `${scopedTasks.length} of ${total}` : `${total} total`}</span>
          <ScopeToggle
            scope={scope}
            identity={myIdentity}
            onScopeChange={handleScopeChange}
            onIdentityChange={handleIdentityChange}
          />
        </div>
        <div className="tasks-toolbar-right">
          <div className="tasks-view-toggle">
            {([['list', ListIcon], ['tree', TreeIcon], ['kanban', KanbanIcon], ['priority', PriorityIcon], ['audit', AuditIcon], ['gantt', GanttIcon], ['digest', DigestIcon]] as const).map(
              ([mode, Icon]) => (
                <button
                  key={mode}
                  className={`tasks-view-btn ${viewMode === mode ? 'active' : ''}`}
                  onClick={() => setViewMode(mode as ViewMode)}
                  title={`${mode.charAt(0).toUpperCase() + mode.slice(1)} view`}
                >
                  <Icon />
                </button>
              )
            )}
          </div>
          <input
            type="text"
            className="tasks-search"
            placeholder="Search tasks..."
            value={filters.search}
            onChange={e => setFilters(f => ({ ...f, search: e.target.value }))}
          />
          <button className="tasks-refresh-btn" onClick={refreshTasks} title="Refresh">
            ↻
          </button>
          <button className="tasks-new-btn" title="New Task" onClick={() => setShowCreateForm(true)}>
            <PlusIcon />
            <span>New Task</span>
          </button>
        </div>
      </div>

      {/* Overview cards */}
      <TaskOverview
        tasks={scopedTasks}
        stats={stats}
        activeFilter={filters.status}
        onFilterStatus={status => setFilters(f => ({ ...f, status }))}
      />

      {/* Filter bar */}
      <div className="tasks-filter-bar">
        <div className="tasks-filter-chips">
          {Object.entries(stats).map(([status, count]) =>
            count > 0 ? (
              <button
                key={status}
                className={`tasks-stat-chip ${filters.status === status ? 'active' : ''}`}
                onClick={() =>
                  setFilters(f => ({ ...f, status: f.status === status ? null : status }))
                }
              >
                <StatusDot status={status} />
                {status.replace(/_/g, ' ')} ({count})
              </button>
            ) : null
          )}
        </div>
        <div className="tasks-filter-dropdowns">
          <select
            className="tasks-filter-select"
            value={filters.priority ?? ''}
            onChange={e =>
              setFilters(f => ({
                ...f,
                priority: e.target.value === '' ? null : Number(e.target.value),
              }))
            }
          >
            <option value="">All Priorities</option>
            {PRIORITY_OPTIONS.map(p => (
              <option key={p.value} value={p.value}>{p.label}</option>
            ))}
          </select>
          <select
            className="tasks-filter-select"
            value={filters.taskType ?? ''}
            onChange={e =>
              setFilters(f => ({ ...f, taskType: e.target.value || null }))
            }
          >
            <option value="">All Types</option>
            {TYPE_OPTIONS.map(t => (
              <option key={t} value={t}>{t}</option>
            ))}
          </select>
          <select
            className="tasks-filter-select"
            value={filters.status ?? ''}
            onChange={e =>
              setFilters(f => ({ ...f, status: e.target.value || null }))
            }
          >
            <option value="">All Statuses</option>
            {STATUS_OPTIONS.map(s => (
              <option key={s} value={s}>{s.replace(/_/g, ' ')}</option>
            ))}
          </select>
          {hasActiveFilters && (
            <button
              className="tasks-filter-clear"
              onClick={() =>
                setFilters(f => ({
                  ...f,
                  status: null,
                  priority: null,
                  taskType: null,
                  assignee: null,
                }))
              }
            >
              Clear filters
            </button>
          )}
        </div>
      </div>

      {/* Content */}
      {isLoading ? (
        <div className="tasks-loading">Loading tasks...</div>
      ) : scopedTasks.length === 0 ? (
        <div className="tasks-empty">{scope === 'mine' ? 'No tasks matching your identity' : 'No tasks found'}</div>
      ) : viewMode === 'digest' ? (
        <DigestView
          tasks={scopedTasks}
          onSelectTask={setSelectedTaskId}
        />
      ) : viewMode === 'gantt' ? (
        <GanttChart
          tasks={scopedTasks}
          onSelectTask={setSelectedTaskId}
          onReschedule={(taskId, offsetDays) => {
            // Persist position change via sequence_order (offset * 1000 for granularity)
            const task = scopedTasks.find(t => t.id === taskId)
            const currentOrder = task?.sequence_order ?? 0
            updateTask(taskId, { sequence_order: currentOrder + offsetDays * 1000 })
          }}
        />
      ) : viewMode === 'audit' ? (
        <AuditLog
          tasks={scopedTasks}
          onSelectTask={setSelectedTaskId}
        />
      ) : viewMode === 'priority' ? (
        <PriorityBoard
          tasks={scopedTasks}
          onSelectTask={setSelectedTaskId}
          onUpdateStatus={(taskId, newStatus) => updateTask(taskId, { status: newStatus })}
        />
      ) : viewMode === 'kanban' ? (
        <KanbanBoard
          tasks={scopedTasks}
          onSelectTask={setSelectedTaskId}
          onUpdateStatus={(taskId, newStatus) => updateTask(taskId, { status: newStatus })}
          onReorder={(taskId, newOrder) => updateTask(taskId, { sequence_order: newOrder })}
        />
      ) : viewMode === 'tree' ? (
        <TaskTree
          tasks={scopedTasks}
          onSelectTask={setSelectedTaskId}
          onReparent={(taskId, newParentId) => updateTask(taskId, { parent_task_id: newParentId || '' })}
        />
      ) : (
        <div className="tasks-table-container">
          <table className="tasks-table">
            <thead>
              <tr>
                <th className="tasks-th" style={{ width: 28 }}></th>
                <th className="tasks-th" style={{ width: 64 }}>Ref</th>
                <th className="tasks-th">Title</th>
                <th className="tasks-th" style={{ width: 80 }}>Type</th>
                <th className="tasks-th" style={{ width: 80 }}>Priority</th>
                <th className="tasks-th" style={{ width: 100 }}>Status</th>
              </tr>
            </thead>
            <tbody>
              {scopedTasks.map(task => (
                <TaskRow key={task.id} task={task} onSelect={setSelectedTaskId} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <TaskDetail
        taskId={selectedTaskId}
        getTask={getTask}
        getDependencies={getDependencies}
        getSubtasks={getSubtasks}
        actions={{ updateTask, closeTask, reopenTask }}
        onSelectTask={setSelectedTaskId}
        onClose={() => setSelectedTaskId(null)}
        onClone={handleClone}
      />

      <TaskCreateForm
        isOpen={showCreateForm}
        tasks={tasks}
        defaults={createDefaults}
        onSubmit={createTask}
        onClose={() => { setShowCreateForm(false); setCloneDefaults(null) }}
      />
    </main>
  )
}
