import { useState } from 'react'

interface McpAddServerModalProps {
  onAdd: (params: {
    name: string
    transport: string
    url?: string
    command?: string
    args?: string[]
    enabled?: boolean
  }) => Promise<boolean>
  onClose: () => void
}

export function McpAddServerModal({ onAdd, onClose }: McpAddServerModalProps) {
  const [name, setName] = useState('')
  const [transport, setTransport] = useState('http')
  const [url, setUrl] = useState('')
  const [command, setCommand] = useState('')
  const [args, setArgs] = useState('')
  const [enabled, setEnabled] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const needsUrl = transport === 'http' || transport === 'websocket' || transport === 'sse'
  const needsCommand = transport === 'stdio'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!name.trim()) { setError('Name is required'); return }
    if (needsUrl && !url.trim()) { setError('URL is required'); return }
    if (needsCommand && !command.trim()) { setError('Command is required'); return }

    setSaving(true)
    setError(null)
    const params: Parameters<typeof onAdd>[0] = {
      name: name.trim(),
      transport,
      enabled,
    }
    if (needsUrl) params.url = url.trim()
    if (needsCommand) {
      params.command = command.trim()
      if (args.trim()) params.args = args.trim().split(/\s+/)
    }

    const ok = await onAdd(params)
    setSaving(false)
    if (ok) onClose()
    else setError('Failed to add server')
  }

  return (
    <div className="mcp-modal-overlay" onClick={onClose}>
      <form className="mcp-modal" onClick={e => e.stopPropagation()} onSubmit={handleSubmit}>
        <h3>Add MCP Server</h3>

        {error && <div className="mcp-form-error">{error}</div>}

        <div className="mcp-form-row">
          <div className="mcp-form-group">
            <label className="mcp-form-label">Name</label>
            <input
              className="mcp-form-input"
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="my-server"
              autoFocus
            />
          </div>
          <div className="mcp-form-group">
            <label className="mcp-form-label">Transport</label>
            <select className="mcp-form-select" value={transport} onChange={e => setTransport(e.target.value)}>
              <option value="http">HTTP</option>
              <option value="stdio">Stdio</option>
              <option value="websocket">WebSocket</option>
              <option value="sse">SSE</option>
            </select>
          </div>
        </div>

        {needsUrl && (
          <div className="mcp-form-group">
            <label className="mcp-form-label">URL</label>
            <input
              className="mcp-form-input"
              value={url}
              onChange={e => setUrl(e.target.value)}
              placeholder="http://localhost:8080"
            />
          </div>
        )}

        {needsCommand && (
          <>
            <div className="mcp-form-group">
              <label className="mcp-form-label">Command</label>
              <input
                className="mcp-form-input"
                value={command}
                onChange={e => setCommand(e.target.value)}
                placeholder="npx"
              />
            </div>
            <div className="mcp-form-group">
              <label className="mcp-form-label">Arguments (space-separated)</label>
              <input
                className="mcp-form-input"
                value={args}
                onChange={e => setArgs(e.target.value)}
                placeholder="-y @modelcontextprotocol/server-x"
              />
            </div>
          </>
        )}

        <div className="mcp-form-group">
          <label className="mcp-form-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <input
              type="checkbox"
              checked={enabled}
              onChange={e => setEnabled(e.target.checked)}
            />
            Enabled
          </label>
        </div>

        <div className="mcp-modal-actions">
          <button type="button" className="mcp-modal-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="mcp-modal-btn mcp-modal-btn--primary" disabled={saving}>
            {saving ? 'Adding...' : 'Add Server'}
          </button>
        </div>
      </form>
    </div>
  )
}

interface McpImportModalProps {
  onImport: (params: {
    from_project?: string
    github_url?: string
    query?: string
  }) => Promise<boolean>
  onClose: () => void
}

export function McpImportModal({ onImport, onClose }: McpImportModalProps) {
  const [activeTab, setActiveTab] = useState<'project' | 'github' | 'search'>('github')
  const [value, setValue] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [importing, setImporting] = useState(false)

  const placeholder = activeTab === 'project'
    ? 'other-project-name'
    : activeTab === 'github'
      ? 'https://github.com/org/mcp-server'
      : 'search query...'

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!value.trim()) { setError('Value is required'); return }

    setImporting(true)
    setError(null)
    const params: Parameters<typeof onImport>[0] = {}
    if (activeTab === 'project') params.from_project = value.trim()
    else if (activeTab === 'github') params.github_url = value.trim()
    else params.query = value.trim()

    const ok = await onImport(params)
    setImporting(false)
    if (ok) onClose()
    else setError('Import failed')
  }

  return (
    <div className="mcp-modal-overlay" onClick={onClose}>
      <form className="mcp-modal" onClick={e => e.stopPropagation()} onSubmit={handleSubmit}>
        <h3>Import MCP Server</h3>

        <div className="mcp-import-tabs">
          <button
            type="button"
            className={`mcp-import-tab ${activeTab === 'project' ? 'mcp-import-tab--active' : ''}`}
            onClick={() => { setActiveTab('project'); setValue(''); setError(null) }}
          >
            From Project
          </button>
          <button
            type="button"
            className={`mcp-import-tab ${activeTab === 'github' ? 'mcp-import-tab--active' : ''}`}
            onClick={() => { setActiveTab('github'); setValue(''); setError(null) }}
          >
            GitHub URL
          </button>
          <button
            type="button"
            className={`mcp-import-tab ${activeTab === 'search' ? 'mcp-import-tab--active' : ''}`}
            onClick={() => { setActiveTab('search'); setValue(''); setError(null) }}
          >
            Search
          </button>
        </div>

        {error && <div className="mcp-form-error">{error}</div>}

        <div className="mcp-form-group">
          <label className="mcp-form-label">
            {activeTab === 'project' ? 'Project Name' : activeTab === 'github' ? 'GitHub URL' : 'Search Query'}
          </label>
          <input
            className="mcp-form-input"
            value={value}
            onChange={e => setValue(e.target.value)}
            placeholder={placeholder}
            autoFocus
          />
        </div>

        <div className="mcp-modal-actions">
          <button type="button" className="mcp-modal-btn" onClick={onClose}>Cancel</button>
          <button type="submit" className="mcp-modal-btn mcp-modal-btn--primary" disabled={importing}>
            {importing ? 'Importing...' : 'Import'}
          </button>
        </div>
      </form>
    </div>
  )
}
