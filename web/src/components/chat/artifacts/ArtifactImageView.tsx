import { useState } from 'react'
import { Button } from '../ui/Button'

interface ArtifactImageViewProps {
  content: string
}

export function ArtifactImageView({ content }: ArtifactImageViewProps) {
  const [zoom, setZoom] = useState(100)

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center gap-2 px-2 py-1 border-b border-border">
        <Button size="sm" variant="ghost" onClick={() => setZoom(Math.max(25, zoom - 25))} className="text-xs">-</Button>
        <span className="text-xs text-muted-foreground">{zoom}%</span>
        <Button size="sm" variant="ghost" onClick={() => setZoom(Math.min(400, zoom + 25))} className="text-xs">+</Button>
        <Button size="sm" variant="ghost" onClick={() => setZoom(100)} className="text-xs">Reset</Button>
      </div>
      <div className="flex-1 min-h-0 overflow-auto flex items-center justify-center p-4">
        {/^(https?:|data:image\/|\/|\.\/)/.test(content) ? (
          <img
            src={content}
            alt="Artifact"
            style={{ width: `${zoom}%`, maxWidth: 'none' }}
            className="object-contain"
          />
        ) : (
          <span className="text-sm text-muted-foreground">Invalid image source</span>
        )}
      </div>
    </div>
  )
}
