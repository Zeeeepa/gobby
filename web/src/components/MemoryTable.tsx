import { useState } from 'react'
import type { GobbyMemory, MemoryFilters, MemoryStats } from '../hooks/useMemory'
import { MemoryFilters as MemoryFiltersComponent } from './MemoryFilters'
import { formatRelativeTime } from '../utils/formatTime'

interface MemoryTableProps {
  memories: GobbyMemory[]
  stats: MemoryStats | null
  filters: MemoryFilters
  onFiltersChange: (filters: MemoryFilters) => void
  onDelete: (memoryId: string) => void
  onUpdate?: (memoryId: string, params: { content?: string; importance?: number; tags?: string[] }) => void
  isLoading: boolean
  onRefresh: () => void
  onSelect?: (memory: GobbyMemory) => void
  onEdit?: (memory: GobbyMemory) => void
}

function typeColor(type: string): string {
  switch (type) {
    case 'fact':
      return 'var(--accent)'
    case 'preference':
      return '#c084fc'
    case 'pattern':
      return '#34d399'
    case 'context':
      return '#fbbf24'
    default:
      return 'var(--text-muted)'
  }
}

function importanceBar(importance: number): string {
  if (importance >= 0.9) return 'importance-critical'
  if (importance >= 0.7) return 'importance-high'
  if (importance >= 0.5) return 'importance-medium'
  return 'importance-low'
}

function isPinned(m: GobbyMemory): boolean {
  return m.importance >= 1.0
}

export function MemoryTable({
  memories,
  stats,
  filters,
  onFiltersChange,
  onDelete,
  onUpdate,
  isLoading,
  onRefresh,
  onSelect,
  onEdit,
}: MemoryTableProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const handlePin = (e: React.MouseEvent, m: GobbyMemory) => {
    e.stopPropagation()
    if (!onUpdate) return
    onUpdate(m.id, { importance: isPinned(m) ? 0.5 : 1.0 })
  }

  return (
    <div className="memory-page">
      <div className="memory-sidebar">
        <div className="memory-sidebar-header">
          <span className="memory-sidebar-title">Memories</span>
          <button
            className="terminals-action-btn"
            onClick={onRefresh}
            title="Refresh"
            disabled={isLoading}
          >
            &#x21bb;
          </button>
        </div>

        <MemoryFiltersComponent
          filters={filters}
          onFiltersChange={onFiltersChange}
        />

        {stats && (
          <div className="memory-stats-bar">
            <span className="memory-stats-count">{stats.total_count} memories</span>
            <span className="memory-stats-sep">&middot;</span>
            <span className="memory-stats-avg">
              avg {(stats.avg_importance * 100).toFixed(0)}%
            </span>
          </div>
        )}
      </div>

      <div className="memory-content">
        {isLoading ? (
          <div className="memory-empty">Loading memories...</div>
        ) : memories.length === 0 ? (
          <div className="memory-empty">
            <div className="memory-empty-icon">&#x1f9e0;</div>
            <div>No memories found</div>
            <div className="memory-empty-hint">
              Memories are created during sessions and capture important facts.
            </div>
          </div>
        ) : (
          <div className="memory-list">
            {memories.map((m) => {
              const pinned = isPinned(m)
              return (
                <div
                  key={m.id}
                  className={`memory-card ${expandedId === m.id ? 'expanded' : ''} ${pinned ? 'memory-card--pinned' : ''}`}
                  onClick={() =>
                    setExpandedId(expandedId === m.id ? null : m.id)
                  }
                >
                  <div className="memory-card-header">
                    <span
                      className="memory-type-badge"
                      style={{ backgroundColor: typeColor(m.memory_type) }}
                    >
                      {m.memory_type}
                    </span>
                    {pinned && <span className="memory-pin-indicator" title="Pinned">{'\u{1F4CC}'}</span>}
                    <div
                      className={`memory-importance ${importanceBar(m.importance)}`}
                      title={`Importance: ${(m.importance * 100).toFixed(0)}%`}
                    >
                      <div
                        className="memory-importance-fill"
                        style={{ width: `${m.importance * 100}%` }}
                      />
                    </div>
                    <span className="memory-date">
                      {formatRelativeTime(m.created_at)}
                    </span>
                    {/* Quick action buttons - always visible */}
                    <div className="memory-card-quick-actions">
                      {onUpdate && (
                        <button
                          className={`memory-pin-btn ${pinned ? 'memory-pin-btn--active' : ''}`}
                          onClick={(e) => handlePin(e, m)}
                          title={pinned ? 'Unpin memory' : 'Pin memory'}
                        >
                          {'\u{1F4CC}'}
                        </button>
                      )}
                      {onEdit && (
                        <button
                          className="memory-quick-edit-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            onEdit(m)
                          }}
                          title="Edit memory"
                        >
                          {'\u270E'}
                        </button>
                      )}
                    </div>
                  </div>

                  <div className="memory-card-content">
                    {expandedId === m.id
                      ? m.content
                      : m.content.length > 120
                        ? m.content.slice(0, 120) + '...'
                        : m.content}
                  </div>

                  {m.tags && m.tags.length > 0 && (
                    <div className="memory-tags">
                      {m.tags.map((tag) => (
                        <span key={tag} className="memory-tag">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}

                  {expandedId === m.id && (
                    <div className="memory-card-actions">
                      <span className="memory-card-id" title={m.id}>
                        {m.id.slice(0, 12)}
                      </span>
                      <span className="memory-card-access">
                        {m.access_count} accesses
                      </span>
                      {onSelect && (
                        <button
                          className="memory-action-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            onSelect(m)
                          }}
                          title="View details"
                        >
                          View
                        </button>
                      )}
                      {onEdit && (
                        <button
                          className="memory-action-btn"
                          onClick={(e) => {
                            e.stopPropagation()
                            onEdit(m)
                          }}
                          title="Edit memory"
                        >
                          Edit
                        </button>
                      )}
                      <button
                        className="memory-delete-btn"
                        onClick={(e) => {
                          e.stopPropagation()
                          onDelete(m.id)
                        }}
                        title="Delete memory"
                      >
                        Delete
                      </button>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}
