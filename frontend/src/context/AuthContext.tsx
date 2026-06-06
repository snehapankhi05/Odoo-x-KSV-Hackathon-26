import React, { createContext, useCallback, useEffect, useState } from 'react'
import type { AuthContextType, AuthState, LoginRequest, User, UserRole } from '@/types/auth'
import { authService } from '@/services/auth.service'
import { storage, STORAGE_KEYS } from '@/utils/storage'

// ── Context ───────────────────────────────────────────────────────────
export const AuthContext = createContext<AuthContextType | null>(null)

// ── Initial State ─────────────────────────────────────────────────────
function getInitialState(): AuthState {
  return {
    user: storage.get<User>(STORAGE_KEYS.USER),
    accessToken: storage.get<string>(STORAGE_KEYS.ACCESS_TOKEN),
    refreshToken: storage.get<string>(STORAGE_KEYS.REFRESH_TOKEN),
    isAuthenticated: !!storage.get<string>(STORAGE_KEYS.ACCESS_TOKEN),
    isLoading: false,
  }
}

// ── Provider ──────────────────────────────────────────────────────────
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [state, setState] = useState<AuthState>(getInitialState)

  // Persist auth state changes to localStorage
  useEffect(() => {
    if (state.accessToken) {
      storage.set(STORAGE_KEYS.ACCESS_TOKEN, state.accessToken)
    } else {
      storage.remove(STORAGE_KEYS.ACCESS_TOKEN)
    }

    if (state.refreshToken) {
      storage.set(STORAGE_KEYS.REFRESH_TOKEN, state.refreshToken)
    } else {
      storage.remove(STORAGE_KEYS.REFRESH_TOKEN)
    }

    if (state.user) {
      storage.set(STORAGE_KEYS.USER, state.user)
    } else {
      storage.remove(STORAGE_KEYS.USER)
    }
  }, [state.accessToken, state.refreshToken, state.user])

  // ── login ──────────────────────────────────────────────────────────
  const login = useCallback(async (credentials: LoginRequest) => {
    setState((prev) => ({ ...prev, isLoading: true }))
    try {
      const response = await authService.login(credentials)
      setState({
        user: response.user,
        accessToken: response.access_token,
        refreshToken: response.refresh_token,
        isAuthenticated: true,
        isLoading: false,
      })
    } catch (err) {
      setState((prev) => ({ ...prev, isLoading: false }))
      throw err
    }
  }, [])

  // ── logout ─────────────────────────────────────────────────────────
  const logout = useCallback(() => {
    authService.logout().catch(() => {})
    setState({
      user: null,
      accessToken: null,
      refreshToken: null,
      isAuthenticated: false,
      isLoading: false,
    })
  }, [])

  // ── refreshAccessToken ─────────────────────────────────────────────
  const refreshAccessToken = useCallback(async (): Promise<string | null> => {
    const rt = state.refreshToken
    if (!rt) return null
    try {
      const { access_token } = await authService.refresh(rt)
      setState((prev) => ({ ...prev, accessToken: access_token }))
      return access_token
    } catch {
      logout()
      return null
    }
  }, [state.refreshToken, logout])

  // ── hasRole ────────────────────────────────────────────────────────
  const hasRole = useCallback(
    (role: UserRole | UserRole[]): boolean => {
      if (!state.user) return false
      const roles = Array.isArray(role) ? role : [role]
      return roles.includes(state.user.role)
    },
    [state.user]
  )

  return (
    <AuthContext.Provider value={{ ...state, login, logout, refreshAccessToken, hasRole }}>
      {children}
    </AuthContext.Provider>
  )
}
