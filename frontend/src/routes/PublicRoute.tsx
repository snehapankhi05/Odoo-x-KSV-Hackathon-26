import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { PageSpinner } from '@/components/ui/Spinner'

/** Public-only route. Redirects already-authenticated users to /dashboard. */
export function PublicRoute() {
  const { isAuthenticated, isLoading } = useAuth()

  if (isLoading) return <PageSpinner />

  if (isAuthenticated) {
    return <Navigate to="/dashboard" replace />
  }

  return <Outlet />
}
