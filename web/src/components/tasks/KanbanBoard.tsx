import type { GobbyTask } from '../../hooks/useTasks'
import { StatusDot, PriorityBadge, TypeBadge } from './TaskBadges'

// =============================================================================
// Column definitions: map 8 statuses → 6 columns
// =============================================================================

interface KanbanColumn {
  key: string
  label: string
  statuses: string[]
  color: string
}

const COLUMNS: KanbanColumn[] = [
  { key: 'backlog',     label: 'Backlog',     statuses: ['open'],                    color: '#3b82f6' },
  { key: 'in_progress', label: 'In Progress', statuses: ['in_progress'],             color: '#f59e0b' },
  { key: 'review',      label: 'Review',      statuses: ['needs_review'],            color: '#8b5cf6' },
  { key: 'blocked',     label: 'Blocked',     statuses: ['failed', 'escalated'],     color: '#ef4444' },
  { key: 'done',        label: 'Done',        statuses: ['approved'],                color: '#22c55e' },
  { key: 'closed',      label: 'Closed',      statuses: ['closed'],                  color: '#737373' },
]

// =============================================================================
// KanbanCard
// =============================================================================

function KanbanCard({ task, onSelect }: { task: GobbyTask; onSelect: (id: string) => void }) {
  return (
    <button className="kanban-card" onClick={() => onSelect(task.id)}>
      <div className="kanban-card-header">
        <span className="kanban-card-ref">{task.ref}</span>
        <PriorityBadge priority={task.priority} />
      </div>
      <div className="kanban-card-title">{task.title}</div>
      <div className="kanban-card-footer">
        <TypeBadge type={task.type} />
      </div>
    </button>
  )
}

// =============================================================================
// KanbanBoard
// =============================================================================

interface KanbanBoardProps {
  tasks: GobbyTask[]
  onSelectTask: (id: string) => void
}

export function KanbanBoard({ tasks, onSelectTask }: KanbanBoardProps) {
  // Group tasks by column
  const grouped = new Map<string, GobbyTask[]>()
  for (const col of COLUMNS) {
    grouped.set(col.key, [])
  }
  for (const task of tasks) {
    const col = COLUMNS.find(c => c.statuses.includes(task.status))
    if (col) {
      grouped.get(col.key)!.push(task)
    }
  }

  return (
    <div className="kanban-board">
      {COLUMNS.map(col => {
        const columnTasks = grouped.get(col.key) || []
        return (
          <div key={col.key} className="kanban-column">
            <div className="kanban-column-header">
              <StatusDot status={col.statuses[0]} />
              <span className="kanban-column-label">{col.label}</span>
              <span className="kanban-column-count">{columnTasks.length}</span>
            </div>
            <div className="kanban-column-body">
              {columnTasks.length === 0 ? (
                <div className="kanban-column-empty">No tasks</div>
              ) : (
                columnTasks.map(task => (
                  <KanbanCard key={task.id} task={task} onSelect={onSelectTask} />
                ))
              )}
            </div>
          </div>
        )
      })}
    </div>
  )
}
