import { useState, useCallback, useMemo, useEffect } from 'react'
import { useMemory, useNeo4jStatus } from '../hooks/useMemory'
import type { GobbyMemory } from '../hooks/useMemory'
import { MemoryOverview } from './MemoryOverview'
import { MemoryFilters } from './MemoryFilters'
import { MemoryTable } from './MemoryTable'
import { MemoryGraph } from './MemoryGraph'
import { KnowledgeGraph } from './KnowledgeGraph'
import { MemoryForm } from './MemoryForm'
import type { MemoryFormData } from './MemoryForm'
import { MemoryDetail } from './MemoryDetail'

const TWENTY_FOUR_HOURS_MS = 24 * 60 * 60 * 1000

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
type OverviewFilter = 'total' | 'important' | 'recent' | null

export function MemoryPage() {
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
  const neo4jStatus = useNeo4jStatus()

  const [viewMode, setViewMode] = useState<ViewMode>('graph')
  const [showForm, setShowForm] = useState(false)

  // Default to knowledge view when Neo4j status loads and is configured
  useEffect(() => {
    if (neo4jStatus?.configured && viewMode === 'graph') {
      setViewMode('knowledge')
    }
  }, [neo4jStatus?.configured]) // eslint-disable-line react-hooks/exhaustive-deps
  const [editMemory, setEditMemory] = useState<GobbyMemory | null>(null)
  const [selectedMemory, setSelectedMemory] = useState<GobbyMemory | null>(null)
  const [overviewFilter, setOverviewFilter] = useState<OverviewFilter>(null)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const showError = useCallback((msg: string) => {
    setErrorMessage(msg)
    setTimeout(() => setErrorMessage(null), 4000)
  }, [])
  const [searchText, setSearchText] = useState('')

  // Apply overview filter + search to memories
  const filteredMemories = useMemo(() => {
    let result = memories

    if (overviewFilter === 'important') {
      result = result.filter(m => m.importance >= 0.7)
    } else if (overviewFilter === 'recent') {
      const cutoff = Date.now() - TWENTY_FOUR_HOURS_MS
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
  }, [memories, overviewFilter, searchText])

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
    [editMemory, createMemory, updateMemory]
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
    [deleteMemory, selectedMemory]
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
          <span className="memory-toolbar-count">{stats?.total_count ?? 0}</span>
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

      {/* Overview cards */}
      <MemoryOverview
        memories={memories}
        stats={stats}
        activeFilter={overviewFilter}
        onFilter={f => setOverviewFilter(f as OverviewFilter)}
      />

      {/* Filter bar */}
      <MemoryFilters
        filters={filters}
        stats={stats}
        onFiltersChange={setFilters}
      />

      {/* Content area */}
      <div className="memory-content">
        {viewMode === 'knowledge' ? (
          <KnowledgeGraph
            fetchKnowledgeGraph={fetchKnowledgeGraph}
            fetchEntityNeighbors={fetchEntityNeighbors}
          />
        ) : viewMode === 'graph' ? (
          <MemoryGraph
            memories={filteredMemories}
            fetchGraphData={fetchGraphData}
            onSelect={handleSelect}
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
