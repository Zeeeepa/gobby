import { createContext, useContext } from 'react'
import type { ArtifactType } from '../../../types/artifacts'

interface ArtifactContextValue {
  openCodeAsArtifact: (language: string, content: string, title?: string) => void
  openFileAsArtifact: (type: ArtifactType, language: string, content: string, title?: string) => void
}

export const ArtifactContext = createContext<ArtifactContextValue | null>(null)

export function useArtifactContext() {
  const ctx = useContext(ArtifactContext)
  if (!ctx) {
    if (process.env.NODE_ENV === 'development') {
      console.warn('useArtifactContext: no ArtifactContext provider found, using no-op fallback')
    }
    return { openCodeAsArtifact: () => {}, openFileAsArtifact: () => {} }
  }
  return ctx
}
