import { cva, type VariantProps } from 'class-variance-authority'
import { cn } from '@/utils/cn'

const badgeVariants = cva(
  'inline-flex items-center gap-1 rounded-full font-medium text-xs px-2.5 py-0.5 transition-colors',
  {
    variants: {
      variant: {
        default:    'bg-secondary text-secondary-foreground',
        primary:    'bg-accent text-accent-foreground',
        success:    'bg-success/15 text-success dark:bg-success/20',
        warning:    'bg-warning/15 text-warning dark:bg-warning/20',
        danger:     'bg-destructive/15 text-destructive dark:bg-destructive/20',
        info:       'bg-primary/10 text-primary',
        outline:    'border border-border text-foreground bg-transparent',
      },
    },
    defaultVariants: {
      variant: 'default',
    },
  }
)

export interface BadgeProps
  extends React.HTMLAttributes<HTMLSpanElement>,
    VariantProps<typeof badgeVariants> {
  dot?: boolean
}

export function Badge({ className, variant, dot, children, ...props }: BadgeProps) {
  return (
    <span className={cn(badgeVariants({ variant }), className)} {...props}>
      {dot && (
        <span
          className={cn(
            'h-1.5 w-1.5 rounded-full',
            variant === 'success' && 'bg-success',
            variant === 'warning' && 'bg-warning',
            variant === 'danger'  && 'bg-destructive',
            variant === 'info'    && 'bg-primary',
            variant === 'primary' && 'bg-accent-foreground',
            (!variant || variant === 'default') && 'bg-muted-foreground',
          )}
        />
      )}
      {children}
    </span>
  )
}

export { badgeVariants }
