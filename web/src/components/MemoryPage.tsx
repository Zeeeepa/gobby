import { useState, useCallback } from 'react'
import { useMemory, useMem0Status } from '../hooks/useMemory'
import type { GobbyMemory } from '../hooks/useMemory'
import { MemoryTable } from './MemoryTable'
import { MemoryForm } from './MemoryForm'
import type { MemoryFormData } from './MemoryForm'
import { MemoryDetail } from './MemoryDetail'

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
  } = useMemory()
  const mem0Status = useMem0Status()

  const [showForm, setShowForm] = useState(false)
  const [editMemory, setEditMemory] = useState<GobbyMemory | null>(null)
  const [selectedMemory, setSelectedMemory] = useState<GobbyMemory | null>(null)

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
    },
    [editMemory, createMemory, updateMemory]
  )

  const handleDelete = useCallback(
    async (memoryId: string) => {
      await deleteMemory(memoryId)
      if (selectedMemory?.id === memoryId) {
        setSelectedMemory(null)
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

  return (
    <main className="memory-page-root">
      <div className="memory-page-header">
        <div className="memory-page-header-left">
          <h2 className="memory-page-title">Memory</h2>
          {mem0Status?.configured && (
            <a
              className="mem0-badge"
              href={mem0Status.url}
              target="_blank"
              rel="noopener noreferrer"
              title={`Mem0 at ${mem0Status.url}`}
            >
              Powered by mem0
            </a>
          )}
        </div>
        <button className="memory-create-btn" onClick={handleCreate}>
          + Create Memory
        </button>
      </div>

      <MemoryTable
        memories={memories}
        stats={stats}
        filters={filters}
        onFiltersChange={setFilters}
        onDelete={handleDelete}
        isLoading={isLoading}
        onRefresh={refreshMemories}
        onSelect={handleSelect}
        onEdit={handleEdit}
      />

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

      {selectedMemory && !showForm && (
        <div className="memory-detail-overlay" onClick={() => setSelectedMemory(null)}>
          <div className="memory-detail-panel" onClick={(e) => e.stopPropagation()}>
            <MemoryDetail
              memory={selectedMemory}
              onEdit={handleDetailEdit}
              onDelete={handleDetailDelete}
              onClose={() => setSelectedMemory(null)}
            />
          </div>
        </div>
      )}
    </main>
  )
}
