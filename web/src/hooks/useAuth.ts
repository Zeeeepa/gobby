import { useState, useEffect, useCallback } from 'react'

const BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

interface AuthState {
  authRequired: boolean
  authenticated: boolean
  loading: boolean
}

export function useAuth() {
  const [state, setState] = useState<AuthState>({
    authRequired: false,
    authenticated: true, // optimistic default — no flash
    loading: true,
  })

  const checkStatus = useCallback(async () => {
    try {
      const res = await fetch(`${BASE_URL}/api/auth/status`, { credentials: 'include' })
      if (!res.ok) {
        setState({ authRequired: false, authenticated: true, loading: false })
        return
      }
      const data = await res.json()
      setState({
        authRequired: data.auth_required ?? false,
        authenticated: data.authenticated ?? true,
        loading: false,
      })
    } catch {
      // If status endpoint fails, assume no auth required
      setState({ authRequired: false, authenticated: true, loading: false })
    }
  }, [])

  useEffect(() => {
    checkStatus()
  }, [checkStatus])

  const login = useCallback(async (username: string, password: string, rememberMe: boolean): Promise<string | null> => {
    try {
      const res = await fetch(`${BASE_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ username, password, remember_me: rememberMe }),
      })
      const data = await res.json()
      if (res.ok && data.ok) {
        setState(prev => ({ ...prev, authenticated: true }))
        return null
      }
      return data.error || 'Login failed'
    } catch {
      return 'Network error — is the daemon running?'
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await fetch(`${BASE_URL}/api/auth/logout`, {
        method: 'POST',
        credentials: 'include',
      })
    } catch {
      // Best-effort
    }
    setState(prev => ({ ...prev, authenticated: false }))
  }, [])

  return { ...state, login, logout }
}
