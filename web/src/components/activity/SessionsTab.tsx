import { memo } from 'react'

export const SessionsTab = memo(function SessionsTab() {
  return (
    <div className="activity-tab-empty">
      <p>Session observation</p>
      <p className="text-xs text-muted-foreground mt-1">
        Use the Active Sessions modal to select a session to observe here
      </p>
    </div>
  )
})
