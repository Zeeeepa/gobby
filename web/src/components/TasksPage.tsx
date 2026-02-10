import { useState } from 'react'
import { useTasks } from '../hooks/useTasks'
import type { GobbyTask } from '../hooks/useTasks'
import { StatusDot, PriorityBadge, TypeBadge } from './tasks/TaskBadges'
import { TaskDetail } from './tasks/TaskDetail'

// =============================================================================
// Constants
// =============================================================================

type ViewMode = 'list' | 'tree' | 'kanban'

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

function PlusIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
    </svg>
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
  const { tasks, total, stats, isLoading, filters, setFilters, refreshTasks, getTask } = useTasks()
  const [viewMode, setViewMode] = useState<ViewMode>('list')
  const [selectedTaskId, setSelectedTaskId] = useState<string | null>(null)

  const hasActiveFilters = filters.status !== null || filters.priority !== null
    || filters.taskType !== null || filters.assignee !== null

  return (
    <main className="tasks-page">
      {/* Toolbar */}
      <div className="tasks-toolbar">
        <div className="tasks-toolbar-left">
          <h2 className="tasks-title">Tasks</h2>
          <span className="tasks-count">{total} total</span>
        </div>
        <div className="tasks-toolbar-right">
          <div className="tasks-view-toggle">
            {([['list', ListIcon], ['tree', TreeIcon], ['kanban', KanbanIcon]] as const).map(
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
          <button className="tasks-new-btn" title="New Task">
            <PlusIcon />
            <span>New Task</span>
          </button>
        </div>
      </div>

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
      ) : tasks.length === 0 ? (
        <div className="tasks-empty">No tasks found</div>
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
              {tasks.map(task => (
                <TaskRow key={task.id} task={task} onSelect={setSelectedTaskId} />
              ))}
            </tbody>
          </table>
        </div>
      )}

      <TaskDetail
        taskId={selectedTaskId}
        getTask={getTask}
        onClose={() => setSelectedTaskId(null)}
      />
    </main>
  )
}
