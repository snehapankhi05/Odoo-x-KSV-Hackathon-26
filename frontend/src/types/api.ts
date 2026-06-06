// ── API Response Types ───────────────────────────────────────────────

export interface ApiResponse<T = unknown> {
  data: T
  message?: string
  success: boolean
}

export interface PaginatedResponse<T> {
  data: T[]
  total: number
  skip: number
  limit: number
  has_more: boolean
}

export interface ApiError {
  message: string
  detail?: string | Record<string, string[]>
  status_code?: number
}

export interface SelectOption<T = string> {
  label: string
  value: T
  disabled?: boolean
}

export type SortDirection = 'asc' | 'desc'

export interface SortConfig {
  field: string
  direction: SortDirection
}

export interface FilterConfig {
  search?: string
  skip?: number
  limit?: number
  [key: string]: unknown
}
