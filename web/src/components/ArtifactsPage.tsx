import { useState, useCallback, useMemo } from 'react'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useArtifacts } from '../hooks/useArtifacts'
import type { GobbyArtifact, ArtifactFilters } from '../hooks/useArtifacts'
import './ArtifactsPage.css'

// =============================================================================
// Helpers
// =============================================================================

const ARTIFACT_TYPE_META: Record<string, { label: string; color: string }> = {
  code: { label: 'Code', color: '#3b82f6' },
  error: { label: 'Error', color: '#ef4444' },
  diff: { label: 'Diff', color: '#f59e0b' },
  file_path: { label: 'File', color: '#8b5cf6' },
  structured_data: { label: 'Data', color: '#06b6d4' },
  text: { label: 'Text', color: '#6b7280' },
  plan: { label: 'Plan', color: '#10b981' },
  command_output: { label: 'Output', color: '#f97316' },
}

function getTypeMeta(type: string) {
  return ARTIFACT_TYPE_META[type] ?? { label: type, color: '#6b7280' }
}

function getLanguageFromMetadata(artifact: GobbyArtifact): string {
  const meta = artifact.metadata
  if (meta && typeof meta === 'object' && 'language' in meta && typeof meta.language === 'string') {
    return meta.language
  }
  if (artifact.source_file) {
    const ext = artifact.source_file.split('.').pop()?.toLowerCase()
    const extMap: Record<string, string> = {
      py: 'python', ts: 'typescript', tsx: 'tsx', js: 'javascript',
      jsx: 'jsx', rs: 'rust', go: 'go', sql: 'sql', sh: 'bash',
      json: 'json', yaml: 'yaml', yml: 'yaml', toml: 'toml', xml: 'xml',
      css: 'css', html: 'html', md: 'markdown',
    }
    if (ext && extMap[ext]) return extMap[ext]
  }
  return 'text'
}

function formatRelativeDate(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMin = Math.floor(diffMs / 60000)
  const diffHr = Math.floor(diffMs / 3600000)

  if (diffMin < 1) return 'Just now'
  if (diffMin < 60) return `${diffMin}m ago`
  if (diffHr < 24) return `${diffHr}h ago`

  const diffDays = Math.floor(diffMs / 86400000)
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

function getDateGroup(dateStr: string): string {
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffDays === 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 7) return 'This Week'
  return 'Older'
}

function truncateContent(content: string, maxLen = 100): string {
  const firstLine = content.split('\n')[0]
  if (firstLine.length <= maxLen) return firstLine
  return firstLine.slice(0, maxLen) + '...'
}

const codeTheme = {
  ...oneDark,
  'pre[class*="language-"]': {
    ...oneDark['pre[class*="language-"]'],
    background: '#0d0d0d',
    margin: '0',
    padding: '1rem',
    borderRadius: '0.5rem',
    fontSize: '0.85em',
  },
  'code[class*="language-"]': {
    ...oneDark['code[class*="language-"]'],
    background: 'transparent',
    fontFamily: "'SF Mono', 'Fira Code', 'JetBrains Mono', monospace",
  },
}

// =============================================================================
// Sub-components
// =============================================================================

function TypeBadge({ type }: { type: string }) {
  const meta = getTypeMeta(type)
  return (
    <span
      className="artifact-type-badge"
      style={{ borderColor: meta.color, color: meta.color }}
    >
      {meta.label}
    </span>
  )
}

function ArtifactListItem({
  artifact,
  isSelected,
  onClick,
}: {
  artifact: GobbyArtifact
  isSelected: boolean
  onClick: () => void
}) {
  return (
    <div
      className={`artifact-list-item ${isSelected ? 'selected' : ''}`}
      onClick={onClick}
    >
      <div className="artifact-list-item-header">
        <TypeBadge type={artifact.artifact_type} />
        <span className="artifact-list-item-time">
          {formatRelativeDate(artifact.created_at)}
        </span>
      </div>
      <div className="artifact-list-item-title">
        {artifact.title ?? truncateContent(artifact.content)}
      </div>
      {artifact.tags.length > 0 && (
        <div className="artifact-list-item-tags">
          {artifact.tags.map(tag => (
            <span key={tag} className="artifact-tag-chip-small">{tag}</span>
          ))}
        </div>
      )}
    </div>
  )
}

function ArtifactDetail({
  artifact,
  onDelete,
  onAddTag,
  onRemoveTag,
}: {
  artifact: GobbyArtifact
  onDelete: (id: string) => void
  onAddTag: (id: string, tag: string) => void
  onRemoveTag: (id: string, tag: string) => void
}) {
  const [tagInput, setTagInput] = useState('')
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(artifact.content)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }, [artifact.content])

  const handleAddTag = useCallback(() => {
    const tag = tagInput.trim()
    if (tag && !artifact.tags.includes(tag)) {
      onAddTag(artifact.id, tag)
      setTagInput('')
    }
  }, [tagInput, artifact.id, artifact.tags, onAddTag])

  const handleTagKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAddTag()
    }
  }, [handleAddTag])

  const language = getLanguageFromMetadata(artifact)
  const isCode = artifact.artifact_type === 'code' || artifact.artifact_type === 'diff'

  return (
    <div className="artifact-detail">
      <div className="artifact-detail-header">
        <div className="artifact-detail-title-row">
          <TypeBadge type={artifact.artifact_type} />
          <h3 className="artifact-detail-title">
            {artifact.title ?? 'Untitled Artifact'}
          </h3>
        </div>
        <div className="artifact-detail-meta">
          <span className="artifact-detail-meta-item">
            {new Date(artifact.created_at).toLocaleString()}
          </span>
          {artifact.source_file && (
            <span className="artifact-detail-meta-item" title={artifact.source_file}>
              {artifact.source_file.split('/').pop()}
              {artifact.line_start != null && `:${artifact.line_start}`}
              {artifact.line_end != null && `-${artifact.line_end}`}
            </span>
          )}
          {artifact.session_id && (
            <span className="artifact-detail-meta-item">
              Session: {artifact.session_id.slice(0, 8)}...
            </span>
          )}
          {artifact.task_id && (
            <span className="artifact-detail-meta-item">
              Task: {artifact.task_id.slice(0, 8)}...
            </span>
          )}
        </div>
      </div>

      <div className="artifact-detail-content">
        {isCode ? (
          <SyntaxHighlighter
            style={codeTheme}
            language={artifact.artifact_type === 'diff' ? 'diff' : language}
            PreTag="div"
            showLineNumbers
            lineNumberStyle={{
              minWidth: '2.5em',
              paddingRight: '1em',
              textAlign: 'right' as const,
              userSelect: 'none' as const,
              color: '#555',
            }}
          >
            {artifact.content}
          </SyntaxHighlighter>
        ) : artifact.artifact_type === 'error' ? (
          <pre className="artifact-error-content">{artifact.content}</pre>
        ) : (
          <pre className="artifact-text-content">{artifact.content}</pre>
        )}
      </div>

      <div className="artifact-detail-tags">
        <div className="artifact-tags-list">
          {artifact.tags.map(tag => (
            <span key={tag} className="artifact-tag-chip">
              {tag}
              <button
                className="artifact-tag-remove"
                onClick={() => onRemoveTag(artifact.id, tag)}
                title={`Remove tag "${tag}"`}
              >
                x
              </button>
            </span>
          ))}
          <div className="artifact-tag-add">
            <input
              type="text"
              className="artifact-tag-input"
              placeholder="Add tag..."
              value={tagInput}
              onChange={e => setTagInput(e.target.value)}
              onKeyDown={handleTagKeyDown}
            />
            {tagInput.trim() && (
              <button className="artifact-tag-add-btn" onClick={handleAddTag}>+</button>
            )}
          </div>
        </div>
      </div>

      <div className="artifact-detail-actions">
        <button className="artifact-action-btn" onClick={handleCopy}>
          {copied ? 'Copied!' : 'Copy'}
        </button>
        <button
          className="artifact-action-btn artifact-action-delete"
          onClick={() => onDelete(artifact.id)}
        >
          Delete
        </button>
      </div>
    </div>
  )
}

// =============================================================================
// Main Component
// =============================================================================

export function ArtifactsPage() {
  const {
    artifacts,
    searchResults,
    selectedArtifact,
    setSelectedArtifact,
    stats,
    isLoading,
    hasMore,
    filters,
    setFilters,
    deleteArtifact,
    addTag,
    removeTag,
    loadMore,
    refreshArtifacts,
  } = useArtifacts()

  const displayArtifacts = searchResults ?? artifacts

  // Group artifacts by date
  const groupedArtifacts = useMemo(() => {
    const groups: Record<string, GobbyArtifact[]> = {}
    for (const a of displayArtifacts) {
      const group = getDateGroup(a.created_at)
      if (!groups[group]) groups[group] = []
      groups[group].push(a)
    }
    return groups
  }, [displayArtifacts])

  const groupOrder = ['Today', 'Yesterday', 'This Week', 'Older']

  // Available types from stats
  const availableTypes = useMemo(() => {
    if (!stats?.by_type) return []
    return Object.entries(stats.by_type)
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => ({ type, count }))
  }, [stats])

  const handleFilterType = useCallback((type: string | null) => {
    setFilters((f: ArtifactFilters) => ({
      ...f,
      artifactType: f.artifactType === type ? null : type,
    }))
  }, [setFilters])

  const handleSearch = useCallback((value: string) => {
    setFilters((f: ArtifactFilters) => ({ ...f, search: value }))
  }, [setFilters])

  const handleDelete = useCallback(async (id: string) => {
    await deleteArtifact(id)
  }, [deleteArtifact])

  const handleAddTag = useCallback(async (id: string, tag: string) => {
    await addTag(id, tag)
  }, [addTag])

  const handleRemoveTag = useCallback(async (id: string, tag: string) => {
    await removeTag(id, tag)
  }, [removeTag])

  return (
    <main className="artifacts-page">
      {/* Sidebar */}
      <div className="artifacts-sidebar">
        <div className="artifacts-sidebar-header">
          <span className="artifacts-sidebar-title">Artifacts</span>
          <div className="artifacts-sidebar-actions">
            <span className="artifacts-count">
              {stats?.total_count ?? 0}
            </span>
            <button
              className="artifacts-refresh-btn"
              onClick={refreshArtifacts}
              title="Refresh"
            >
              <RefreshIcon />
            </button>
          </div>
        </div>

        <div className="artifacts-search-bar">
          <input
            type="text"
            className="artifacts-search-input"
            placeholder="Search artifacts..."
            value={filters.search}
            onChange={e => handleSearch(e.target.value)}
          />
        </div>

        {availableTypes.length > 0 && (
          <div className="artifacts-filter-chips">
            {availableTypes.map(({ type, count }) => {
              const meta = getTypeMeta(type)
              return (
                <button
                  key={type}
                  className={`artifacts-chip ${filters.artifactType === type ? 'active' : ''}`}
                  onClick={() => handleFilterType(type)}
                  style={filters.artifactType === type ? { borderColor: meta.color, color: meta.color } : {}}
                >
                  {meta.label} ({count})
                </button>
              )
            })}
          </div>
        )}

        <div className="artifacts-list">
          {isLoading && displayArtifacts.length === 0 ? (
            <div className="artifacts-loading">Loading...</div>
          ) : displayArtifacts.length === 0 ? (
            <div className="artifacts-empty-list">
              {filters.search ? 'No results found' : 'No artifacts yet'}
            </div>
          ) : (
            <>
              {groupOrder.map(group => {
                const items = groupedArtifacts[group]
                if (!items || items.length === 0) return null
                return (
                  <div key={group} className="artifacts-group">
                    <div className="artifacts-group-header">{group}</div>
                    {items.map(artifact => (
                      <ArtifactListItem
                        key={artifact.id}
                        artifact={artifact}
                        isSelected={selectedArtifact?.id === artifact.id}
                        onClick={() => setSelectedArtifact(artifact)}
                      />
                    ))}
                  </div>
                )
              })}
              {hasMore && (
                <button className="artifacts-load-more" onClick={loadMore}>
                  Load more
                </button>
              )}
            </>
          )}
        </div>
      </div>

      {/* Detail Panel */}
      <div className="artifacts-content">
        {selectedArtifact ? (
          <ArtifactDetail
            artifact={selectedArtifact}
            onDelete={handleDelete}
            onAddTag={handleAddTag}
            onRemoveTag={handleRemoveTag}
          />
        ) : (
          <div className="artifacts-empty-state">
            <ArtifactsEmptyIcon />
            <h3>Select an artifact</h3>
            <p>Choose an artifact from the sidebar to view its content</p>
          </div>
        )}
      </div>
    </main>
  )
}

// =============================================================================
// Icons
// =============================================================================

function RefreshIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="23 4 23 10 17 10" />
      <path d="M20.49 15a9 9 0 1 1-2.12-9.36L23 10" />
    </svg>
  )
}

function ArtifactsEmptyIcon() {
  return (
    <svg width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" style={{ opacity: 0.3 }}>
      <path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z" />
      <polyline points="3.27 6.96 12 12.01 20.73 6.96" />
      <line x1="12" y1="22.08" x2="12" y2="12" />
    </svg>
  )
}
