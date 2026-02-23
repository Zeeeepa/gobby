import { useState, useCallback, useMemo, useEffect, useRef, lazy, Suspense, Component, type ReactNode } from 'react'
import { useMemory, useNeo4jStatus } from '../hooks/useMemory'
import type { GobbyMemory } from '../hooks/useMemory'
import { MemoryFilters } from './MemoryFilters'
import { MemoryTable } from './MemoryTable'
import { MemoryGraph } from './MemoryGraph'
import { MemoryForm } from './MemoryForm'
import type { MemoryFormData } from './MemoryForm'
import { MemoryDetail } from './MemoryDetail'

const DEFAULT_MEMORY_GRAPH_LIMIT = 200
const DEFAULT_KNOWLEDGE_GRAPH_LIMIT = 500
const GRAPH_LIMIT_MIN = 50
const GRAPH_LIMIT_MAX = 1000
const KNOWLEDGE_LIMIT_MAX = 5000
const GRAPH_LIMIT_STEP = 50

const KnowledgeGraph = lazy(() => import('./KnowledgeGraph').then(m => ({ default: m.KnowledgeGraph })))

class KnowledgeGraphErrorBoundary extends Component<
  { children: ReactNode; onFallback?: () => void },
  { hasError: boolean }
> {
  constructor(props: { children: ReactNode; onFallback?: () => void }) {
    super(props)
    this.state = { hasError: false }
  }
  static getDerivedStateFromError() {
    return { hasError: true }
  }
  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[KnowledgeGraphErrorBoundary]', error, info)
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ padding: '2rem', color: 'var(--text-secondary)', textAlign: 'center' }}>
          <div>3D knowledge graph failed to load.</div>
          <div style={{ display: 'flex', gap: '0.5rem', justifyContent: 'center', marginTop: '0.75rem' }}>
            <button
              onClick={() => this.setState({ hasError: false })}
              style={{ padding: '0.35rem 0.75rem', borderRadius: 4, border: '1px solid var(--border)', background: 'var(--bg-secondary)', color: 'var(--text-primary)', cursor: 'pointer', fontSize: '0.8rem' }}
            >
              Try Again
            </button>
            {this.props.onFallback && (
              <button
                onClick={this.props.onFallback}
                style={{ padding: '0.35rem 0.75rem', borderRadius: 4, border: 'none', background: 'var(--accent)', color: '#fff', cursor: 'pointer', fontSize: '0.8rem' }}
              >
                Switch to 2D
              </button>
            )}
          </div>
        </div>
      )
    }
    return this.props.children
  }
}

function ListIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <line x1="3" y1="3" x2="11" y2="3" />
      <line x1="3" y1="7" x2="11" y2="7" />
      <line x1="3" y1="11" x2="11" y2="11" />
    </svg>
  )
}

function GraphIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="3" cy="3" r="1.5" />
      <circle cx="11" cy="3" r="1.5" />
      <circle cx="7" cy="11" r="1.5" />
      <line x1="4.2" y1="4" x2="6.2" y2="9.8" />
      <line x1="9.8" y1="4" x2="7.8" y2="9.8" />
    </svg>
  )
}

function KnowledgeIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <rect x="1" y="2" width="4" height="3" rx="1" />
      <rect x="9" y="2" width="4" height="3" rx="1" />
      <rect x="5" y="9" width="4" height="3" rx="1" />
      <line x1="5" y1="3.5" x2="9" y2="3.5" />
      <line x1="3" y1="5" x2="7" y2="9" />
      <line x1="11" y1="5" x2="7" y2="9" />
    </svg>
  )
}

type ViewMode = 'list' | 'graph' | 'knowledge'
interface MemoryPageProps {
  projectId?: string | null
}

export function MemoryPage({ projectId }: MemoryPageProps = {}) {
  const {
    memories,
    stats,
    isLoading,
    filters,
    setFilters,
    createMemory,
    updateMemory,
    deleteMemory,
    refreshMemories,
    fetchGraphData,
    fetchKnowledgeGraph,
    fetchEntityNeighbors,
  } = useMemory()

  // Sync global project filter into the hook's server-side filtering
  useEffect(() => {
    setFilters(f => ({ ...f, projectId: projectId ?? null }))
  }, [projectId, setFilters])
  const neo4jStatus = useNeo4jStatus()

  // Configurable graph limits (fetched from backend config, overridable per-session)
  const [memoryGraphLimit, setMemoryGraphLimit] = useState(DEFAULT_MEMORY_GRAPH_LIMIT)
  const [knowledgeGraphLimit, setKnowledgeGraphLimit] = useState(DEFAULT_KNOWLEDGE_GRAPH_LIMIT)

  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/config/values', { signal: controller.signal })
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (!data) return
        const values = data.values ?? data
        const memLimit = values?.['ui.memory_graph_limit']
        const kgLimit = values?.['ui.knowledge_graph_limit']
        if (typeof memLimit === 'number' && memLimit >= 50) setMemoryGraphLimit(memLimit)
        if (typeof kgLimit === 'number' && kgLimit >= 50) setKnowledgeGraphLimit(kgLimit)
      })
      .catch((e) => { if (e.name !== 'AbortError') console.debug('Config fetch failed:', e) })
    return () => controller.abort()
  }, [])

  const [viewMode, setViewMode] = useState<ViewMode>(() => {
    try {
      const saved = localStorage.getItem('gobby-memory-view')
      if (saved === 'knowledge' || saved === 'graph' || saved === 'list') return saved
    } catch { /* noop */ }
    return 'graph'
  })
  const [showForm, setShowForm] = useState(false)

  // Default to knowledge view when Neo4j is configured and no saved preference
  // Skip if 3D previously failed (user can manually re-select knowledge view to retry)
  const autoSwitchedRef = useRef(false)
  useEffect(() => {
    if (neo4jStatus?.configured && viewMode === 'graph' && !autoSwitchedRef.current) {
      try {
        if (!localStorage.getItem('gobby-memory-view') && !localStorage.getItem('gobby-kg-failed')) {
          setViewMode('knowledge')
        }
      } catch {
        setViewMode('knowledge')
      }
      autoSwitchedRef.current = true
    }
  }, [neo4jStatus?.configured, viewMode])

  // Persist view mode
  useEffect(() => {
    try { localStorage.setItem('gobby-memory-view', viewMode) } catch { /* noop */ }
  }, [viewMode])
  const [editMemory, setEditMemory] = useState<GobbyMemory | null>(null)
  const [selectedMemory, setSelectedMemory] = useState<GobbyMemory | null>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const showError = useCallback((msg: string) => {
    setErrorMessage(msg)
    setTimeout(() => setErrorMessage(null), 4000)
  }, [])
  const handleKnowledgeGraphError = useCallback(() => {
    setViewMode('graph')
    showError('3D knowledge graph unavailable — switched to 2D view')
    try { localStorage.setItem('gobby-kg-failed', 'true') } catch { /* noop */ }
  }, [showError])

  const [searchText, setSearchText] = useState('')

  // Apply search and recent filters to memories
  const filteredMemories = useMemo(() => {
    let result = memories

    if (filters.recentOnly) {
      const cutoff = Date.now() - 24 * 60 * 60 * 1000
      result = result.filter(m => new Date(m.created_at).getTime() > cutoff)
    }

    if (searchText.trim()) {
      const q = searchText.toLowerCase()
      result = result.filter(m =>
        m.content.toLowerCase().includes(q) ||
        m.memory_type.toLowerCase().includes(q) ||
        (m.tags && m.tags.some(t => t.toLowerCase().includes(q)))
      )
    }

    return result
  }, [memories, filters.recentOnly, searchText])

  const handleCreate = useCallback(() => {
    setEditMemory(null)
    setShowForm(true)
  }, [])

  const handleEdit = useCallback((memory: GobbyMemory) => {
    setSelectedMemory(null)
    setEditMemory(memory)
    setShowForm(true)
  }, [])

  const handleSave = useCallback(
    async (data: MemoryFormData) => {
      try {
        if (editMemory) {
          await updateMemory(editMemory.id, {
            content: data.content,
            importance: data.importance,
            tags: data.tags,
          })
        } else {
          await createMemory({
            content: data.content,
            memory_type: data.memory_type,
            importance: data.importance,
            tags: data.tags,
          })
        }
        setShowForm(false)
        setEditMemory(null)
      } catch (e) {
        console.error('Failed to save memory:', e)
        showError('Failed to save memory')
      }
    },
    [editMemory, createMemory, updateMemory, showError]
  )

  const handleDelete = useCallback(
    async (memoryId: string) => {
      try {
        await deleteMemory(memoryId)
        if (selectedMemory?.id === memoryId) {
          setSelectedMemory(null)
        }
      } catch (e) {
        console.error('Failed to delete memory:', e)
        showError('Failed to delete memory')
      }
    },
    [deleteMemory, selectedMemory, showError]
  )

  const handleSelect = useCallback((memory: GobbyMemory) => {
    setSelectedMemory(memory)
  }, [])

  const handleDetailEdit = useCallback(() => {
    if (selectedMemory) {
      handleEdit(selectedMemory)
    }
  }, [selectedMemory, handleEdit])

  const handleDetailDelete = useCallback(() => {
    if (selectedMemory) {
      handleDelete(selectedMemory.id)
    }
  }, [selectedMemory, handleDelete])

  const viewModes: [ViewMode, React.ComponentType, string][] = [
    ...(neo4jStatus?.configured ? [['knowledge' as ViewMode, KnowledgeIcon, 'Knowledge graph'] as [ViewMode, React.ComponentType, string]] : []),
    ['graph', GraphIcon, 'Graph view'],
    ['list', ListIcon, 'List view'],
  ]

  return (
    <main className="memory-page">
      {errorMessage && (
        <div className="memory-error-toast" onClick={() => setErrorMessage(null)}>
          {errorMessage}
        </div>
      )}
      {/* Toolbar */}
      <div className="memory-toolbar">
        <div className="memory-toolbar-left">
          <h2 className="memory-toolbar-title">Memory</h2>
        </div>
        <div className="memory-toolbar-right">
          <div className="memory-view-toggle">
            {viewModes.map(([mode, Icon, title]) => (
              <button
                key={mode}
                className={`memory-view-btn ${viewMode === mode ? 'active' : ''}`}
                onClick={() => setViewMode(mode)}
                title={title}
              >
                <Icon />
              </button>
            ))}
          </div>
          {viewMode !== 'list' && (
            <label className="memory-limit-control" title="Max nodes to display">
              Limit
              <input
                type="number"
                min={GRAPH_LIMIT_MIN}
                max={viewMode === 'graph' ? GRAPH_LIMIT_MAX : KNOWLEDGE_LIMIT_MAX}
                step={GRAPH_LIMIT_STEP}
                value={viewMode === 'knowledge' ? knowledgeGraphLimit : memoryGraphLimit}
                onChange={e => {
                  const sliderMax = viewMode === 'graph' ? GRAPH_LIMIT_MAX : KNOWLEDGE_LIMIT_MAX
                  const v = Math.max(GRAPH_LIMIT_MIN, Math.min(sliderMax, Number(e.target.value) || GRAPH_LIMIT_MIN))
                  if (viewMode === 'knowledge') setKnowledgeGraphLimit(v)
                  else setMemoryGraphLimit(v)
                }}
              />
            </label>
          )}
          <input
            className="memory-search"
            type="text"
            placeholder="Search..."
            value={searchText}
            onChange={e => setSearchText(e.target.value)}
          />
          <button
            className="memory-toolbar-btn"
            onClick={refreshMemories}
            title="Refresh"
            disabled={isLoading}
          >
            &#x21bb;
          </button>
          <button className="memory-new-btn" onClick={handleCreate}>
            + New
          </button>
        </div>
      </div>

      {/* Filter bar */}
      <MemoryFilters
        filters={filters}
        stats={stats}
        recentCount={stats?.recent_count ?? 0}
        onFiltersChange={setFilters}
      />

      {/* Content area */}
      <div className="memory-content">
        {viewMode === 'knowledge' ? (
          <KnowledgeGraphErrorBoundary onFallback={handleKnowledgeGraphError}>
            <Suspense fallback={<div style={{ padding: '2rem', color: 'var(--text-secondary)' }}>Loading 3D graph...</div>}>
              <KnowledgeGraph
                fetchKnowledgeGraph={fetchKnowledgeGraph}
                fetchEntityNeighbors={fetchEntityNeighbors}
                limit={knowledgeGraphLimit}
                onError={handleKnowledgeGraphError}
              />
            </Suspense>
          </KnowledgeGraphErrorBoundary>
        ) : viewMode === 'graph' ? (
          <MemoryGraph
            fetchGraphData={fetchGraphData}
            onSelect={handleSelect}
            memoryLimit={memoryGraphLimit}
          />
        ) : (
          <MemoryTable
            memories={filteredMemories}
            onSelect={handleSelect}
            onDelete={handleDelete}
            onUpdate={updateMemory}
            onEdit={handleEdit}
            isLoading={isLoading}
          />
        )}
      </div>

      {/* Detail slide-out panel — always rendered */}
      <MemoryDetail
        memory={selectedMemory}
        onEdit={handleDetailEdit}
        onDelete={handleDetailDelete}
        onClose={() => setSelectedMemory(null)}
      />

      {/* Create/Edit form modal */}
      {showForm && (
        <MemoryForm
          memory={editMemory}
          onSave={handleSave}
          onCancel={() => {
            setShowForm(false)
            setEditMemory(null)
          }}
        />
      )}
    </main>
  )
}
