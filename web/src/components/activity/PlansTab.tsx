import { memo, useEffect } from 'react'
import type { Artifact } from '../../types/artifacts'
import { ArtifactPanel } from '../chat/artifacts/ArtifactPanel'

interface PlansTabProps {
  artifacts: Map<string, Artifact>
  artifact: Artifact | null
  onOpenArtifact: (id: string) => void
  onClose: () => void
  onUpdateContent?: (id: string, content: string) => void
  onSetVersion: (id: string, index: number) => void
  planPendingApproval?: boolean
  onApprovePlan?: () => void
  onRequestPlanChanges?: (feedback: string) => void
}

export const PlansTab = memo(function PlansTab({
  artifacts,
  artifact,
  onOpenArtifact,
  onClose,
  onUpdateContent,
  onSetVersion,
  planPendingApproval,
  onApprovePlan,
  onRequestPlanChanges,
}: PlansTabProps) {
  // Only plan artifacts
  const plans = Array.from(artifacts.values()).filter((a) => a.isPlan)
  const latestPlan = plans[plans.length - 1] ?? null

  // Auto-open the latest plan if none is active
  useEffect(() => {
    if (!artifact && latestPlan) {
      onOpenArtifact(latestPlan.id)
    }
  }, [artifact, latestPlan, onOpenArtifact])

  if (!latestPlan) {
    return (
      <div className="activity-tab-empty">
        <p>No plans yet</p>
        <p className="text-xs text-muted-foreground mt-1">
          Plans will appear here when the agent proposes one for review
        </p>
      </div>
    )
  }

  // Show the active plan (or latest if none selected)
  const displayPlan = artifact?.isPlan ? artifact : latestPlan

  return (
    <ArtifactPanel
      artifact={displayPlan}
      onClose={onClose}
      onBack={onClose}
      onUpdateContent={onUpdateContent}
      onSetVersion={onSetVersion}
      planPendingApproval={planPendingApproval}
      onApprovePlan={onApprovePlan}
      onRequestPlanChanges={onRequestPlanChanges}
    />
  )
})
