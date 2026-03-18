import { useState, useCallback, useEffect } from 'react'
import { ResizeHandle } from '../chat/artifacts/ResizeHandle'
import { ArtifactsTab } from './ArtifactsTab'
import { CanvasTab } from './CanvasTab'
import { SessionsTab } from './SessionsTab'
import { PipelinesTab } from './PipelinesTab'
import { TasksTab } from './TasksTab'
import { FilesTab } from './FilesTab'
import type { Artifact } from '../../types/artifacts'
import type { CanvasPanelState } from '../canvas/hooks/useCanvasPanel'

export type ActivityTab = 'sessions' | 'pipelines' | 'tasks' | 'files' | 'artifacts' | 'canvas'

const TABS: Array<{ id: ActivityTab; label: string; icon: string }> = [
  { id: 'sessions', label: 'Sessions', icon: '\u2B24' },
  { id: 'pipelines', label: 'Pipelines', icon: '\u25B6' },
  { id: 'tasks', label: 'Tasks', icon: '\u2713' },
  { id: 'files', label: 'Files', icon: '\uD83D\uDCC1' },
  { id: 'artifacts', label: 'Artifacts', icon: '\uD83D\uDCCE' },
  { id: 'canvas', label: 'Canvas', icon: '\uD83C\uDFA8' },
]

const STORAGE_KEY_PINNED = 'gobby-activity-panel-pinned'
const STORAGE_KEY_WIDTH = 'gobby-activity-panel-width'
const STORAGE_KEY_TAB = 'gobby-activity-panel-tab'

interface ActivityPanelProps {
  isPinned: boolean
  onPinnedChange: (pinned: boolean) => void
  panelWidth: number
  onWidthChange: (width: number) => void
  activeTab: ActivityTab
  onTabChange: (tab: ActivityTab) => void
  // Artifacts tab props
  activeArtifact: Artifact | null
  onCloseArtifact: () => void
  onUpdateArtifactContent?: (id: string, content: string) => void
  onSetArtifactVersion: (id: string, index: number) => void
  planPendingApproval?: boolean
  onApprovePlan?: () => void
  onRequestPlanChanges?: (feedback: string) => void
  // Canvas tab props
  canvasState: CanvasPanelState | null
  onCloseCanvas: () => void
  // Tasks tab
  projectId?: string | null
  // Files tab
  onAddFileToChat?: (filePath: string) => void
  // Sessions tab
  onKillAgent?: (runId: string) => void
  isMobile?: boolean
}

export function ActivityPanel({
  isPinned,
  onPinnedChange,
  panelWidth,
  onWidthChange,
  activeTab,
  onTabChange,
  activeArtifact,
  onCloseArtifact,
  onUpdateArtifactContent,
  onSetArtifactVersion,
  planPendingApproval,
  onApprovePlan,
  onRequestPlanChanges,
  canvasState,
  onCloseCanvas,
  projectId,
  onAddFileToChat,
  onKillAgent,
  isMobile = false,
}: ActivityPanelProps) {
  if (!isPinned) return null

  // Mobile: close handler
  const handleClose = () => onPinnedChange(false)

  const tabContent = () => {
    switch (activeTab) {
      case 'sessions':
        return <SessionsTab onKillAgent={onKillAgent} />
      case 'pipelines':
        return <PipelinesTab projectId={projectId} />
      case 'tasks':
        return <TasksTab projectId={projectId} />
      case 'files':
        return <FilesTab projectId={projectId} onAddToChat={onAddFileToChat} />
      case 'artifacts':
        return (
          <ArtifactsTab
            artifact={activeArtifact}
            onClose={onCloseArtifact}
            onUpdateContent={onUpdateArtifactContent}
            onSetVersion={onSetArtifactVersion}
            planPendingApproval={planPendingApproval}
            onApprovePlan={onApprovePlan}
            onRequestPlanChanges={onRequestPlanChanges}
          />
        )
      case 'canvas':
        return (
          <CanvasTab
            state={canvasState}
            onClose={onCloseCanvas}
          />
        )
      default:
        return null
    }
  }

  if (isMobile) {
    return (
      <div className="activity-panel-mobile-overlay">
        <div className="activity-panel">
          {/* Tab strip with close button */}
          <div className="activity-panel-tabs">
            <div className="activity-panel-tab-strip">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  className={`activity-panel-tab${activeTab === tab.id ? ' active' : ''}`}
                  onClick={() => onTabChange(tab.id)}
                  title={tab.label}
                >
                  <span className="activity-panel-tab-icon">{tab.icon}</span>
                  <span className="activity-panel-tab-label">{tab.label}</span>
                </button>
              ))}
            </div>
            <button
              className="activity-panel-close"
              onClick={handleClose}
              title="Close panel"
            >
              {'\u2715'}
            </button>
          </div>

          {/* Tab content */}
          <div className="activity-panel-content">
            {tabContent()}
          </div>
        </div>
      </div>
    )
  }

  return (
    <>
      <ResizeHandle
        onResize={onWidthChange}
        panelWidth={panelWidth}
        minWidth={280}
        maxWidth={1200}
      />
      <div
        className="activity-panel"
        style={{ width: panelWidth, flexShrink: 0 }}
      >
        {/* Tab strip */}
        <div className="activity-panel-tabs">
          <div className="activity-panel-tab-strip">
            {TABS.map((tab) => (
              <button
                key={tab.id}
                className={`activity-panel-tab${activeTab === tab.id ? ' active' : ''}`}
                onClick={() => onTabChange(tab.id)}
                title={tab.label}
              >
                <span className="activity-panel-tab-icon">{tab.icon}</span>
                <span className="activity-panel-tab-label">{tab.label}</span>
              </button>
            ))}
          </div>
          <button
            className="activity-panel-pin"
            onClick={() => onPinnedChange(!isPinned)}
            title={isPinned ? 'Unpin panel' : 'Pin panel'}
          >
            <PinIcon pinned={isPinned} />
          </button>
        </div>

        {/* Tab content */}
        <div className="activity-panel-content">
          {tabContent()}
        </div>
      </div>
    </>
  )
}

// Hooks for persisting panel state
export function useActivityPanel() {
  const [isPinned, setIsPinned] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY_PINNED)
      if (stored !== null) return stored === 'true'
    } catch { /* ignore */ }
    // Default: pinned on desktop
    return window.innerWidth >= 1100
  })

  const [panelWidth, setPanelWidth] = useState(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY_WIDTH)
      if (stored) {
        const w = parseInt(stored, 10)
        if (w >= 280 && w <= 1200) return w
      }
    } catch { /* ignore */ }
    return 360
  })

  const [activeTab, setActiveTab] = useState<ActivityTab>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY_TAB) as ActivityTab | null
      if (stored && TABS.some((t) => t.id === stored)) return stored
    } catch { /* ignore */ }
    return 'tasks'
  })

  // Persist
  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY_PINNED, String(isPinned)) } catch { /* ignore */ }
  }, [isPinned])

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY_WIDTH, String(panelWidth)) } catch { /* ignore */ }
  }, [panelWidth])

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY_TAB, activeTab) } catch { /* ignore */ }
  }, [activeTab])

  // Auto-collapse on narrow viewport
  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 1100 && isPinned) {
        setIsPinned(false)
      }
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [isPinned])

  const showTab = useCallback((tab: ActivityTab) => {
    setActiveTab(tab)
    if (!isPinned) setIsPinned(true)
  }, [isPinned])

  const togglePanel = useCallback(() => {
    setIsPinned((prev) => !prev)
  }, [])

  return {
    isPinned,
    setIsPinned,
    panelWidth,
    setPanelWidth,
    activeTab,
    setActiveTab,
    showTab,
    togglePanel,
  }
}

function PinIcon({ pinned }: { pinned: boolean }) {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ transform: pinned ? 'rotate(45deg)' : undefined }}>
      <line x1="12" y1="17" x2="12" y2="22" />
      <path d="M5 17h14v-1.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V6h1a2 2 0 0 0 0-4H8a2 2 0 0 0 0 4h1v4.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24Z" />
    </svg>
  )
}
