import { cn } from '@/utils/cn'

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg' | 'xl'
  className?: string
  label?: string
}

const sizeMap = {
  sm: 'h-4 w-4 border-2',
  md: 'h-6 w-6 border-2',
  lg: 'h-8 w-8 border-3',
  xl: 'h-12 w-12 border-4',
}

export function Spinner({ size = 'md', className, label = 'Loading...' }: SpinnerProps) {
  return (
    <div role="status" aria-label={label} className={cn('inline-flex', className)}>
      <div
        className={cn(
          'rounded-full border-border border-t-primary animate-spin',
          sizeMap[size]
        )}
      />
      <span className="sr-only">{label}</span>
    </div>
  )
}

export function PageSpinner() {
  return (
    <div className="flex h-full min-h-64 items-center justify-center">
      <Spinner size="lg" />
    </div>
  )
}
