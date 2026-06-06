import {
  LayoutDashboard,
  FileText,
  ShoppingCart,
  Users,
  Building2,
  CheckSquare,
  Package,
  Receipt,
  BarChart3,
  Bell,
  Activity,
  Settings,
  UserCircle,
} from 'lucide-react'
import type { NavItem } from '@/types/navigation'

// ── All navigation items with role filters ────────────────────────────
export const navigationItems: NavItem[] = [
  {
    label: 'Dashboard',
    href: '/dashboard',
    icon: LayoutDashboard,
    // All roles
  },
  {
    label: 'RFQ Management',
    href: '/rfqs',
    icon: FileText,
    roles: ['admin', 'officer', 'manager'],
  },
  {
    label: 'My RFQs',
    href: '/vendor/rfqs',
    icon: FileText,
    roles: ['vendor'],
  },
  {
    label: 'Quotations',
    href: '/quotations',
    icon: ShoppingCart,
    roles: ['admin', 'officer', 'manager'],
  },
  {
    label: 'My Quotations',
    href: '/vendor/quotations',
    icon: ShoppingCart,
    roles: ['vendor'],
  },
  {
    label: 'Approvals',
    href: '/approvals',
    icon: CheckSquare,
    roles: ['admin', 'manager'],
  },
  {
    label: 'Purchase Orders',
    href: '/purchase-orders',
    icon: Package,
    roles: ['admin', 'officer', 'manager'],
  },
  {
    label: 'My Orders',
    href: '/vendor/purchase-orders',
    icon: Package,
    roles: ['vendor'],
  },
  {
    label: 'Invoices',
    href: '/invoices',
    icon: Receipt,
    roles: ['admin', 'officer', 'manager'],
  },
  {
    label: 'My Invoices',
    href: '/vendor/invoices',
    icon: Receipt,
    roles: ['vendor'],
  },
  {
    label: 'Vendors',
    href: '/vendors',
    icon: Building2,
    roles: ['admin', 'officer', 'manager'],
  },
  {
    label: 'Users',
    href: '/users',
    icon: Users,
    roles: ['admin'],
  },
  {
    label: 'Reports',
    href: '/reports',
    icon: BarChart3,
    roles: ['admin', 'officer', 'manager'],
  },
  {
    label: 'Notifications',
    href: '/notifications',
    icon: Bell,
  },
  {
    label: 'Activity Logs',
    href: '/activity-logs',
    icon: Activity,
    roles: ['admin'],
  },
]

// ── Bottom nav items (shown at sidebar bottom) ────────────────────────
export const bottomNavItems: NavItem[] = [
  {
    label: 'Profile',
    href: '/profile',
    icon: UserCircle,
  },
  {
    label: 'Settings',
    href: '/settings',
    icon: Settings,
    roles: ['admin'],
  },
]
