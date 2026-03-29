export type ArtifactType = 'code' | 'text' | 'image' | 'sheet'

export interface ArtifactVersion {
  content: string
  messageId?: string
  timestamp: Date
}

export interface Artifact {
  id: string
  type: ArtifactType
  title: string
  language?: string
  versions: ArtifactVersion[]
  currentVersionIndex: number
  isPlan?: boolean
}
