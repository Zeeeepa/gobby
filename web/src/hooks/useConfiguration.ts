import { useState, useCallback } from 'react'

// =============================================================================
// Types
// =============================================================================

export interface SecretInfo {
  id: string
  name: string
  category: string
  description: string | null
  created_at: string
  updated_at: string
}

export interface PromptInfo {
  path: string
  description: string
  category: string
  source: 'bundled' | 'overridden'
  has_override: boolean
}

export interface PromptDetail {
  path: string
  description: string
  content: string
  source: 'bundled' | 'overridden'
  has_override: boolean
  bundled_content: string | null
  variables: Record<string, { type: string; required: boolean; default: unknown }>
}

export interface ConfigExportBundle {
  version: number
  exported_at: string
  config: Record<string, unknown>
  prompts: Record<string, string>
  secrets: SecretInfo[]
}

// =============================================================================
// Hook
// =============================================================================

export function useConfiguration() {
  // Schema + Config
  const [schema, setSchema] = useState<Record<string, unknown> | null>(null)
  const [configValues, setConfigValues] = useState<Record<string, unknown>>({})
  const [isLoading, setIsLoading] = useState(false)

  // Raw YAML
  const [yamlContent, setYamlContent] = useState('')

  // Secrets
  const [secrets, setSecrets] = useState<SecretInfo[]>([])
  const [secretCategories, setSecretCategories] = useState<string[]>([])

  // Prompts
  const [prompts, setPrompts] = useState<PromptInfo[]>([])
  const [promptCategories, setPromptCategories] = useState<Record<string, number>>({})

  // =========================================================================
  // Schema + Config
  // =========================================================================

  const fetchSchema = useCallback(async () => {
    try {
      const res = await fetch('/api/config/schema')
      if (res.ok) {
        const data = await res.json()
        setSchema(data)
      }
    } catch (e) {
      console.error('Failed to fetch config schema:', e)
    }
  }, [])

  const fetchConfigValues = useCallback(async () => {
    try {
      const res = await fetch('/api/config/values')
      if (res.ok) {
        const data = await res.json()
        setConfigValues(data)
      }
    } catch (e) {
      console.error('Failed to fetch config values:', e)
    }
  }, [])

  const fetchConfig = useCallback(async () => {
    setIsLoading(true)
    try {
      await Promise.all([fetchSchema(), fetchConfigValues()])
    } finally {
      setIsLoading(false)
    }
  }, [fetchSchema, fetchConfigValues])

  const saveConfig = useCallback(async (values: Record<string, unknown>): Promise<{ ok: boolean; errors?: string[] }> => {
    try {
      const res = await fetch('/api/config/values', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values }),
      })
      const data = await res.json()
      if (res.ok) return { ok: true }
      return { ok: false, errors: [data.detail || 'Save failed'] }
    } catch (e) {
      return { ok: false, errors: [String(e)] }
    }
  }, [])

  const validateConfig = useCallback(async (values: Record<string, unknown>): Promise<string[]> => {
    try {
      const res = await fetch('/api/config/values/validate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ values }),
      })
      const data = await res.json()
      return data.errors || []
    } catch (e) {
      return [String(e)]
    }
  }, [])

  const resetToDefaults = useCallback(async (): Promise<boolean> => {
    try {
      const res = await fetch('/api/config/values/reset', { method: 'POST' })
      return res.ok
    } catch {
      return false
    }
  }, [])

  // =========================================================================
  // Raw YAML
  // =========================================================================

  const fetchYaml = useCallback(async () => {
    try {
      const res = await fetch('/api/config/yaml')
      if (res.ok) {
        const data = await res.json()
        setYamlContent(data.content || '')
      }
    } catch (e) {
      console.error('Failed to fetch YAML:', e)
    }
  }, [])

  const saveYaml = useCallback(async (content: string): Promise<{ ok: boolean; errors?: string[] }> => {
    try {
      const res = await fetch('/api/config/yaml', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      })
      const data = await res.json()
      if (res.ok) return { ok: true }
      return { ok: false, errors: [data.detail || 'Save failed'] }
    } catch (e) {
      return { ok: false, errors: [String(e)] }
    }
  }, [])

  // =========================================================================
  // Secrets
  // =========================================================================

  const fetchSecrets = useCallback(async () => {
    try {
      const res = await fetch('/api/config/secrets')
      if (res.ok) {
        const data = await res.json()
        setSecrets(data.secrets || [])
        setSecretCategories(data.categories || [])
      }
    } catch (e) {
      console.error('Failed to fetch secrets:', e)
    }
  }, [])

  const saveSecret = useCallback(async (
    name: string,
    value: string,
    category?: string,
    description?: string,
  ): Promise<boolean> => {
    try {
      const res = await fetch('/api/config/secrets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, value, category, description }),
      })
      if (res.ok) {
        await fetchSecrets()
        return true
      }
    } catch (e) {
      console.error('Failed to save secret:', e)
    }
    return false
  }, [fetchSecrets])

  const deleteSecret = useCallback(async (name: string): Promise<boolean> => {
    try {
      const res = await fetch(`/api/config/secrets/${encodeURIComponent(name)}`, {
        method: 'DELETE',
      })
      if (res.ok) {
        setSecrets(prev => prev.filter(s => s.name !== name))
        return true
      }
    } catch (e) {
      console.error('Failed to delete secret:', e)
    }
    return false
  }, [])

  // =========================================================================
  // Prompts
  // =========================================================================

  const fetchPrompts = useCallback(async () => {
    try {
      const res = await fetch('/api/config/prompts')
      if (res.ok) {
        const data = await res.json()
        setPrompts(data.prompts || [])
        setPromptCategories(data.categories || {})
      }
    } catch (e) {
      console.error('Failed to fetch prompts:', e)
    }
  }, [])

  const getPromptDetail = useCallback(async (path: string): Promise<PromptDetail | null> => {
    try {
      const res = await fetch(`/api/config/prompts/${encodeURIComponent(path)}`)
      if (res.ok) return await res.json()
    } catch (e) {
      console.error('Failed to get prompt detail:', e)
    }
    return null
  }, [])

  const savePromptOverride = useCallback(async (path: string, content: string): Promise<boolean> => {
    try {
      const res = await fetch(`/api/config/prompts/${encodeURIComponent(path)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content }),
      })
      if (res.ok) {
        await fetchPrompts()
        return true
      }
    } catch (e) {
      console.error('Failed to save prompt override:', e)
    }
    return false
  }, [fetchPrompts])

  const deletePromptOverride = useCallback(async (path: string): Promise<boolean> => {
    try {
      const res = await fetch(`/api/config/prompts/${encodeURIComponent(path)}`, {
        method: 'DELETE',
      })
      if (res.ok) {
        await fetchPrompts()
        return true
      }
    } catch (e) {
      console.error('Failed to delete prompt override:', e)
    }
    return false
  }, [fetchPrompts])

  // =========================================================================
  // Export / Import
  // =========================================================================

  const exportConfig = useCallback(async (): Promise<ConfigExportBundle | null> => {
    try {
      const res = await fetch('/api/config/export', { method: 'POST' })
      if (res.ok) return await res.json()
    } catch (e) {
      console.error('Failed to export config:', e)
    }
    return null
  }, [])

  const importConfig = useCallback(async (bundle: { config?: Record<string, unknown>; prompts?: Record<string, string> }): Promise<{ success: boolean; summary: string }> => {
    try {
      const res = await fetch('/api/config/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(bundle),
      })
      const data = await res.json()
      return { success: res.ok, summary: data.summary || data.detail || 'Unknown result' }
    } catch (e) {
      return { success: false, summary: String(e) }
    }
  }, [])

  return {
    // Schema + Config
    schema,
    configValues,
    isLoading,
    fetchConfig,
    saveConfig,
    validateConfig,
    resetToDefaults,

    // Raw YAML
    yamlContent,
    fetchYaml,
    saveYaml,

    // Secrets
    secrets,
    secretCategories,
    fetchSecrets,
    saveSecret,
    deleteSecret,

    // Prompts
    prompts,
    promptCategories,
    fetchPrompts,
    getPromptDetail,
    savePromptOverride,
    deletePromptOverride,

    // Export/Import
    exportConfig,
    importConfig,
  }
}
