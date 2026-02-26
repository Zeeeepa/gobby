import { CodeMirrorEditor } from '../../shared/CodeMirrorEditor'

interface ArtifactCodeViewProps {
  content: string
  language?: string
  isEditing?: boolean
  onChange?: (content: string) => void
}

export function ArtifactCodeView({ content, language = 'text', isEditing = false, onChange }: ArtifactCodeViewProps) {
  return (
    <div className="flex flex-col h-full">
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
