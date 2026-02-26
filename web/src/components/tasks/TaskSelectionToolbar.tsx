import { useState } from 'react'
import { BatchLaunchAgentDialog } from './LaunchAgentDialog'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SelectedTask {
  id: string
  title: string
  category?: string | null
}

interface TaskSelectionToolbarProps {
  selectedTasks: SelectedTask[]
  projectId?: string | null
  onClearSelection: () => void
  onBatchSpawned?: (succeeded: number, failed: number) => void
}

// ---------------------------------------------------------------------------
// Icons
// ---------------------------------------------------------------------------

function RocketIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M4.5 16.5c-1.5 1.26-2 5-2 5s3.74-.5 5-2c.71-.84.7-2.13-.09-2.91a2.18 2.18 0 0 0-2.91-.09z" />
      <path d="m12 15-3-3a22 22 0 0 1 2-3.95A12.88 12.88 0 0 1 22 2c0 2.72-.78 7.5-6 11a22.35 22.35 0 0 1-4 2z" />
      <path d="M9 12H4s.55-3.03 2-4c1.62-1.08 5 0 5 0" />
      <path d="M12 15v5s3.03-.55 4-2c1.08-1.62 0-5 0-5" />
    </svg>
  )
}

// ---------------------------------------------------------------------------
// Toolbar
// ---------------------------------------------------------------------------

export function TaskSelectionToolbar({
  selectedTasks,
  projectId,
  onClearSelection,
  onBatchSpawned,
}: TaskSelectionToolbarProps) {
  const [showBatchDialog, setShowBatchDialog] = useState(false)

  if (selectedTasks.length === 0) return null

  return (
    <>
      <div className="task-selection-toolbar">
        <span className="task-selection-count">
          {selectedTasks.length} task{selectedTasks.length !== 1 ? 's' : ''} selected
        </span>
        <button
          className="task-selection-btn task-selection-btn--primary"
          onClick={() => setShowBatchDialog(true)}
        >
          <RocketIcon /> Launch Agents
        </button>
        <button
          className="task-selection-btn task-selection-btn--default"
          onClick={onClearSelection}
        >
          Clear
        </button>
      </div>

      <BatchLaunchAgentDialog
        isOpen={showBatchDialog}
        tasks={selectedTasks}
        projectId={projectId}
        onClose={() => setShowBatchDialog(false)}
        onSpawned={(succeeded, failed) => {
          setShowBatchDialog(false)
          onClearSelection()
          onBatchSpawned?.(succeeded, failed)
        }}
      />
    </>
  )
}
