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
  isLoading: boolean
  onRefresh: () => void
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

export function MemoryTable({
  memories,
  stats,
  filters,
  onFiltersChange,
  onDelete,
  isLoading,
  onRefresh,
}: MemoryTableProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

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
            {memories.map((m) => (
              <div
                key={m.id}
                className={`memory-card ${expandedId === m.id ? 'expanded' : ''}`}
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
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
