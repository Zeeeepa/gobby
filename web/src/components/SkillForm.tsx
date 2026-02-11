import { useState, useCallback } from 'react'
import type { GobbySkill } from '../hooks/useSkills'
import { MemoizedMarkdown } from './MemoizedMarkdown'

export interface SkillFormData {
  name: string
  description: string
  content: string
  version: string
  license: string
  compatibility: string
  allowed_tools: string[]
  enabled: boolean
  always_apply: boolean
  injection_format: string
}

interface SkillFormProps {
  skill: GobbySkill | null
  onSave: (data: SkillFormData) => void
  onCancel: () => void
}

export function SkillForm({ skill, onSave, onCancel }: SkillFormProps) {
  const [name, setName] = useState(skill?.name || '')
  const [description, setDescription] = useState(skill?.description || '')
  const [content, setContent] = useState(skill?.content || '')
  const [version, setVersion] = useState(skill?.version || '')
  const [license, setLicense] = useState(skill?.license || '')
  const [compatibility, setCompatibility] = useState(skill?.compatibility || '')
  const [allowedToolsStr, setAllowedToolsStr] = useState(skill?.allowed_tools?.join(', ') || '')
  const [enabled, setEnabled] = useState(skill?.enabled ?? true)
  const [alwaysApply, setAlwaysApply] = useState(skill?.always_apply ?? false)
  const [injectionFormat, setInjectionFormat] = useState(skill?.injection_format || 'summary')

  const handleSubmit = useCallback((e: React.FormEvent) => {
    e.preventDefault()
    const tools = allowedToolsStr
      .split(',')
      .map(t => t.trim())
      .filter(Boolean)

    onSave({
      name,
      description,
      content,
      version,
      license,
      compatibility,
      allowed_tools: tools.length > 0 ? tools : [],
      enabled,
      always_apply: alwaysApply,
      injection_format: injectionFormat,
    })
  }, [name, description, content, version, license, compatibility, allowedToolsStr, enabled, alwaysApply, injectionFormat, onSave])

  return (
    <div className="skill-form-overlay" onClick={onCancel}>
      <div className="skill-form-modal" onClick={e => e.stopPropagation()}>
        <div className="skill-form-header">
          <h3>{skill ? 'Edit Skill' : 'New Skill'}</h3>
          <button className="skill-form-close" onClick={onCancel}>&times;</button>
        </div>

        <form onSubmit={handleSubmit} className="skill-form-body">
          <div className="skill-form-top">
            <div className="skill-form-fields">
              <div className="skill-form-row">
                <label className="skill-form-label">Name</label>
                <input
                  className="skill-form-input"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="my-skill"
                  required
                  disabled={!!skill}
                />
              </div>

              <div className="skill-form-row">
                <label className="skill-form-label">Description</label>
                <input
                  className="skill-form-input"
                  value={description}
                  onChange={e => setDescription(e.target.value)}
                  placeholder="What this skill does"
                  required
                />
              </div>

              <div className="skill-form-row-group">
                <div className="skill-form-row skill-form-row--half">
                  <label className="skill-form-label">Version</label>
                  <input
                    className="skill-form-input"
                    value={version}
                    onChange={e => setVersion(e.target.value)}
                    placeholder="1.0.0"
                  />
                </div>
                <div className="skill-form-row skill-form-row--half">
                  <label className="skill-form-label">License</label>
                  <input
                    className="skill-form-input"
                    value={license}
                    onChange={e => setLicense(e.target.value)}
                    placeholder="MIT"
                  />
                </div>
              </div>

              <div className="skill-form-row">
                <label className="skill-form-label">Compatibility</label>
                <input
                  className="skill-form-input"
                  value={compatibility}
                  onChange={e => setCompatibility(e.target.value)}
                  placeholder="Claude Code, Gemini CLI"
                />
              </div>

              <div className="skill-form-row">
                <label className="skill-form-label">Allowed Tools (comma-separated)</label>
                <input
                  className="skill-form-input"
                  value={allowedToolsStr}
                  onChange={e => setAllowedToolsStr(e.target.value)}
                  placeholder="Edit, Write, Bash"
                />
              </div>

              <div className="skill-form-row">
                <label className="skill-form-label">Injection Format</label>
                <select
                  className="skill-form-select"
                  value={injectionFormat}
                  onChange={e => setInjectionFormat(e.target.value)}
                >
                  <option value="summary">Summary</option>
                  <option value="full">Full</option>
                  <option value="content">Content Only</option>
                </select>
              </div>

              <div className="skill-form-checkboxes">
                <label className="skill-form-checkbox">
                  <input type="checkbox" checked={enabled} onChange={e => setEnabled(e.target.checked)} />
                  Enabled
                </label>
                <label className="skill-form-checkbox">
                  <input type="checkbox" checked={alwaysApply} onChange={e => setAlwaysApply(e.target.checked)} />
                  Always Apply
                </label>
              </div>
            </div>
          </div>

          <div className="skill-form-editor-container">
            <div className="skill-form-editor-pane">
              <label className="skill-form-label">Content (Markdown)</label>
              <textarea
                className="skill-form-textarea"
                value={content}
                onChange={e => setContent(e.target.value)}
                placeholder="# Skill Instructions&#10;&#10;Write your skill content here..."
                spellCheck={false}
              />
            </div>
            <div className="skill-form-preview-pane">
              <label className="skill-form-label">Preview</label>
              <div className="skill-form-preview-content">
                <MemoizedMarkdown content={content || '*No content yet*'} id="skill-form-preview" />
              </div>
            </div>
          </div>

          <div className="skill-form-footer">
            <button type="button" className="skill-form-cancel-btn" onClick={onCancel}>Cancel</button>
            <button type="submit" className="skill-form-save-btn">
              {skill ? 'Save Changes' : 'Create Skill'}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
