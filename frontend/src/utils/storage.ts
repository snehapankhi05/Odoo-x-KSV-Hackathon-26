/** Typed localStorage wrapper */

export const storage = {
  get<T>(key: string): T | null {
    try {
      const raw = localStorage.getItem(key)
      if (raw === null) return null
      return JSON.parse(raw) as T
    } catch {
      return null
    }
  },

  set<T>(key: string, value: T): void {
    try {
      localStorage.setItem(key, JSON.stringify(value))
    } catch {
      // ignore quota errors silently
    }
  },

  remove(key: string): void {
    localStorage.removeItem(key)
  },

  clear(): void {
    localStorage.clear()
  },
}

// ── Storage Keys ──────────────────────────────────────────────────────
export const STORAGE_KEYS = {
  ACCESS_TOKEN: 'vb_access_token',
  REFRESH_TOKEN: 'vb_refresh_token',
  USER: 'vb_user',
  THEME: 'vb_theme',
  SIDEBAR_COLLAPSED: 'vb_sidebar_collapsed',
} as const
