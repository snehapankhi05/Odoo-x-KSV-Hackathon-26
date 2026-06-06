import { useAuth } from '@/hooks/useAuth'
import { capitalize } from '@/utils/format'

/**
 * Dashboard placeholder — Phase 2 will populate this with widgets and charts.
 */
export function DashboardPage() {
  const { user } = useAuth()

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-foreground">
          Welcome back, {user?.first_name} 👋
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">
          You're signed in as{' '}
          <span className="font-medium text-foreground">{capitalize(user?.role ?? '')}</span>.
          Dashboard content is coming in Phase 2.
        </p>
      </div>

      {/* Phase 2 placeholder grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div
            key={i}
            className="rounded-2xl border border-dashed border-border bg-muted/30 p-6 flex flex-col items-center justify-center gap-2 min-h-[120px]"
          >
            <span className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
              KPI Widget {i + 1}
            </span>
            <span className="text-xs text-muted-foreground/60">Phase 2</span>
          </div>
        ))}
      </div>
    </div>
  )
}
