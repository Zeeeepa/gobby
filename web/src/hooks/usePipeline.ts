import { useState, useEffect, useCallback, useRef } from 'react'

export interface PipelineStep {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'skipped' | 'failed' | 'waiting_approval'
  output?: unknown
  error?: string
  startedAt?: Date
  completedAt?: Date
}

export interface PipelineExecution {
  id: string
  pipelineName: string
  status: 'pending' | 'running' | 'completed' | 'failed' | 'waiting_approval'
  steps: PipelineStep[]
  inputs?: Record<string, unknown>
  outputs?: Record<string, unknown>
  error?: string
  approvalRequired?: {
    stepId: string
    message: string
    token: string
  }
  startedAt?: Date
  completedAt?: Date
}

interface PipelineEventMessage {
  type: 'pipeline_event'
  event: string
  execution_id: string
  timestamp: string
  pipeline_name?: string
  step_id?: string
  step_name?: string
  step_count?: number
  inputs?: Record<string, unknown>
  outputs?: Record<string, unknown>
  output?: unknown
  error?: string
  message?: string
  token?: string
  reason?: string
}

export function usePipeline() {
  const [executions, setExecutions] = useState<Map<string, PipelineExecution>>(new Map())
  const [isConnected, setIsConnected] = useState(false)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimeoutRef = useRef<number | null>(null)
  const handleEventRef = useRef<(event: PipelineEventMessage) => void>(() => {})

  // Handle pipeline events
  const handlePipelineEvent = useCallback((event: PipelineEventMessage) => {
    setExecutions((prev) => {
      const updated = new Map(prev)
      let execution = updated.get(event.execution_id)

      switch (event.event) {
        case 'pipeline_started':
          execution = {
            id: event.execution_id,
            pipelineName: event.pipeline_name || 'Unknown',
            status: 'running',
            steps: [],
            inputs: event.inputs,
            startedAt: new Date(event.timestamp),
          }
          // Initialize steps as pending
          if (event.step_count) {
            execution.steps = Array.from({ length: event.step_count }, (_, i) => ({
              id: `step-${i}`,
              name: `Step ${i + 1}`,
              status: 'pending',
            }))
          }
          break

        case 'step_started':
          if (execution) {
            const stepIndex = execution.steps.findIndex((s) => s.id === event.step_id)
            if (stepIndex >= 0) {
              const newSteps = [...execution.steps]
              newSteps[stepIndex] = {
                ...execution.steps[stepIndex],
                name: event.step_name || execution.steps[stepIndex].name,
                status: 'running',
                startedAt: new Date(event.timestamp),
              }
              execution = { ...execution, steps: newSteps }
            } else {
              // Add new step if not found
              execution = {
                ...execution,
                steps: [
                  ...execution.steps,
                  {
                    id: event.step_id || `step-${execution.steps.length}`,
                    name: event.step_name || `Step ${execution.steps.length + 1}`,
                    status: 'running',
                    startedAt: new Date(event.timestamp),
                  },
                ],
              }
            }
          }
          break

        case 'step_completed':
          if (execution) {
            const stepIndex = execution.steps.findIndex((s) => s.id === event.step_id)
            if (stepIndex >= 0) {
              const newSteps = [...execution.steps]
              newSteps[stepIndex] = {
                ...execution.steps[stepIndex],
                status: 'completed',
                output: event.output,
                completedAt: new Date(event.timestamp),
              }
              execution = { ...execution, steps: newSteps }
            }
          }
          break

        case 'step_skipped':
          if (execution) {
            const stepIndex = execution.steps.findIndex((s) => s.id === event.step_id)
            if (stepIndex >= 0) {
              const newSteps = [...execution.steps]
              newSteps[stepIndex] = {
                ...execution.steps[stepIndex],
                status: 'skipped',
                completedAt: new Date(event.timestamp),
              }
              execution = { ...execution, steps: newSteps }
            }
          }
          break

        case 'step_failed':
          if (execution) {
            const stepIndex = execution.steps.findIndex((s) => s.id === event.step_id)
            if (stepIndex >= 0) {
              const newSteps = [...execution.steps]
              newSteps[stepIndex] = {
                ...execution.steps[stepIndex],
                status: 'failed',
                error: event.error,
                completedAt: new Date(event.timestamp),
              }
              execution = { ...execution, steps: newSteps }
            }
          }
          break

        case 'approval_required':
          if (execution) {
            const stepIndex = execution.steps.findIndex((s) => s.id === event.step_id)
            let newSteps = execution.steps
            if (stepIndex >= 0) {
              newSteps = [...execution.steps]
              newSteps[stepIndex] = {
                ...execution.steps[stepIndex],
                status: 'waiting_approval',
              }
            }
            execution = {
              ...execution,
              status: 'waiting_approval',
              approvalRequired: {
                stepId: event.step_id || '',
                message: event.message || 'Approval required',
                token: event.token || '',
              },
              steps: newSteps,
            }
          }
          break

        case 'pipeline_completed':
          if (execution) {
            execution = {
              ...execution,
              status: 'completed',
              outputs: event.outputs,
              completedAt: new Date(event.timestamp),
            }
          }
          break

        case 'pipeline_failed':
          if (execution) {
            execution = {
              ...execution,
              status: 'failed',
              error: event.error,
              completedAt: new Date(event.timestamp),
            }
          }
          break
      }

      if (execution) {
        updated.set(event.execution_id, { ...execution })
      }
      return updated
    })
  }, [])

  // Keep ref updated
  useEffect(() => {
    handleEventRef.current = handlePipelineEvent
  }, [handlePipelineEvent])

  // Connect to WebSocket
  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const isSecure = window.location.protocol === 'https:'
    const wsUrl = isSecure
      ? `wss://${window.location.host}/ws`
      : `ws://${window.location.hostname}:60888`

    console.log('Pipeline: Connecting to WebSocket:', wsUrl)
    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      console.log('Pipeline: WebSocket connected')
      setIsConnected(true)

      // Subscribe to pipeline events
      ws.send(JSON.stringify({
        type: 'subscribe',
        events: ['pipeline_event'],
      }))
    }

    ws.onclose = () => {
      console.log('Pipeline: WebSocket disconnected')
      setIsConnected(false)

      // Reconnect after 2 seconds
      reconnectTimeoutRef.current = window.setTimeout(() => {
        connect()
      }, 2000)
    }

    ws.onerror = (error) => {
      console.error('Pipeline: WebSocket error:', error)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'pipeline_event') {
          handleEventRef.current(data as PipelineEventMessage)
        }
      } catch (e) {
        console.error('Pipeline: Failed to parse WebSocket message:', e)
      }
    }
  }, [])

  // Connect on mount
  useEffect(() => {
    connect()

    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current)
      }
      wsRef.current?.close()
    }
  }, [connect])

  // Approve a pipeline execution
  const approvePipeline = useCallback(async (token: string) => {
    try {
      const response = await fetch(`/api/pipelines/approve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      if (!response.ok) {
        throw new Error(`Failed to approve: ${response.statusText}`)
      }
      return await response.json()
    } catch (e) {
      console.error('Failed to approve pipeline:', e)
      throw e
    }
  }, [])

  // Reject a pipeline execution
  const rejectPipeline = useCallback(async (token: string) => {
    try {
      const response = await fetch(`/api/pipelines/reject`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      })
      if (!response.ok) {
        throw new Error(`Failed to reject: ${response.statusText}`)
      }
      return await response.json()
    } catch (e) {
      console.error('Failed to reject pipeline:', e)
      throw e
    }
  }, [])

  // Clear completed executions
  const clearCompleted = useCallback(() => {
    setExecutions((prev) => {
      const updated = new Map(prev)
      for (const [id, exec] of updated) {
        if (exec.status === 'completed' || exec.status === 'failed') {
          updated.delete(id)
        }
      }
      return updated
    })
  }, [])

  return {
    executions: Array.from(executions.values()),
    isConnected,
    approvePipeline,
    rejectPipeline,
    clearCompleted,
  }
}
