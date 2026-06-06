// ── Auth & User Types ────────────────────────────────────────────────

export type UserRole = 'admin' | 'officer' | 'manager' | 'vendor'

export interface User {
  user_id: string
  first_name: string
  last_name: string
  email: string
  phone_number: string
  role: UserRole
  is_active: boolean
  created_at: string
  updated_at?: string
}

export interface LoginRequest {
  email: string
  password: string
}

export interface LoginResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
}

export interface AuthState {
  user: User | null
  accessToken: string | null
  refreshToken: string | null
  isAuthenticated: boolean
  isLoading: boolean
}

export interface AuthContextType extends AuthState {
  login: (credentials: LoginRequest) => Promise<void>
  logout: () => void
  refreshAccessToken: () => Promise<string | null>
  hasRole: (role: UserRole | UserRole[]) => boolean
}
