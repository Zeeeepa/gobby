import { memo } from 'react'
import type { CanvasPanelState } from '../canvas/hooks/useCanvasPanel'

interface CanvasTabProps {
  state: CanvasPanelState | null
  onClose: () => void
}

export const CanvasTab = memo(function CanvasTab({ state, onClose }: CanvasTabProps) {
  if (!state) {
    return (
      <div className="activity-tab-empty">
        <p>No canvas active</p>
        <p className="text-xs text-muted-foreground mt-1">
          Interactive surfaces appear here when generated
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between px-3 py-2 border-b border-border">
        <span className="text-sm font-medium text-foreground truncate">
          {state.title || 'Canvas'}
        </span>
        <button
          className="text-muted-foreground hover:text-foreground text-xs"
          onClick={onClose}
        >
          Close
        </button>
      </div>
      <div className="flex-1 overflow-hidden relative">
        <iframe
          src={state.url}
          sandbox="allow-scripts"
          className="absolute inset-0 w-full h-full border-0 bg-white"
          title={state.title || 'Canvas'}
        />
      </div>
    </div>
  )
})
