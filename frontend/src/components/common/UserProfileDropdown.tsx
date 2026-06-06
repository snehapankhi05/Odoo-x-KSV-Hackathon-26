import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { LogOut, UserCircle, Settings, ChevronDown } from 'lucide-react'
import { motion, AnimatePresence } from 'framer-motion'
import { useAuth } from '@/hooks/useAuth'
import { Avatar } from '@/components/ui/Avatar'
import { Badge } from '@/components/ui/Badge'
import { cn } from '@/utils/cn'
import { capitalize } from '@/utils/format'

const roleVariantMap: Record<string, 'info' | 'success' | 'warning' | 'primary'> = {
  admin:   'danger' as never,
  officer: 'info',
  manager: 'warning',
  vendor:  'success',
}

export function UserProfileDropdown() {
  const { user, logout } = useAuth()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  if (!user) return null

  const handleLogout = () => {
    setOpen(false)
    logout()
    navigate('/login')
  }

  return (
    <div ref={ref} className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-2 rounded-xl px-2 py-1.5 hover:bg-accent transition-colors"
        aria-haspopup="menu"
        aria-expanded={open}
      >
        <Avatar firstName={user.first_name} lastName={user.last_name} size="sm" />
        <span className="hidden md:flex flex-col items-start">
          <span className="text-sm font-medium leading-tight text-foreground">
            {user.first_name} {user.last_name}
          </span>
          <span className="text-xs text-muted-foreground">{capitalize(user.role)}</span>
        </span>
        <ChevronDown
          className={cn('h-3.5 w-3.5 text-muted-foreground transition-transform duration-200 hidden md:block', open && 'rotate-180')}
        />
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -8, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.95 }}
            transition={{ duration: 0.15, ease: 'easeOut' }}
            className="absolute right-0 top-full mt-2 w-56 rounded-2xl border border-border bg-popover shadow-glass p-1 z-50"
            role="menu"
          >
            {/* User info header */}
            <div className="px-3 py-2.5 border-b border-border mb-1">
              <p className="text-sm font-semibold text-foreground">{user.first_name} {user.last_name}</p>
              <p className="text-xs text-muted-foreground truncate">{user.email}</p>
              <Badge variant={roleVariantMap[user.role] ?? 'default'} className="mt-1.5 text-[10px]">
                {capitalize(user.role)}
              </Badge>
            </div>

            {/* Menu items */}
            {[
              { label: 'My Profile', icon: UserCircle, href: '/profile' },
              { label: 'Settings', icon: Settings, href: '/settings' },
            ].map(({ label, icon: Icon, href }) => (
              <button
                key={href}
                role="menuitem"
                onClick={() => { setOpen(false); navigate(href) }}
                className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm text-foreground hover:bg-accent transition-colors"
              >
                <Icon className="h-4 w-4 text-muted-foreground" />
                {label}
              </button>
            ))}

            <div className="border-t border-border mt-1 pt-1">
              <button
                role="menuitem"
                onClick={handleLogout}
                className="flex w-full items-center gap-2.5 rounded-xl px-3 py-2 text-sm text-destructive hover:bg-destructive/10 transition-colors"
              >
                <LogOut className="h-4 w-4" />
                Log Out
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
