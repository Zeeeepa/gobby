import { useState, useCallback } from 'react'
import type { GobbySkill, ScanResult } from '../hooks/useSkills'
import { MemoizedMarkdown } from './MemoizedMarkdown'
import { SkillScanPanel } from './SkillScanPanel'

interface SkillDetailProps {
  skill: GobbySkill | null
  onClose: () => void
  onEdit: (skill: GobbySkill) => void
  onExport: (skillId: string) => void
  onScan: (content: string, name: string) => Promise<ScanResult | null>
}

export function SkillDetail({ skill, onClose, onEdit, onExport, onScan }: SkillDetailProps) {
  const [scanResult, setScanResult] = useState<ScanResult | null>(null)
  const [scanning, setScanning] = useState(false)
  const [scanError, setScanError] = useState<string | null>(null)

  const handleScan = useCallback(async () => {
    if (!skill) return
    setScanning(true)
    setScanError(null)
    try {
      const result = await onScan(skill.content, skill.name)
      setScanResult(result)
    } catch (e) {
      setScanError(e instanceof Error ? e.message : 'Scan failed')
    } finally {
      setScanning(false)
    }
  }, [skill, onScan])

  if (!skill) return null

  const category = skill.metadata?.category
    || (skill.metadata?.skillport as Record<string, unknown>)?.category
    || null

  return (
    <div className="skills-detail">
      <div className="skills-detail-header">
        <h3 className="skills-detail-title">{skill.name}</h3>
        <button className="skills-detail-close" onClick={onClose} title="Close">&times;</button>
      </div>

      <div className="skills-detail-meta">
        <div className="skills-detail-meta-row">
          <span className="skills-detail-label">Status</span>
          <span className={`skills-detail-status ${skill.enabled ? 'skills-detail-status--enabled' : 'skills-detail-status--disabled'}`}>
            {skill.enabled ? 'Enabled' : 'Disabled'}
          </span>
        </div>
        {skill.version && (
          <div className="skills-detail-meta-row">
            <span className="skills-detail-label">Version</span>
            <span>{skill.version}</span>
          </div>
        )}
        {skill.source_type && (
          <div className="skills-detail-meta-row">
            <span className="skills-detail-label">Source</span>
            <span className={`skills-source-badge skills-source-badge--${skill.source_type}`}>{skill.source_type}</span>
          </div>
        )}
        {category && (
          <div className="skills-detail-meta-row">
            <span className="skills-detail-label">Category</span>
            <span>{String(category)}</span>
          </div>
        )}
        {skill.injection_format && (
          <div className="skills-detail-meta-row">
            <span className="skills-detail-label">Format</span>
            <span>{skill.injection_format}</span>
          </div>
        )}
        {skill.always_apply && (
          <div className="skills-detail-meta-row">
            <span className="skills-detail-label">Always Apply</span>
            <span>Yes</span>
          </div>
        )}
        {skill.hub_name && (
          <div className="skills-detail-meta-row">
            <span className="skills-detail-label">Hub</span>
            <span>{skill.hub_name}{skill.hub_slug ? ` / ${skill.hub_slug}` : ''}</span>
          </div>
        )}
        {skill.allowed_tools && skill.allowed_tools.length > 0 && (
          <div className="skills-detail-meta-row">
            <span className="skills-detail-label">Allowed Tools</span>
            <span>{skill.allowed_tools.join(', ')}</span>
          </div>
        )}
        <div className="skills-detail-meta-row">
          <span className="skills-detail-label">Updated</span>
          <span>{new Date(skill.updated_at).toLocaleString()}</span>
        </div>
      </div>

      <div className="skills-detail-description">{skill.description}</div>

      <div className="skills-detail-actions">
        <button className="skills-detail-action-btn" onClick={() => onEdit(skill)}>Edit</button>
        <button className="skills-detail-action-btn" onClick={() => onExport(skill.id)}>Export</button>
        <button
          className="skills-detail-action-btn skills-detail-action-btn--scan"
          onClick={handleScan}
          disabled={scanning}
        >
          {scanning ? 'Scanning...' : 'Safety Scan'}
        </button>
      </div>

      {scanError && <div className="skills-detail-scan-error">{scanError}</div>}
      {scanResult && <SkillScanPanel result={scanResult} />}

      <div className="skills-detail-content">
        <MemoizedMarkdown content={skill.content} id={`skill-detail-${skill.id}`} />
      </div>
    </div>
  )
}
