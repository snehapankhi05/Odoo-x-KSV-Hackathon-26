import { Bell } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { cn } from '@/utils/cn'

interface NotificationBellProps {
  unreadCount?: number
  className?: string
}

export function NotificationBell({ unreadCount = 0, className }: NotificationBellProps) {
  const navigate = useNavigate()

  return (
    <button
      onClick={() => navigate('/notifications')}
      aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ''}`}
      className={cn(
        'relative flex h-9 w-9 items-center justify-center rounded-xl',
        'text-muted-foreground hover:text-foreground hover:bg-accent',
        'transition-colors duration-200',
        className
      )}
    >
      <Bell className="h-4.5 w-4.5" />
      {unreadCount > 0 && (
        <span
          className={cn(
            'absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center',
            'rounded-full bg-destructive text-destructive-foreground',
            'text-[10px] font-bold leading-none px-1'
          )}
        >
          {unreadCount > 99 ? '99+' : unreadCount}
        </span>
      )}
    </button>
  )
}
