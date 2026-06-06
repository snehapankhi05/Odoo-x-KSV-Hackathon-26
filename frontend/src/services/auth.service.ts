import api from './axios'
import type { LoginRequest, LoginResponse, User } from '@/types/auth'

export const authService = {
  /** POST /auth/login */
  async login(credentials: LoginRequest): Promise<LoginResponse> {
    const { data } = await api.post<LoginResponse>('/auth/login', credentials)
    return data
  },

  /** POST /auth/refresh */
  async refresh(refreshToken: string): Promise<{ access_token: string; token_type: string }> {
    const { data } = await api.post('/auth/refresh', { refresh_token: refreshToken })
    return data
  },

  /** GET /auth/me — fetch current user profile */
  async getMe(): Promise<User> {
    const { data } = await api.get<User>('/auth/me')
    return data
  },

  /** POST /auth/logout */
  async logout(): Promise<void> {
    try {
      await api.post('/auth/logout')
    } catch {
      // Ignore logout errors; we clear tokens client-side regardless
    }
  },
}

export default authService
