import { useEffect, useRef, useState } from 'react'
import { draggable, dropTargetForElements, monitorForElements } from '@atlaskit/pragmatic-drag-and-drop/element/adapter'
import type { GobbyTask } from '../../hooks/useTasks'
import { StatusDot, PriorityBadge, TypeBadge, BlockedIndicator, PRIORITY_STYLES } from './TaskBadges'

// =============================================================================
// Column definitions: map 8 statuses → 6 columns
// =============================================================================

interface KanbanColumnDef {
  key: string
  label: string
  statuses: string[]
  /** The status to set when a card is dropped into this column */
  targetStatus: string
}

const COLUMNS: KanbanColumnDef[] = [
  { key: 'backlog',     label: 'Backlog',     statuses: ['open'],                targetStatus: 'open' },
  { key: 'in_progress', label: 'In Progress', statuses: ['in_progress'],         targetStatus: 'in_progress' },
  { key: 'review',      label: 'Review',      statuses: ['needs_review'],        targetStatus: 'needs_review' },
  { key: 'blocked',     label: 'Blocked',     statuses: ['failed', 'escalated'], targetStatus: 'failed' },
  { key: 'done',        label: 'Done',        statuses: ['approved'],            targetStatus: 'approved' },
  { key: 'closed',      label: 'Closed',      statuses: ['closed'],              targetStatus: 'closed' },
]

// =============================================================================
// KanbanCard (draggable)
// =============================================================================

const BLOCKED_STATUSES = new Set(['failed', 'escalated'])

function KanbanCard({ task, onSelect }: { task: GobbyTask; onSelect: (id: string) => void }) {
  const ref = useRef<HTMLButtonElement | null>(null)
  const [isDragging, setIsDragging] = useState(false)
  const priorityColor = (PRIORITY_STYLES[task.priority] || PRIORITY_STYLES[2]).color
  const isBlocked = BLOCKED_STATUSES.has(task.status)

  useEffect(() => {
    const el = ref.current
    if (!el || isBlocked) return
    return draggable({
      element: el,
      getInitialData: () => ({ type: 'kanban-card', taskId: task.id, currentStatus: task.status }),
      onDragStart: () => setIsDragging(true),
      onDrop: () => setIsDragging(false),
    })
  }, [task.id, task.status, isBlocked])

  const classes = [
    'kanban-card',
    isDragging ? 'kanban-card--dragging' : '',
    isBlocked ? 'kanban-card--blocked' : '',
  ].filter(Boolean).join(' ')

  return (
    <button
      ref={ref}
      className={classes}
      onClick={() => onSelect(task.id)}
      style={{ borderLeftColor: priorityColor }}
    >
      <div className="kanban-card-header">
        <span className="kanban-card-ref">{task.ref}</span>
        {isBlocked ? <BlockedIndicator /> : <PriorityBadge priority={task.priority} />}
      </div>
      <div className="kanban-card-title">{task.title}</div>
      <div className="kanban-card-footer">
        <TypeBadge type={task.type} />
      </div>
    </button>
  )
}

// =============================================================================
// KanbanColumn (drop target)
// =============================================================================

function KanbanColumnComponent({
  col,
  tasks,
  onSelectTask,
}: {
  col: KanbanColumnDef
  tasks: GobbyTask[]
  onSelectTask: (id: string) => void
}) {
  const ref = useRef<HTMLDivElement | null>(null)
  const [isDraggedOver, setIsDraggedOver] = useState(false)

  useEffect(() => {
    const el = ref.current
    if (!el) return
    return dropTargetForElements({
      element: el,
      getData: () => ({ type: 'kanban-column', columnKey: col.key, targetStatus: col.targetStatus }),
      canDrop: ({ source }) => source.data.type === 'kanban-card',
      onDragEnter: () => setIsDraggedOver(true),
      onDragLeave: () => setIsDraggedOver(false),
      onDrop: () => setIsDraggedOver(false),
    })
  }, [col.key, col.targetStatus])

  return (
    <div ref={ref} className={`kanban-column ${isDraggedOver ? 'kanban-column--drag-over' : ''}`}>
      <div className="kanban-column-header">
        <StatusDot status={col.statuses[0]} />
        <span className="kanban-column-label">{col.label}</span>
        <span className="kanban-column-count">{tasks.length}</span>
      </div>
      <div className="kanban-column-body">
        {tasks.length === 0 ? (
          <div className="kanban-column-empty">No tasks</div>
        ) : (
          tasks.map(task => (
            <KanbanCard key={task.id} task={task} onSelect={onSelectTask} />
          ))
        )}
      </div>
    </div>
  )
}

// =============================================================================
// KanbanBoard
// =============================================================================

interface KanbanBoardProps {
  tasks: GobbyTask[]
  onSelectTask: (id: string) => void
  onUpdateStatus?: (taskId: string, newStatus: string) => void
}

export function KanbanBoard({ tasks, onSelectTask, onUpdateStatus }: KanbanBoardProps) {
  // Monitor for drops globally
  useEffect(() => {
    if (!onUpdateStatus) return
    return monitorForElements({
      canMonitor: ({ source }) => source.data.type === 'kanban-card',
      onDrop: ({ source, location }) => {
        const dropTargets = location.current.dropTargets
        if (dropTargets.length === 0) return

        const target = dropTargets[0]
        if (target.data.type !== 'kanban-column') return

        const taskId = source.data.taskId as string
        const currentStatus = source.data.currentStatus as string
        const targetStatus = target.data.targetStatus as string

        if (currentStatus !== targetStatus) {
          onUpdateStatus(taskId, targetStatus)
        }
      },
    })
  }, [onUpdateStatus])

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
      {COLUMNS.map(col => (
        <KanbanColumnComponent
          key={col.key}
          col={col}
          tasks={grouped.get(col.key) || []}
          onSelectTask={onSelectTask}
        />
      ))}
    </div>
  )
}
