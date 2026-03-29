import { useState, useEffect, useCallback, useRef } from 'react'

export interface ChangedFile {
  path: string
  status: string // M, A, D, R, ??
}

function getBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || ''
}

export function useFileChanges(projectId: string | null) {
  const [changedFiles, setChangedFiles] = useState<ChangedFile[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const fetchStatus = useCallback(async () => {
    if (!projectId) {
      setChangedFiles([])
      setIsLoading(false)
      return
    }
    const baseUrl = getBaseUrl()
    try {
      const res = await fetch(
        `${baseUrl}/api/files/git-status?project_id=${encodeURIComponent(projectId)}`
      )
      if (!res.ok) {
        setChangedFiles([])
        return
      }
      const data = await res.json()
      // data.files is Record<path, statusCode>
      const files: ChangedFile[] = Object.entries(data.files || {}).map(
        ([path, status]) => ({ path, status: status as string })
      )
      // Sort: modified first, then added, then rest, alphabetically within groups
      files.sort((a, b) => {
        const order = (s: string) => {
          if (s === 'M') return 0
          if (s === 'A') return 1
          if (s === 'D') return 2
          if (s === '??') return 3
          return 4
        }
        const diff = order(a.status) - order(b.status)
        return diff !== 0 ? diff : a.path.localeCompare(b.path)
      })
      setChangedFiles(files)
    } catch {
      // Silently fail — will retry on next poll
    } finally {
      setIsLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    fetchStatus()
    intervalRef.current = setInterval(fetchStatus, 10000)
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [fetchStatus])

  const fetchDiff = useCallback(
    async (path: string): Promise<string> => {
      if (!projectId) return ''
      const baseUrl = getBaseUrl()
      try {
        const res = await fetch(
          `${baseUrl}/api/files/git-diff?project_id=${encodeURIComponent(projectId)}&path=${encodeURIComponent(path)}`
        )
        if (!res.ok) return ''
        const data = await res.json()
        return data.diff || ''
      } catch {
        return ''
      }
    },
    [projectId]
  )

  return { changedFiles, isLoading, fetchDiff, refresh: fetchStatus }
}
