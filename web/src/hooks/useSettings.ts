import { useState, useEffect, useCallback } from 'react'
import type { ChatMode } from '../types/chat'

export type Theme = 'dark' | 'light' | 'system'

export interface Settings {
  fontSize: number // Base font size in pixels (12-24)
  model: string // Selected LLM model short name
  chatMode: ChatMode // Active chat mode
  theme: Theme // UI theme
}

export const MODEL_OPTIONS = [
  { value: 'opus', label: 'Claude Opus' },
  { value: 'sonnet', label: 'Claude Sonnet' },
  { value: 'haiku', label: 'Claude Haiku' },
] as const

const DEFAULT_SETTINGS: Settings = {
  fontSize: 16,
  model: 'opus',
  chatMode: 'bypass',
  theme: 'dark',
}

const STORAGE_KEY = 'gobby-settings'

export function useSettings() {
  const [settings, setSettings] = useState<Settings>(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY)
      if (stored) {
        return { ...DEFAULT_SETTINGS, ...JSON.parse(stored) }
      }
    } catch (e) {
      console.error('Failed to load settings:', e)
    }
    return DEFAULT_SETTINGS
  })
  // Apply font size to document
  useEffect(() => {
    document.documentElement.style.setProperty(
      '--font-size-base',
      `${settings.fontSize}px`
    )
  }, [settings.fontSize])

  // Apply theme to document
  useEffect(() => {
    const applyTheme = (resolved: 'dark' | 'light') => {
      document.documentElement.setAttribute('data-theme', resolved)
    }

    if (settings.theme === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)')
      applyTheme(mq.matches ? 'dark' : 'light')
      const handler = (e: MediaQueryListEvent) => applyTheme(e.matches ? 'dark' : 'light')
      mq.addEventListener('change', handler)
      return () => mq.removeEventListener('change', handler)
    } else {
      applyTheme(settings.theme)
    }
  }, [settings.theme])

  // Persist settings
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
    } catch (e) {
      console.error('Failed to save settings:', e)
    }
  }, [settings])

  const updateFontSize = useCallback((size: number) => {
    setSettings((prev) => ({ ...prev, fontSize: size }))
  }, [])

  const updateModel = useCallback((model: string) => {
    setSettings((prev) => ({ ...prev, model }))
  }, [])

  const updateChatMode = useCallback((chatMode: ChatMode) => {
    setSettings((prev) => ({ ...prev, chatMode }))
  }, [])

  const updateTheme = useCallback((theme: Theme) => {
    setSettings((prev) => ({ ...prev, theme }))
  }, [])

  const resetSettings = useCallback(() => {
    setSettings(DEFAULT_SETTINGS)
  }, [])

  return {
    settings,
    updateFontSize,
    updateModel,
    updateChatMode,
    updateTheme,
    resetSettings,
  }
}
