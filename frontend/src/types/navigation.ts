import type { LucideIcon } from 'lucide-react'
import type { UserRole } from './auth'

export interface NavItem {
  label: string
  href: string
  icon: LucideIcon
  badge?: string | number
  roles?: UserRole[]
  children?: NavItem[]
}

export interface SidebarSection {
  title?: string
  items: NavItem[]
}
