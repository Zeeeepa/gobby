import { useState, useEffect, useCallback } from 'react'

export interface Settings {
  fontSize: number // Base font size in pixels (12-24)
  model: string | null // Selected LLM model
  provider: string | null // Selected LLM provider
}

export interface ModelInfo {
  models: string[]
  default_model: string | null
}

const DEFAULT_SETTINGS: Settings = {
  fontSize: 16,
  model: null,
  provider: null,
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
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null)
  const [modelsLoading, setModelsLoading] = useState(true)

  // Fetch available Claude models on mount
  useEffect(() => {
    const fetchModels = async () => {
      try {
        // Use same host logic as WebSocket - HTTPS uses relative path, HTTP uses daemon port
        const baseUrl = ''

        const response = await fetch(`${baseUrl}/admin/models?provider=claude`)
        if (response.ok) {
          const data = await response.json()
          // Flatten: { models: { claude: [...] }, default_model } -> { models: [...], default_model }
          const claudeModels: string[] = data.models?.claude || []
          setModelInfo({ models: claudeModels, default_model: data.default_model })

          // Set defaults if not already set
          setSettings(prev => {
            if (!prev.model && data.default_model) {
              return {
                ...prev,
                model: data.default_model,
                provider: 'claude',
              }
            }
            return prev
          })
        }
      } catch (e) {
        console.error('Failed to fetch models:', e)
      } finally {
        setModelsLoading(false)
      }
    }

    fetchModels()
  }, [])

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

  const updateModel = useCallback((model: string) => {
    setSettings((prev) => ({ ...prev, model, provider: 'claude' }))
  }, [])

  const resetSettings = useCallback(() => {
    setSettings({
      ...DEFAULT_SETTINGS,
      model: modelInfo?.default_model || null,
      provider: 'claude',
    })
  }, [modelInfo])

  return {
    settings,
    modelInfo,
    modelsLoading,
    updateFontSize,
    updateModel,
    resetSettings,
  }
}
