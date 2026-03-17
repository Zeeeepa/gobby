import { memo, useState, useEffect } from 'react'

interface PipelinesTabProps {
  projectId?: string | null
}

export const PipelinesTab = memo(function PipelinesTab({ projectId }: PipelinesTabProps) {
  const [executions, setExecutions] = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    params.set('limit', '20')
    fetch(`${baseUrl}/api/pipelines/executions?${params}`)
      .then((res) => (res.ok ? res.json() : { executions: [] }))
      .then((data) => setExecutions(data.executions ?? []))
      .catch(() => setExecutions([]))
      .finally(() => setLoading(false))
  }, [projectId])

  if (loading) {
    return <div className="activity-tab-empty"><p>Loading pipelines...</p></div>
  }

  if (executions.length === 0) {
    return (
      <div className="activity-tab-empty">
        <p>No pipeline executions</p>
        <p className="text-xs text-muted-foreground mt-1">
          Pipeline runs will appear here
        </p>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full overflow-y-auto">
      {executions.map((exec: any) => (
        <div key={exec.id} className="px-3 py-2 border-b border-border">
          <div className="flex items-center gap-2">
            <span className={`text-xs ${exec.status === 'completed' ? 'text-green-400' : exec.status === 'failed' ? 'text-red-400' : 'text-accent'}`}>
              {exec.status === 'completed' ? '\u2713' : exec.status === 'failed' ? '\u2717' : '\u25CE'}
            </span>
            <span className="text-sm text-foreground truncate">{exec.pipeline_name}</span>
          </div>
          <div className="text-xs text-muted-foreground mt-0.5">{exec.status}</div>
        </div>
      ))}
    </div>
  )
})
