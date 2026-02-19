import { useCallback } from 'react'
import type { Artifact } from '../../../types/artifacts'
import { Button } from '../ui/Button'
import { Badge } from '../ui/Badge'
import { ArtifactCodeView } from './ArtifactCodeView'
import { ArtifactTextView } from './ArtifactTextView'
import { ArtifactImageView } from './ArtifactImageView'
import { ArtifactSheetView } from './ArtifactSheetView'
import { ArtifactVersionBar } from './ArtifactVersionBar'

interface ArtifactPanelProps {
  artifact: Artifact
  width: number
  onClose: () => void
  onUpdateContent?: (id: string, content: string) => void
  onSetVersion: (id: string, index: number) => void
}

export function ArtifactPanel({ artifact, width, onClose, onUpdateContent, onSetVersion }: ArtifactPanelProps) {
  const versionIndex = Math.max(0, Math.min(artifact.currentVersionIndex, artifact.versions.length - 1))
  const currentVersion = artifact.versions[versionIndex]
  const content = currentVersion?.content ?? ''

  const handleCopy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(content)
    } catch {
      console.error('Failed to copy to clipboard')
    }
  }, [content])

  const handleDownload = useCallback(() => {
    const ext = artifact.type === 'code' ? (artifact.language || 'txt') : artifact.type === 'image' ? 'png' : artifact.type === 'sheet' ? 'csv' : 'txt'
    let blob: Blob
    if (artifact.type === 'image' && content.startsWith('data:')) {
      const commaIdx = content.indexOf(',')
      if (commaIdx === -1) {
        blob = new Blob([content], { type: 'application/octet-stream' })
      } else {
        const header = content.slice(0, commaIdx)
        const b64 = content.slice(commaIdx + 1)
        const mime = header.match(/data:(.*?);/)?.[1] || 'application/octet-stream'
        const binary = atob(b64)
        const bytes = new Uint8Array(binary.length)
        for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i)
        blob = new Blob([bytes], { type: mime })
      }
    } else {
      const mimeType = artifact.type === 'image' ? 'application/octet-stream' : 'text/plain'
      blob = new Blob([content], { type: mimeType })
    }
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    const safeName = artifact.title.replace(/[^\w\s.-]/g, '').replace(/\s+/g, '_') || 'artifact'
    a.download = `${safeName}.${ext}`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    setTimeout(() => URL.revokeObjectURL(url), 100)
  }, [content, artifact])

  return (
    <div
      className="flex flex-col h-full border-l border-border bg-background shrink-0"
      style={{ width }}
    >
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-border">
        <div className="flex-1 min-w-0">
          <div className="text-sm font-medium text-foreground truncate">{artifact.title}</div>
          <div className="flex items-center gap-1.5 mt-0.5">
            <Badge variant="default">{artifact.type}</Badge>
            {artifact.language && (
              <span className="text-xs text-muted-foreground font-mono">{artifact.language}</span>
            )}
          </div>
        </div>
        <Button size="icon" variant="ghost" onClick={handleCopy} title="Copy">
          <CopyIcon />
        </Button>
        <Button size="icon" variant="ghost" onClick={handleDownload} title="Download">
          <DownloadIcon />
        </Button>
        <Button size="icon" variant="ghost" onClick={onClose} title="Close panel">
          <CloseIcon />
        </Button>
      </div>

      {/* Content */}
      <div className="flex-1 min-h-0">
        {artifact.type === 'code' && (
          <ArtifactCodeView
            content={content}
            language={artifact.language}
            onChange={onUpdateContent ? (c) => onUpdateContent(artifact.id, c) : undefined}
          />
        )}
        {artifact.type === 'text' && (
          <ArtifactTextView content={content} artifactId={artifact.id} />
        )}
        {artifact.type === 'image' && (
          <ArtifactImageView content={content} />
        )}
        {artifact.type === 'sheet' && (
          <ArtifactSheetView content={content} />
        )}
      </div>

      {/* Version bar */}
      <ArtifactVersionBar
        artifact={artifact}
        onSetVersion={(index) => onSetVersion(artifact.id, index)}
      />
    </div>
  )
}

function CopyIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  )
}

function DownloadIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  )
}

function CloseIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  )
}
