import { useMemo, useCallback } from 'react'
import type { ChatMessage } from '../types/chat'
import { classifyTool } from '../types/chat'

export interface ChangedFile {
  path: string
  status: string // E = edited, W = written (new)
}

function getBaseUrl(): string {
  return import.meta.env.VITE_API_BASE_URL || ''
}

/** Tools that create or modify files */
const EDIT_TOOL_TYPES = new Set(['edit'])

/** Extract file path from tool call arguments */
function extractFilePath(args: Record<string, unknown> | undefined): string | null {
  if (!args) return null
  // Claude Code uses file_path; other CLIs may use path
  const raw = args.file_path ?? args.path
  if (typeof raw === 'string' && raw.length > 0) return raw
  return null
}

/**
 * Derive session-scoped file changes from chat messages.
 * Scans completed edit/write tool calls and extracts file paths.
 */
export function useFileChanges(messages: ChatMessage[], projectId: string | null) {
  const changedFiles = useMemo(() => {
    const fileMap = new Map<string, string>() // path → status

    for (const msg of messages) {
      if (msg.role !== 'assistant' || !msg.toolCalls) continue
      for (const tc of msg.toolCalls) {
        if (tc.status !== 'completed') continue
        const toolType = tc.tool_type || classifyTool(tc.tool_name)
        if (!EDIT_TOOL_TYPES.has(toolType)) continue

        const filePath = extractFilePath(tc.arguments)
        if (!filePath) continue

        // Skip internal gobby files and plan files
        if (filePath.includes('.gobby/')) continue
        if (filePath.includes('.claude/plans/')) continue

        // Determine status: Write = new file, Edit = modified
        const toolName = tc.tool_name?.toLowerCase() || ''
        if (toolName === 'write' && !fileMap.has(filePath)) {
          fileMap.set(filePath, 'W')
        } else {
          fileMap.set(filePath, 'E')
        }
      }
    }

    const files: ChangedFile[] = Array.from(fileMap, ([path, status]) => ({ path, status }))
    // Sort: written (new) first, then edited, alphabetically within groups
    files.sort((a, b) => {
      const order = (s: string) => (s === 'W' ? 0 : s === 'E' ? 1 : 2)
      const diff = order(a.status) - order(b.status)
      return diff !== 0 ? diff : a.path.localeCompare(b.path)
    })
    return files
  }, [messages])

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
      } catch (error) {
        if (import.meta.env.DEV) console.error('fetchDiff failed:', error)
        return ''
      }
    },
    [projectId]
  )

  return { changedFiles, fetchDiff }
}
