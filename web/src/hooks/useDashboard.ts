import { useState, useEffect, useCallback } from 'react'

export interface AdminStatus {
  status: string
  server: { port: number; uptime_seconds: number | null; running: boolean }
  process: {
    memory_rss_mb: number
    memory_vms_mb: number
    cpu_percent: number
    num_threads: number
  } | null
  background_tasks: { active: number; total: number; completed: number; failed: number }
  mcp_servers: Record<string, {
    connected: boolean
    status: string
    health: string | null
    transport: string
    internal?: boolean
    enabled?: boolean
    tool_count?: number
  }>
  sessions: { active: number; paused: number; handoff_ready: number; total: number }
  tasks: { open: number; in_progress: number; closed: number; ready: number; blocked: number }
  memory: { count: number }
  skills: { total: number }
  plugins: { enabled: boolean; loaded: number; handlers: number }
}

export function useDashboard() {
  const [data, setData] = useState<AdminStatus | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  const fetchStatus = useCallback(async () => {
    try {
      const response = await fetch('/admin/status')
      if (response.ok) {
        const json = await response.json()
        setData(json)
        setError(null)
        setLastUpdated(new Date())
      } else {
        setError(`HTTP ${response.status}`)
      }
    } catch (e) {
      setError(String(e))
    }
  }, [])

  const refresh = useCallback(async () => {
    setIsLoading(true)
    await fetchStatus()
    setIsLoading(false)
  }, [fetchStatus])

  useEffect(() => {
    refresh()
    const interval = setInterval(fetchStatus, 30_000)
    return () => clearInterval(interval)
  }, [refresh, fetchStatus])

  return { data, isLoading, error, lastUpdated, refresh }
}
