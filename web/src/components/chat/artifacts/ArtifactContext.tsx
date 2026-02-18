import { createContext, useContext } from 'react'

interface ArtifactContextValue {
  openCodeAsArtifact: (language: string, content: string, title?: string) => void
}

export const ArtifactContext = createContext<ArtifactContextValue | null>(null)

export function useArtifactContext() {
  const ctx = useContext(ArtifactContext)
  if (!ctx) {
    return { openCodeAsArtifact: () => {} }
  }
  return ctx
}
