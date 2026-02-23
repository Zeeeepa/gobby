import { useState } from 'react'
import { Markdown } from '../Markdown'
import { CodeMirrorEditor } from '../../CodeMirrorEditor'
import { Button } from '../ui/Button'

interface ArtifactTextViewProps {
  content: string
  artifactId: string
  onChange?: (content: string) => void
}

export function ArtifactTextView({ content, artifactId, onChange }: ArtifactTextViewProps) {
  const [showSource, setShowSource] = useState(false)
  const [isEditing, setIsEditing] = useState(false)

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-end px-2 py-1 border-b border-border">
        {onChange ? (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setIsEditing(!isEditing)}
            className="text-xs"
          >
            {isEditing ? 'View' : 'Edit'}
          </Button>
        ) : (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setShowSource(!showSource)}
            className="text-xs"
          >
            {showSource ? 'Preview' : 'Source'}
          </Button>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        {onChange && isEditing ? (
          <CodeMirrorEditor
            content={content}
            language="markdown"
            readOnly={false}
            onChange={onChange}
          />
        ) : showSource && !onChange ? (
          <pre className="text-sm font-mono text-foreground whitespace-pre-wrap p-4">{content}</pre>
        ) : (
          <div className="prose dark:prose-invert prose-sm max-w-none p-4">
            <Markdown content={content} id={`artifact-text-${artifactId}`} />
          </div>
        )}
      </div>
    </div>
  )
}
