import { useState, useCallback } from 'react'
import type { Artifact, ArtifactType } from '../types/artifacts'

const PANEL_WIDTH_KEY = 'gobby-artifact-panel-width'

function loadPanelWidth(): number {
  try {
    const stored = localStorage.getItem(PANEL_WIDTH_KEY)
    if (stored) return Math.max(300, Math.min(800, parseInt(stored, 10)))
  } catch {}
  return 480
}

function savePanelWidth(width: number): void {
  try { localStorage.setItem(PANEL_WIDTH_KEY, String(width)) } catch {}
}

export function useArtifacts() {
  const [artifacts, setArtifacts] = useState<Map<string, Artifact>>(new Map())
  const [activeArtifactId, setActiveArtifactId] = useState<string | null>(null)
  const [isPanelOpen, setIsPanelOpen] = useState(false)
  const [panelWidth, setPanelWidth] = useState(loadPanelWidth)

  const createArtifact = useCallback((
    type: ArtifactType,
    content: string,
    language?: string,
    title?: string,
  ): string => {
    const id = `artifact-${crypto.randomUUID().slice(0, 8)}`
    const artifact: Artifact = {
      id,
      type,
      title: title || `Artifact`,
      language,
      versions: [{ content, timestamp: new Date() }],
      currentVersionIndex: 0,
    }
    setArtifacts((prev) => {
      const next = new Map(prev)
      next.set(id, artifact)
      return next
    })
    setActiveArtifactId(id)
    setIsPanelOpen(true)
    return id
  }, [])

  const updateArtifact = useCallback((id: string, content: string, messageId?: string) => {
    setArtifacts((prev) => {
      const existing = prev.get(id)
      if (!existing) return prev
      const next = new Map(prev)
      const versions = [...existing.versions, { content, messageId, timestamp: new Date() }]
      next.set(id, { ...existing, versions, currentVersionIndex: versions.length - 1 })
      return next
    })
  }, [])

  const openArtifact = useCallback((id: string) => {
    setActiveArtifactId(id)
    setIsPanelOpen(true)
  }, [])

  const closePanel = useCallback(() => {
    setIsPanelOpen(false)
  }, [])

  const setVersion = useCallback((id: string, index: number) => {
    setArtifacts((prev) => {
      const existing = prev.get(id)
      if (!existing || index < 0 || index >= existing.versions.length) return prev
      const next = new Map(prev)
      next.set(id, { ...existing, currentVersionIndex: index })
      return next
    })
  }, [])

  const handlePanelWidthChange = useCallback((width: number) => {
    setPanelWidth(width)
    savePanelWidth(width)
  }, [])

  const activeArtifact = activeArtifactId ? artifacts.get(activeArtifactId) ?? null : null

  return {
    artifacts,
    activeArtifactId,
    activeArtifact,
    isPanelOpen,
    panelWidth,
    createArtifact,
    updateArtifact,
    openArtifact,
    closePanel,
    setVersion,
    setPanelWidth: handlePanelWidthChange,
  }
}
