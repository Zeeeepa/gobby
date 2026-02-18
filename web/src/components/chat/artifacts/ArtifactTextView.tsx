import { useState } from 'react'
import { Markdown } from '../Markdown'
import { Button } from '../ui/Button'

interface ArtifactTextViewProps {
  content: string
  artifactId: string
}

export function ArtifactTextView({ content, artifactId }: ArtifactTextViewProps) {
  const [showSource, setShowSource] = useState(false)

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-end px-2 py-1 border-b border-border">
        <Button
          size="sm"
          variant="ghost"
          onClick={() => setShowSource(!showSource)}
          className="text-xs"
        >
          {showSource ? 'Preview' : 'Source'}
        </Button>
      </div>
      <div className="flex-1 min-h-0 overflow-auto p-4">
        {showSource ? (
          <pre className="text-sm font-mono text-foreground whitespace-pre-wrap">{content}</pre>
        ) : (
          <div className="prose prose-invert prose-sm max-w-none">
            <Markdown content={content} id={`artifact-text-${artifactId}`} />
          </div>
        )}
      </div>
    </div>
  )
}
