import { cn } from '@/utils/cn'
import { getInitials } from '@/utils/format'

type AvatarSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl'

const sizeMap: Record<AvatarSize, string> = {
  xs: 'h-6 w-6 text-[10px]',
  sm: 'h-8 w-8 text-xs',
  md: 'h-9 w-9 text-sm',
  lg: 'h-11 w-11 text-base',
  xl: 'h-14 w-14 text-lg',
}

const colorPalette = [
  'bg-blue-500',
  'bg-violet-500',
  'bg-emerald-500',
  'bg-amber-500',
  'bg-rose-500',
  'bg-indigo-500',
  'bg-teal-500',
  'bg-orange-500',
]

function getColorFromName(name: string): string {
  const index = name.charCodeAt(0) % colorPalette.length
  return colorPalette[index]
}

interface AvatarProps {
  src?: string | null
  firstName?: string
  lastName?: string
  size?: AvatarSize
  className?: string
}

export function Avatar({
  src,
  firstName = '',
  lastName = '',
  size = 'md',
  className,
}: AvatarProps) {
  const initials = getInitials(firstName || '?', lastName || '')
  const color = getColorFromName(firstName || 'A')

  if (src) {
    return (
      <img
        src={src}
        alt={`${firstName} ${lastName}`}
        className={cn(
          'rounded-full object-cover ring-2 ring-border',
          sizeMap[size],
          className
        )}
      />
    )
  }

  return (
    <div
      className={cn(
        'flex items-center justify-center rounded-full font-semibold text-white select-none shrink-0',
        sizeMap[size],
        color,
        className
      )}
      aria-label={`${firstName} ${lastName}`}
    >
      {initials}
    </div>
  )
}
