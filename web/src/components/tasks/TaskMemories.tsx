import { useState, useEffect, useCallback, useMemo } from 'react'

// =============================================================================
// Types
// =============================================================================

interface MemoryEntry {
  id: string
  content: string
  memory_type: string
  importance: number
  source_session_id: string | null
  created_at: string
  tags: string[]
}

// =============================================================================
// Helpers
// =============================================================================

function getBaseUrl(): string {
  const isSecure = window.location.protocol === 'https:'
  return isSecure ? '' : `http://${window.location.hostname}:60887`
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
    + ' ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
}

function importanceColor(imp: number): string {
  if (imp >= 0.8) return '#22c55e'
  if (imp >= 0.5) return '#3b82f6'
  if (imp >= 0.3) return '#eab308'
  return '#737373'
}

const TYPE_ICONS: Record<string, string> = {
  fact: '\u2139',         // ℹ
  pattern: '\u2699',      // ⚙
  preference: '\u2605',   // ★
  decision: '\u2714',     // ✔
  lesson: '\u2728',       // ✨
  insight: '\u{1F4A1}',   // 💡
}

// =============================================================================
// TaskMemories
// =============================================================================

interface TaskMemoriesProps {
  sessionId: string | null
}

export function TaskMemories({ sessionId }: TaskMemoriesProps) {
  const [memories, setMemories] = useState<MemoryEntry[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [expandedIds, setExpandedIds] = useState<Set<string>>(new Set())

  const fetchMemories = useCallback(async () => {
    if (!sessionId) return
    setIsLoading(true)
    try {
      const baseUrl = getBaseUrl()
      const response = await fetch(`${baseUrl}/memories?limit=200`)
      if (response.ok) {
        const data = await response.json()
        const all: MemoryEntry[] = data.memories || []
        // Filter to memories created in this session
        const sessionMemories = all.filter(m => m.source_session_id === sessionId)
        setMemories(sessionMemories)
      }
    } catch (e) {
      console.error('Failed to fetch memories:', e)
    }
    setIsLoading(false)
  }, [sessionId])

  useEffect(() => {
    fetchMemories()
  }, [fetchMemories])

  const toggle = useCallback((id: string) => {
    setExpandedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }, [])

  const sortedMemories = useMemo(
    () => [...memories].sort((a, b) => b.importance - a.importance),
    [memories],
  )

  if (!sessionId) return null
  if (isLoading) return <div className="task-memories-loading">Loading memories...</div>
  if (memories.length === 0) return <div className="task-memories-empty">No memories from this session</div>

  return (
    <div className="task-memories">
      <span className="task-memories-count">{memories.length} memor{memories.length === 1 ? 'y' : 'ies'}</span>
      <div className="task-memories-list">
        {sortedMemories.map(mem => {
          const isExpanded = expandedIds.has(mem.id)
          const preview = mem.content.length > 100 && !isExpanded
            ? mem.content.slice(0, 100) + '...'
            : mem.content
          const icon = TYPE_ICONS[mem.memory_type] || '\u2022'

          return (
            <button
              key={mem.id}
              className="task-memory-item"
              onClick={() => toggle(mem.id)}
            >
              <div className="task-memory-header">
                <span className="task-memory-icon">{icon}</span>
                <span className="task-memory-type">{mem.memory_type}</span>
                <span
                  className="task-memory-importance"
                  style={{ color: importanceColor(mem.importance) }}
                  title={`Importance: ${(mem.importance * 100).toFixed(0)}%`}
                >
                  {'\u25CF'} {(mem.importance * 100).toFixed(0)}%
                </span>
                <span className="task-memory-date">{formatDate(mem.created_at)}</span>
              </div>
              <div className="task-memory-content">{preview}</div>
              {mem.tags.length > 0 && (
                <div className="task-memory-tags">
                  {mem.tags.map(tag => (
                    <span key={tag} className="task-memory-tag">{tag}</span>
                  ))}
                </div>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}
