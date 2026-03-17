import { memo, useState, useEffect, useCallback } from 'react'

interface FilesTabProps {
  projectId?: string | null
}

interface FileEntry {
  name: string
  path: string
  is_dir: boolean
  size?: number
  extension?: string
  children?: FileEntry[]
  loaded?: boolean
}

export const FilesTab = memo(function FilesTab({ projectId }: FilesTabProps) {
  const [rootEntries, setRootEntries] = useState<FileEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedPaths, setExpandedPaths] = useState<Set<string>>(new Set())
  const [childrenMap, setChildrenMap] = useState<Map<string, FileEntry[]>>(new Map())
  const [selectedFile, setSelectedFile] = useState<string | null>(null)
  const [fileContent, setFileContent] = useState<string | null>(null)
  const [fileLoading, setFileLoading] = useState(false)

  // Fetch root directory
  useEffect(() => {
    if (!projectId) {
      setRootEntries([])
      setLoading(false)
      return
    }
    setLoading(true)
    const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
    fetch(`${baseUrl}/api/files/tree?project_id=${encodeURIComponent(projectId)}&path=`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => setRootEntries(Array.isArray(data) ? data : []))
      .catch(() => setRootEntries([]))
      .finally(() => setLoading(false))
  }, [projectId])

  const loadChildren = useCallback((dirPath: string) => {
    if (!projectId || childrenMap.has(dirPath)) return
    const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
    fetch(`${baseUrl}/api/files/tree?project_id=${encodeURIComponent(projectId)}&path=${encodeURIComponent(dirPath)}`)
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        setChildrenMap((prev) => {
          const next = new Map(prev)
          next.set(dirPath, Array.isArray(data) ? data : [])
          return next
        })
      })
      .catch(() => {
        setChildrenMap((prev) => {
          const next = new Map(prev)
          next.set(dirPath, [])
          return next
        })
      })
  }, [projectId, childrenMap])

  const toggleDir = useCallback((path: string) => {
    setExpandedPaths((prev) => {
      const next = new Set(prev)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
        loadChildren(path)
      }
      return next
    })
  }, [loadChildren])

  const openFile = useCallback((path: string) => {
    if (!projectId) return
    setSelectedFile(path)
    setFileLoading(true)
    setFileContent(null)
    const baseUrl = import.meta.env.VITE_API_BASE_URL || ''
    fetch(`${baseUrl}/api/files/read?project_id=${encodeURIComponent(projectId)}&path=${encodeURIComponent(path)}`)
      .then((res) => (res.ok ? res.json() : { content: 'Failed to load file' }))
      .then((data) => setFileContent(data.content ?? data.error ?? 'No content'))
      .catch(() => setFileContent('Error loading file'))
      .finally(() => setFileLoading(false))
  }, [projectId])

  if (loading) {
    return <div className="activity-tab-empty"><p>Loading files...</p></div>
  }

  if (!projectId) {
    return <div className="activity-tab-empty"><p>No project selected</p></div>
  }

  const renderEntry = (entry: FileEntry, depth: number) => {
    const isDir = entry.is_dir
    const isExpanded = expandedPaths.has(entry.path)
    const isSelected = entry.path === selectedFile
    const children = childrenMap.get(entry.path)

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
          {!isDir && entry.size != null && (
            <span className="text-[10px] text-muted-foreground ml-auto shrink-0">
              {entry.size < 1024 ? `${entry.size}B` : entry.size < 1048576 ? `${(entry.size / 1024).toFixed(0)}K` : `${(entry.size / 1048576).toFixed(1)}M`}
            </span>
          )}
        </div>
        {isDir && isExpanded && children?.map((c) => renderEntry(c, depth + 1))}
        {isDir && isExpanded && !children && (
          <div style={{ paddingLeft: `${22 + depth * 14}px` }} className="text-xs text-muted-foreground py-1">
            Loading...
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full">
      {/* File tree */}
      <div className={`overflow-y-auto ${selectedFile ? 'max-h-[40%] border-b border-border' : 'flex-1'}`}>
        {rootEntries.length === 0 ? (
          <div className="activity-tab-empty"><p>No files</p></div>
        ) : (
          rootEntries.map((e) => renderEntry(e, 0))
        )}
      </div>

      {/* File viewer */}
      {selectedFile && (
        <div className="flex-1 flex flex-col min-h-0">
          <div className="flex items-center justify-between px-3 py-1.5 border-b border-border bg-muted/30">
            <span className="text-xs text-foreground font-mono truncate">{selectedFile}</span>
            <button
              className="text-xs text-muted-foreground hover:text-foreground shrink-0 ml-2"
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
