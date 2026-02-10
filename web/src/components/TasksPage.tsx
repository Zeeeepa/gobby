import { useTasks } from '../hooks/useTasks'
import type { GobbyTask } from '../hooks/useTasks'

const STATUS_COLORS: Record<string, string> = {
  open: '#3b82f6',
  in_progress: '#f59e0b',
  needs_review: '#8b5cf6',
  approved: '#22c55e',
  closed: '#737373',
  failed: '#ef4444',
  escalated: '#ef4444',
  needs_decomposition: '#f59e0b',
}

const PRIORITY_LABELS: Record<number, string> = {
  0: 'Critical',
  1: 'High',
  2: 'Medium',
  3: 'Low',
  4: 'Backlog',
}

function StatusDot({ status }: { status: string }) {
  return (
    <span
      className="tasks-status-dot"
      style={{ backgroundColor: STATUS_COLORS[status] || 'var(--color-text-muted)' }}
      title={status}
    />
  )
}

function TaskRow({ task }: { task: GobbyTask }) {
  return (
    <tr className="tasks-row">
      <td className="tasks-cell tasks-cell--status">
        <StatusDot status={task.status} />
      </td>
      <td className="tasks-cell tasks-cell--ref">
        <span className="tasks-ref">{task.ref}</span>
      </td>
      <td className="tasks-cell tasks-cell--title">{task.title}</td>
      <td className="tasks-cell tasks-cell--type">
        <span className="tasks-badge tasks-badge--type">{task.type}</span>
      </td>
      <td className="tasks-cell tasks-cell--priority">
        <span className={`tasks-badge tasks-badge--p${task.priority}`}>
          {PRIORITY_LABELS[task.priority] || `P${task.priority}`}
        </span>
      </td>
      <td className="tasks-cell tasks-cell--status-text">{task.status.replace('_', ' ')}</td>
    </tr>
  )
}

export function TasksPage() {
  const { tasks, total, stats, isLoading, filters, setFilters, refreshTasks } = useTasks()

  return (
    <main className="tasks-page">
      <div className="tasks-toolbar">
        <div className="tasks-toolbar-left">
          <h2 className="tasks-title">Tasks</h2>
          <span className="tasks-count">{total} total</span>
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
                {status.replace('_', ' ')} ({count})
              </button>
            ) : null
          )}
        </div>
        <div className="tasks-toolbar-right">
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
        </div>
      </div>

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
                <TaskRow key={task.id} task={task} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </main>
  )
}
