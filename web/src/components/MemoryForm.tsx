import { useState } from 'react'
import type { GobbyMemory } from '../hooks/useMemory'

interface MemoryFormProps {
  /** Pre-fill for edit mode, null for create mode */
  memory: GobbyMemory | null
  onSave: (data: MemoryFormData) => void
  onCancel: () => void
}

export interface MemoryFormData {
  content: string
  memory_type: string
  importance: number
  tags: string[]
}

const MEMORY_TYPES = ['fact', 'preference', 'pattern', 'context'] as const

export function MemoryForm({ memory, onSave, onCancel }: MemoryFormProps) {
  const [content, setContent] = useState(memory?.content ?? '')
  const [memoryType, setMemoryType] = useState(memory?.memory_type ?? 'fact')
  const [importance, setImportance] = useState(memory?.importance ?? 0.5)
  const [tags, setTags] = useState<string[]>(memory?.tags ?? [])
  const [tagInput, setTagInput] = useState('')
  const [error, setError] = useState<string | null>(null)

  const isEdit = memory !== null

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!content.trim()) {
      setError('Content is required')
      return
    }
    setError(null)
    onSave({
      content: content.trim(),
      memory_type: memoryType,
      importance,
      tags,
    })
  }

  function handleAddTag() {
    const tag = tagInput.trim()
    if (tag && !tags.includes(tag)) {
      setTags([...tags, tag])
    }
    setTagInput('')
  }

  function handleRemoveTag(tag: string) {
    setTags(tags.filter((t) => t !== tag))
  }

  function handleTagKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter') {
      e.preventDefault()
      handleAddTag()
    }
  }

  return (
    <div className="memory-form-overlay" onClick={onCancel}>
      <form
        className="memory-form"
        onSubmit={handleSubmit}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="memory-form-header">
          <h3>{isEdit ? 'Edit Memory' : 'Create Memory'}</h3>
          <button type="button" className="memory-form-close" onClick={onCancel}>
            &times;
          </button>
        </div>

        {error && <div className="memory-form-error">{error}</div>}

        <div className="memory-form-field">
          <label>Content</label>
          <textarea
            className="memory-form-textarea"
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="What should be remembered?"
            rows={4}
            autoFocus
          />
        </div>

        <div className="memory-form-row">
          <div className="memory-form-field">
            <label>Type</label>
            <select
              className="memory-form-select"
              value={memoryType}
              onChange={(e) => setMemoryType(e.target.value)}
            >
              {MEMORY_TYPES.map((t) => (
                <option key={t} value={t}>
                  {t.charAt(0).toUpperCase() + t.slice(1)}
                </option>
              ))}
            </select>
          </div>

          <div className="memory-form-field">
            <label>Importance: {(importance * 100).toFixed(0)}%</label>
            <input
              type="range"
              className="memory-form-slider"
              min="0"
              max="1"
              step="0.05"
              value={importance}
              onChange={(e) => setImportance(Number(e.target.value))}
            />
          </div>
        </div>

        <div className="memory-form-field">
          <label>Tags</label>
          <div className="memory-form-tags">
            {tags.map((tag) => (
              <span key={tag} className="memory-form-tag">
                {tag}
                <button
                  type="button"
                  className="memory-form-tag-remove"
                  onClick={() => handleRemoveTag(tag)}
                >
                  &times;
                </button>
              </span>
            ))}
            <input
              className="memory-form-tag-input"
              type="text"
              value={tagInput}
              onChange={(e) => setTagInput(e.target.value)}
              onKeyDown={handleTagKeyDown}
              placeholder="Add tag..."
            />
          </div>
        </div>

        <div className="memory-form-actions">
          <button type="button" className="memory-form-btn-cancel" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className="memory-form-btn-save">
            {isEdit ? 'Save Changes' : 'Create Memory'}
          </button>
        </div>
      </form>
    </div>
  )
}
