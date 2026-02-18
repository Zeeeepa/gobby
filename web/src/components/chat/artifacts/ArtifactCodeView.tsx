import { useState } from 'react'
import { CodeMirrorEditor } from '../../CodeMirrorEditor'
import { Button } from '../ui/Button'

interface ArtifactCodeViewProps {
  content: string
  language?: string
  onChange?: (content: string) => void
}

export function ArtifactCodeView({ content, language = 'text', onChange }: ArtifactCodeViewProps) {
  const [isEditing, setIsEditing] = useState(false)

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-end px-2 py-1 border-b border-border">
        {onChange && (
          <Button
            size="sm"
            variant="ghost"
            onClick={() => setIsEditing(!isEditing)}
            className="text-xs"
          >
            {isEditing ? 'View' : 'Edit'}
          </Button>
        )}
      </div>
      <div className="flex-1 min-h-0 overflow-auto">
        <CodeMirrorEditor
          content={content}
          language={language}
          readOnly={!isEditing}
          onChange={isEditing ? onChange : undefined}
        />
      </div>
    </div>
  )
}
