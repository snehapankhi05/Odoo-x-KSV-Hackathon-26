import { useState } from 'react'
import { NavLink, useLocation } from 'react-router-dom'
import { motion, AnimatePresence } from 'framer-motion'
import { PanelLeftClose, PanelLeftOpen, Boxes } from 'lucide-react'
import { navigationItems, bottomNavItems } from '@/config/navigation'
import { useAuth } from '@/hooks/useAuth'
import { storage, STORAGE_KEYS } from '@/utils/storage'
import { cn } from '@/utils/cn'
import type { NavItem } from '@/types/navigation'
import type { UserRole } from '@/types/auth'

const SIDEBAR_W_EXPANDED  = 240
const SIDEBAR_W_COLLAPSED = 64

function filterNavItems(items: NavItem[], role: UserRole): NavItem[] {
  return items.filter((item) => !item.roles || item.roles.includes(role))
}

interface SidebarLinkProps {
  item: NavItem
  collapsed: boolean
}

function SidebarLink({ item, collapsed }: SidebarLinkProps) {
  const Icon = item.icon
  return (
    <NavLink
      to={item.href}
      className={({ isActive }) =>
        cn(
          'group flex items-center gap-3 rounded-xl px-3 py-2.5 text-sm font-medium',
          'transition-all duration-150 relative',
          isActive
            ? 'bg-sidebar-accent text-sidebar-accent-foreground'
            : 'text-sidebar-foreground hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground'
        )
      }
    >
      {({ isActive }) => (
        <>
          {isActive && (
            <motion.span
              layoutId="sidebar-indicator"
              className="absolute inset-0 rounded-xl bg-sidebar-accent"
              transition={{ duration: 0.2 }}
            />
          )}
          <Icon
            className={cn(
              'relative z-10 h-4.5 w-4.5 shrink-0 transition-colors',
              isActive ? 'text-sidebar-accent-foreground' : 'text-sidebar-foreground/60 group-hover:text-sidebar-accent-foreground'
            )}
          />
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.2 }}
                className="relative z-10 overflow-hidden whitespace-nowrap"
              >
                {item.label}
              </motion.span>
            )}
          </AnimatePresence>
          {item.badge && !collapsed && (
            <span className="relative z-10 ml-auto rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-bold text-primary-foreground">
              {item.badge}
            </span>
          )}
        </>
      )}
    </NavLink>
  )
}

interface SidebarProps {
  className?: string
}

export function Sidebar({ className }: SidebarProps) {
  const { user } = useAuth()
  const [collapsed, setCollapsed] = useState<boolean>(
    () => storage.get<boolean>(STORAGE_KEYS.SIDEBAR_COLLAPSED) ?? false
  )

  const toggleCollapse = () => {
    const next = !collapsed
    setCollapsed(next)
    storage.set(STORAGE_KEYS.SIDEBAR_COLLAPSED, next)
  }

  const role = user?.role ?? 'vendor'
  const mainItems = filterNavItems(navigationItems, role)
  const footerItems = filterNavItems(bottomNavItems, role)

  return (
    <motion.aside
      animate={{ width: collapsed ? SIDEBAR_W_COLLAPSED : SIDEBAR_W_EXPANDED }}
      transition={{ duration: 0.25, ease: 'easeInOut' }}
      className={cn(
        'glass-sidebar flex h-screen flex-col overflow-hidden shrink-0',
        className
      )}
    >
      {/* Logo */}
      <div className="flex h-14 items-center px-3 border-b border-sidebar-border">
        <NavLink to="/dashboard" className="flex items-center gap-2.5 min-w-0">
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg gradient-primary">
            <Boxes className="h-4.5 w-4.5 text-white" />
          </div>
          <AnimatePresence initial={false}>
            {!collapsed && (
              <motion.span
                initial={{ opacity: 0, width: 0 }}
                animate={{ opacity: 1, width: 'auto' }}
                exit={{ opacity: 0, width: 0 }}
                transition={{ duration: 0.2 }}
                className="overflow-hidden whitespace-nowrap font-bold text-foreground text-base"
              >
                VendorBridge
              </motion.span>
            )}
          </AnimatePresence>
        </NavLink>
      </div>

      {/* Main Navigation */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden p-2 space-y-0.5" aria-label="Main navigation">
        {mainItems.map((item) => (
          <SidebarLink key={item.href} item={item} collapsed={collapsed} />
        ))}
      </nav>

      {/* Footer Nav */}
      <div className="p-2 border-t border-sidebar-border space-y-0.5">
        {footerItems.map((item) => (
          <SidebarLink key={item.href} item={item} collapsed={collapsed} />
        ))}

        {/* Collapse Toggle */}
        <button
          onClick={toggleCollapse}
          aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          className={cn(
            'flex w-full items-center gap-3 rounded-xl px-3 py-2.5',
            'text-sm font-medium text-sidebar-foreground/60',
            'hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground transition-colors'
          )}
        >
          {collapsed ? (
            <PanelLeftOpen className="h-4.5 w-4.5 shrink-0" />
          ) : (
            <>
              <PanelLeftClose className="h-4.5 w-4.5 shrink-0" />
              <AnimatePresence initial={false}>
                <motion.span
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  exit={{ opacity: 0 }}
                  className="whitespace-nowrap"
                >
                  Collapse
                </motion.span>
              </AnimatePresence>
            </>
          )}
        </button>
      </div>
    </motion.aside>
  )
}
