import { memo } from 'react'
import type { Artifact } from '../../types/artifacts'
import { ArtifactPanel } from '../chat/artifacts/ArtifactPanel'

interface ArtifactsTabProps {
  artifacts: Map<string, Artifact>
  artifact: Artifact | null
  onOpenArtifact: (id: string) => void
  onClose: () => void
  onMinimize?: () => void
  onMaximize?: () => void
  isMaximized?: boolean
  onUpdateContent?: (id: string, content: string) => void
  onSetVersion: (id: string, index: number) => void
  planPendingApproval?: boolean
  onApprovePlan?: () => void
  onRequestPlanChanges?: (feedback: string) => void
}

export const ArtifactsTab = memo(function ArtifactsTab({
  artifacts,
  artifact,
  onOpenArtifact,
  onClose,
  onMinimize,
  onMaximize,
  isMaximized,
  onUpdateContent,
  onSetVersion,
  planPendingApproval,
  onApprovePlan,
  onRequestPlanChanges,
}: ArtifactsTabProps) {
  const artifactList = Array.from(artifacts.values()).reverse()

  if (!artifact) {
    if (artifactList.length === 0) {
      return (
        <div className="activity-tab-empty">
          <p>No artifact open</p>
          <p className="text-xs text-muted-foreground mt-1">
            Artifacts appear here when code, text, or plans are generated
          </p>
        </div>
      )
    }

    return (
      <div className="flex flex-col h-full bg-background">
        <div className="flex items-center justify-between px-4 py-3 border-b border-border">
          <h2 className="text-sm font-semibold">Artifact History</h2>
          <span className="text-xs text-muted-foreground">{artifactList.length} items</span>
        </div>
        <div className="flex-1 overflow-y-auto">
          {artifactList.map((a) => (
            <button
              key={a.id}
              onClick={() => onOpenArtifact(a.id)}
              className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-muted transition-colors border-b border-border/50 group"
            >
              <div className="flex-1 min-w-0">
                <div className="text-sm font-medium truncate group-hover:text-primary transition-colors">
                  {a.title}
                </div>
                <div className="flex items-center gap-2 mt-1">
                  <span className="text-[10px] font-mono text-muted-foreground uppercase px-1.5 py-0.5 rounded bg-muted-foreground/10">
                    {a.type}
                  </span>
                  {a.language && (
                    <span className="text-[10px] text-muted-foreground font-mono">{a.language}</span>
                  )}
                  <span className="text-[10px] text-muted-foreground ml-auto">
                    v{a.versions.length}
                  </span>
                </div>
              </div>
              <ChevronRightIcon />
            </button>
          ))}
        </div>
      </div>
    )
  }

  return (
    <ArtifactPanel
      artifact={artifact}
      onClose={onClose}
      onMinimize={onMinimize}
      onMaximize={onMaximize}
      isMaximized={isMaximized}
      onBack={artifactList.length > 1 ? () => onClose() : undefined}
      onUpdateContent={onUpdateContent}
      onSetVersion={onSetVersion}
      planPendingApproval={planPendingApproval}
      onApprovePlan={onApprovePlan}
      onRequestPlanChanges={onRequestPlanChanges}
    />
  )
})

function ChevronRightIcon() {
  return (
    <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="text-muted-foreground">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  )
}
