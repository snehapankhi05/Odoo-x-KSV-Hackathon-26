import { useLocation, Link } from 'react-router-dom'
import { ChevronRight, Home } from 'lucide-react'
import { cn } from '@/utils/cn'
import { capitalize } from '@/utils/format'

function slugToLabel(slug: string): string {
  return slug
    .split('-')
    .map(capitalize)
    .join(' ')
}

interface BreadcrumbsProps {
  className?: string
}

export function Breadcrumbs({ className }: BreadcrumbsProps) {
  const { pathname } = useLocation()
  const segments = pathname.split('/').filter(Boolean)

  if (segments.length === 0) return null

  return (
    <nav aria-label="Breadcrumb" className={cn('flex items-center gap-1.5 text-sm', className)}>
      <Link
        to="/dashboard"
        className="flex items-center text-muted-foreground hover:text-foreground transition-colors"
      >
        <Home className="h-3.5 w-3.5" />
      </Link>

      {segments.map((segment, index) => {
        const href = '/' + segments.slice(0, index + 1).join('/')
        const isLast = index === segments.length - 1
        const isId = /^[0-9a-f-]{36}$/i.test(segment) || /^\d+$/.test(segment)

        return (
          <span key={href} className="flex items-center gap-1.5">
            <ChevronRight className="h-3.5 w-3.5 text-muted-foreground/50" />
            {isLast ? (
              <span className="font-medium text-foreground">
                {isId ? 'Detail' : slugToLabel(segment)}
              </span>
            ) : (
              <Link
                to={href}
                className="text-muted-foreground hover:text-foreground transition-colors"
              >
                {isId ? 'Detail' : slugToLabel(segment)}
              </Link>
            )}
          </span>
        )
      })}
    </nav>
  )
}
