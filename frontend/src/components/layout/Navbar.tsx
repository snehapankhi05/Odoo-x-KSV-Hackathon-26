import { useScrollPosition } from '@/hooks/useCommon'
import { SearchBar } from '@/components/common/SearchBar'
import { ThemeToggle } from '@/components/common/ThemeToggle'
import { NotificationBell } from '@/components/common/NotificationBell'
import { UserProfileDropdown } from '@/components/common/UserProfileDropdown'
import { cn } from '@/utils/cn'

interface NavbarProps {
  onSearch?: (value: string) => void
  notificationCount?: number
}

export function Navbar({ onSearch, notificationCount = 0 }: NavbarProps) {
  const scrollY = useScrollPosition()
  const elevated = scrollY > 0

  return (
    <header
      className={cn(
        'sticky top-0 z-40 flex h-14 items-center gap-4 px-4 md:px-6',
        'bg-background/80 backdrop-blur-xl border-b border-border/60',
        'transition-shadow duration-200',
        elevated && 'shadow-sm'
      )}
    >
      {/* Search */}
      <div className="flex-1 max-w-xs">
        <SearchBar
          placeholder="Search anything…"
          onSearch={onSearch ?? (() => {})}
          className="w-full"
        />
      </div>

      {/* Right controls */}
      <div className="ml-auto flex items-center gap-1">
        <ThemeToggle />
        <NotificationBell unreadCount={notificationCount} />
        <div className="ml-1">
          <UserProfileDropdown />
        </div>
      </div>
    </header>
  )
}
