import { useState, useCallback } from 'react'

interface SkillImportModalProps {
  onImport: (source: string) => Promise<void>
  onClose: () => void
}

function detectSourceType(source: string): string {
  const s = source.trim()
  if (s.startsWith('github:') || s.startsWith('https://github.com') || s.startsWith('http://github.com')) return 'github'
  if (s.endsWith('.zip')) return 'zip'
  if (s.startsWith('/') || s.startsWith('./') || s.startsWith('~')) return 'local'
  if (s.includes('/') && !s.startsWith('http')) return 'github'
  return 'unknown'
}

export function SkillImportModal({ onImport, onClose }: SkillImportModalProps) {
  const [source, setSource] = useState('')
  const [importing, setImporting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const sourceType = source.trim() ? detectSourceType(source) : null

  const handleImport = useCallback(async () => {
    if (!source.trim()) return
    setImporting(true)
    setError(null)
    try {
      await onImport(source.trim())
      onClose()
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Import failed')
    } finally {
      setImporting(false)
    }
  }, [source, onImport, onClose])

  const handleKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !importing) handleImport()
    if (e.key === 'Escape') onClose()
  }, [handleImport, importing, onClose])

  return (
    <div className="skill-import-overlay" onClick={onClose}>
      <div className="skill-import-modal" onClick={e => e.stopPropagation()}>
        <div className="skill-import-header">
          <h3>Import Skill</h3>
          <button className="skill-import-close" onClick={onClose}>&times;</button>
        </div>

        <div className="skill-import-body">
          <label className="skill-import-label">Source URL or Path</label>
          <input
            className="skill-import-input"
            value={source}
            onChange={e => setSource(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="github:owner/repo, /path/to/skill, or file.zip"
            autoFocus
          />

          {sourceType && (
            <span className={`skills-source-badge skills-source-badge--${sourceType}`}>
              {sourceType}
            </span>
          )}

          {error && <div className="skill-import-error">{error}</div>}
        </div>

        <div className="skill-import-footer">
          <button className="skill-form-cancel-btn" onClick={onClose}>Cancel</button>
          <button
            className="skill-form-save-btn"
            onClick={handleImport}
            disabled={!source.trim() || importing}
          >
            {importing ? 'Importing...' : 'Import'}
          </button>
        </div>
      </div>
    </div>
  )
}
