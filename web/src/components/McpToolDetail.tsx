import { useState, useEffect } from 'react'
import type { McpToolSchema } from '../hooks/useMcp'

interface McpToolDetailProps {
  serverName: string | null
  toolName: string | null
  schema: McpToolSchema | null
  isLoading: boolean
  onClose: () => void
  onCallTool: (server: string, tool: string, args: Record<string, unknown>) => Promise<{ success: boolean; result?: unknown; error?: string }>
}

export function McpToolDetail({ serverName, toolName, schema, isLoading, onClose, onCallTool }: McpToolDetailProps) {
  const isOpen = serverName !== null && toolName !== null
  const [argsText, setArgsText] = useState('{}')
  const [executing, setExecuting] = useState(false)
  const [result, setResult] = useState<{ success: boolean; data: string } | null>(null)

  // Reset state when tool changes
  useEffect(() => {
    setArgsText('{}')
    setResult(null)
  }, [serverName, toolName])

  // Escape key handler
  useEffect(() => {
    if (!isOpen) return
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen, onClose])

  const handleExecute = async () => {
    if (!serverName || !toolName) return
    setExecuting(true)
    setResult(null)
    try {
      const args = JSON.parse(argsText)
      const res = await onCallTool(serverName, toolName, args)
      setResult({
        success: res.success,
        data: JSON.stringify(res.success ? res.result : res.error, null, 2),
      })
    } catch (e) {
      setResult({ success: false, data: String(e) })
    } finally {
      setExecuting(false)
    }
  }

  return (
    <>
      <div
        className={`mcp-detail-backdrop ${isOpen ? 'open' : ''}`}
        onClick={onClose}
      />
      <div className={`mcp-detail-slide ${isOpen ? 'open' : ''}`}>
        {isOpen && (
          <div className="mcp-detail">
            <div className="mcp-detail-header">
              <h3>{toolName}</h3>
              <button className="mcp-detail-close" onClick={onClose}>
                &times;
              </button>
            </div>

            {isLoading ? (
              <div className="mcp-loading">Loading schema...</div>
            ) : schema ? (
              <>
                <div className="mcp-detail-grid">
                  {schema.description && (
                    <>
                      <div className="mcp-detail-label">Description</div>
                      <div className="mcp-detail-value">{schema.description}</div>
                    </>
                  )}
                  <div className="mcp-detail-label">Server</div>
                  <div className="mcp-detail-value">{serverName}</div>
                </div>

                <div className="mcp-detail-section">
                  <h4>Input Schema</h4>
                  <pre className="mcp-detail-schema">
                    <code>{JSON.stringify(schema.inputSchema, null, 2)}</code>
                  </pre>
                </div>

                <div className="mcp-detail-section">
                  <h4>Execute</h4>
                  <textarea
                    className="mcp-detail-execute-area"
                    value={argsText}
                    onChange={e => setArgsText(e.target.value)}
                    placeholder='{"key": "value"}'
                  />
                  <button
                    className="mcp-detail-execute-btn"
                    onClick={handleExecute}
                    disabled={executing}
                  >
                    {executing ? 'Executing...' : 'Execute'}
                  </button>

                  {result && (
                    <pre className={`mcp-detail-result ${!result.success ? 'mcp-detail-result--error' : ''}`}>
                      {result.data}
                    </pre>
                  )}
                </div>
              </>
            ) : (
              <div className="mcp-loading">Failed to load schema</div>
            )}
          </div>
        )}
      </div>
    </>
  )
}
