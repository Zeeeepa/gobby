import { useState, useEffect, useCallback } from 'react'

export interface Settings {
  fontSize: number // Base font size in pixels (12-24)
}

const DEFAULT_SETTINGS: Settings = {
  fontSize: 16,
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

  const resetSettings = useCallback(() => {
    setSettings(DEFAULT_SETTINGS)
  }, [])

  return {
    settings,
    updateFontSize,
    resetSettings,
  }
}
