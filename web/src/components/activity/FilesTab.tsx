import { memo, useState, useEffect, useCallback } from 'react'

interface FilesTabProps {
  projectId?: string | null
}

interface FileEntry {
  name: string
  path: string
  type: 'file' | 'directory'
  children?: FileEntry[]
}

export const FilesTab = memo(function FilesTab({ projectId }: FilesTabProps) {
  const [tree, setTree] = useState<FileEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set())
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [fileLoading, setFileLoading] = useState(false)

  useEffect(() => {
    setLoading(true)
    const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
    const params = new URLSearchParams()
    if (projectId) params.set('project_id', projectId)
    fetch(`${baseUrl}/api/files?${params}`)
      .then((res) => (res.ok ? res.json() : { entries: [] }))
      .then((data) => setTree(data.entries ?? []))
      .catch(() => setTree([]))
      .finally(() => setLoading(false))
  }, [projectId])

  const toggleDir = useCallback((path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev)
      if (next.has(path)) next.delete(path)
      else next.add(path)
      return next
    })
  }, [])

  const openFile = useCallback((path: string) => {
    setSelectedFile(path)
    setFileLoading(true)
    setFileContent(null)
    const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
    fetch(`${baseUrl}/api/files/content?path=${encodeURIComponent(path)}`)
      .then((res) => (res.ok ? res.text() : 'Failed to load file'))
      .then(setFileContent)
      .catch(() => setFileContent('Error loading file'))
      .finally(() => setFileLoading(false))
  }, [])

  if (loading) {
    return <div className="activity-tab-empty"><p>Loading files...</p></div>
  }

  const renderEntry = (entry: FileEntry, depth: number) => {
    const isDir = entry.type === 'directory'
    const isExpanded = expandedPaths.has(entry.path)
    const isSelected = entry.path === selectedFile

    return (
      <div key={entry.path}>
        <div
          className={`flex items-center gap-1.5 px-2 py-1 hover:bg-muted/50 cursor-pointer text-sm${isSelected ? ' bg-muted' : ''}`}
          style={{ paddingLeft: `${8 + depth * 14}px` }}
          onClick={() => isDir ? toggleDir(entry.path) : openFile(entry.path)}
        >
          {isDir ? (
            <span className="text-[10px] text-muted-foreground w-3 text-center shrink-0">
              {isExpanded ? '\u25BC' : '\u25B6'}
            </span>
          ) : (
            <span className="w-3 shrink-0" />
          )}
          <span className="text-xs shrink-0">{isDir ? '\uD83D\uDCC1' : '\uD83D\uDCC4'}</span>
          <span className="text-foreground truncate">{entry.name}</span>
        </div>
        {isDir && isExpanded && entry.children?.map((c) => renderEntry(c, depth + 1))}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* File tree */}
      <div className={`overflow-y-auto ${selectedFile ? 'max-h-[40%] border-b border-border' : 'flex-1'}`}>
        {tree.length === 0 ? (
          <div className="activity-tab-empty"><p>No files</p></div>
        ) : (
          tree.map((e) => renderEntry(e, 0))
        )}
      </div>

      {/* File viewer */}
      {selectedFile && (
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-muted/30">
            <span className="text-xs text-foreground font-mono truncate">{selectedFile}</span>
            <button
              className="text-xs text-muted-foreground hover:text-foreground"
              onClick={() => { setSelectedFile(null); setFileContent(null) }}
            >
              Close
            </button>
          </div>
          <div className="flex-1 overflow-auto">
            {fileLoading ? (
              <div className="p-3 text-xs text-muted-foreground">Loading...</div>
            ) : (
              <pre className="p-3 text-xs font-mono text-foreground whitespace-pre-wrap break-words">
                {fileContent}
              </pre>
            )}
          </div>
        </div>
      )}
    </div>
  )
})
