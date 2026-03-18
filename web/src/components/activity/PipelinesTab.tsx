import { memo, useState, useEffect, useCallback, useRef } from 'react'
import { StatusBadge, StepDisplay, formatTime, type StepData } from '../workflows/execution-utils'

interface PipelinesTabProps {
  projectId?: string | null
}

interface PipelineExecution {
  id: string
  pipeline_name: string
  status: string
  started_at: string
  completed_at?: string | null
  steps?: StepData[]
}

function getBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || ''
}

export const PipelinesTab = memo(function PipelinesTab({ projectId }: PipelinesTabProps) {
  const [executions, setExecutions] = useState<PipelineExecution[]>([])
  const [loading, setLoading] = useState(true)
  const [showCompleted, setShowCompleted] = useState(false)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [detailExec, setDetailExec] = useState<PipelineExecution | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // Fetch executions
  const fetchExecutions = useCallback(() => {
    const baseUrl = getBaseUrl()
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    if (!showCompleted) params.set('status', 'running')
    params.set('limit', '50')
    return fetch(`${baseUrl}/api/pipelines/executions?${params}`)
      .then((res) => (res.ok ? res.json() : { executions: [] }))
      .then((data) => setExecutions(data.executions ?? []))
      .catch(() => setExecutions([]))
  }, [projectId, showCompleted])

  useEffect(() => {
    const controller = new AbortController()
    setLoading(true)
    fetchExecutions().finally(() => {
      if (!controller.signal.aborted) setLoading(false)
    })
    return () => controller.abort()
  }, [fetchExecutions])

  // Fetch detail for selected execution
  const fetchDetail = useCallback((id: string) => {
    const baseUrl = getBaseUrl()
    fetch(`${baseUrl}/api/pipelines/${id}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.execution) setDetailExec(data.execution)
        else if (data?.id) setDetailExec(data)
      })
      .catch((err) => { console.error('Failed to fetch pipeline detail:', err) })
  }, [])

  // Poll running executions
  useEffect(() => {
    const hasRunning = executions.some((e) => e.status === 'running')
    if (hasRunning || (selectedId && detailExec?.status === 'running')) {
      pollRef.current = setInterval(() => {
        fetchExecutions()
        if (selectedId) fetchDetail(selectedId)
      }, 3000)
    }
    return () => { if (pollRef.current) clearInterval(pollRef.current) }
  }, [executions, selectedId, detailExec?.status, fetchExecutions, fetchDetail])

  const handleSelect = useCallback((id: string) => {
    if (selectedId === id) {
      setSelectedId(null)
      setDetailExec(null)
    } else {
      setSelectedId(id)
      fetchDetail(id)
    }
  }, [selectedId, fetchDetail])

  if (loading) {
    return <div className="activity-tab-empty"><p>Loading pipelines...</p></div>
  }

  return (
    <div className="flex flex-col h-full">
      {/* Toolbar */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground cursor-pointer">
          <input
            type="checkbox"
            checked={showCompleted}
            onChange={(e) => setShowCompleted(e.target.checked)}
            className="rounded"
          />
          Show completed
        </label>
        <span className="text-xs text-muted-foreground ml-auto">
          {executions.length} execution{executions.length !== 1 ? 's' : ''}
        </span>
      </div>

      {/* Execution list */}
      <div className={`overflow-y-auto ${selectedId ? 'max-h-[40%] border-b border-border' : 'flex-1'}`}>
        {executions.length === 0 ? (
          <div className="activity-tab-empty">
            <p>{showCompleted ? 'No pipeline executions' : 'No running pipelines'}</p>
            <p className="text-xs text-muted-foreground mt-1">
              {showCompleted ? 'Pipeline runs will appear here' : 'Toggle "Show completed" to see past runs'}
            </p>
          </div>
        ) : (
          executions.map((exec) => (
            <div
              key={exec.id}
              className={`pipeline-exec-row${selectedId === exec.id ? ' pipeline-exec-row--active' : ''}`}
              onClick={() => handleSelect(exec.id)}
            >
              <div className="flex items-center gap-2 min-w-0">
                <ExecutionStatusIcon status={exec.status} />
                <span className="text-sm text-foreground truncate">{exec.pipeline_name}</span>
              </div>
              <div className="flex items-center gap-2">
                <StatusBadge status={exec.status} />
                {exec.started_at && (
                  <span className="text-[10px] text-muted-foreground shrink-0">{formatTime(exec.started_at)}</span>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      {/* Detail pane */}
      {selectedId && detailExec && (
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-muted/30">
            <div className="flex items-center gap-2 min-w-0">
              <span className="text-xs text-foreground truncate">{detailExec.pipeline_name}</span>
              <StatusBadge status={detailExec.status} />
            </div>
            <button
              className="text-xs text-muted-foreground hover:text-foreground shrink-0"
              onClick={() => { setSelectedId(null); setDetailExec(null) }}
            >
              Close
            </button>
          </div>
          <div className="flex-1 overflow-y-auto p-2">
            {detailExec.steps && detailExec.steps.length > 0 ? (
              <div className="space-y-1">
                {detailExec.steps.map((step, i) => (
                  <StepDisplay key={step.step_id ?? i} step={step} index={i} />
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground p-2">No steps available</p>
            )}
          </div>
        </div>
      )}
    </div>
  )
})

function ExecutionStatusIcon({ status }: { status: string }) {
  if (status === 'completed' || status === 'success') {
    return <span className="text-green-400 text-xs">{'\u2713'}</span>
  }
  if (status === 'failed' || status === 'error') {
    return <span className="text-red-400 text-xs">{'\u2717'}</span>
  }
  if (status === 'running') {
    return (
      <span className="pipeline-running-dot" />
    )
  }
  return <span className="text-muted-foreground text-xs">{'\u25CB'}</span>
}
