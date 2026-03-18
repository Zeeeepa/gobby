import { memo } from 'react'
import type { Artifact } from '../../types/artifacts'
import { ArtifactPanel } from '../chat/artifacts/ArtifactPanel'

interface ArtifactsTabProps {
  artifact: Artifact | null
  onClose: () => void
  onUpdateContent?: (id: string, content: string) => void
  onSetVersion: (id: string, index: number) => void
  planPendingApproval?: boolean
  onApprovePlan?: () => void
  onRequestPlanChanges?: (feedback: string) => void
}

export const ArtifactsTab = memo(function ArtifactsTab({
  artifact,
  onClose,
  onUpdateContent,
  onSetVersion,
  planPendingApproval,
  onApprovePlan,
  onRequestPlanChanges,
}: ArtifactsTabProps) {
  if (!artifact) {
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
    <ArtifactPanel
      artifact={artifact}
      onClose={onClose}
      onUpdateContent={onUpdateContent}
      onSetVersion={onSetVersion}
      planPendingApproval={planPendingApproval}
      onApprovePlan={onApprovePlan}
      onRequestPlanChanges={onRequestPlanChanges}
    />
  )
})
