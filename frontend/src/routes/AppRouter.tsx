import { Routes, Route, Navigate } from 'react-router-dom'
import { AnimatePresence } from 'framer-motion'

// Route Guards
import { ProtectedRoute } from './ProtectedRoute'
import { PublicRoute } from './PublicRoute'

// Layout
import { AppLayout } from '@/components/layout/AppLayout'

// Pages
import { LoginPage }     from '@/pages/auth/LoginPage'
import { ForbiddenPage } from '@/pages/auth/ForbiddenPage'
import { NotFoundPage }  from '@/pages/auth/NotFoundPage'
import { DashboardPage } from '@/pages/dashboard/DashboardPage'

export function AppRouter() {
  return (
    <AnimatePresence mode="wait">
      <Routes>
        {/* ── Public routes (redirect to dashboard if logged in) ── */}
        <Route element={<PublicRoute />}>
          <Route path="/login" element={<LoginPage />} />
        </Route>

        {/* ── Error pages (public) ── */}
        <Route path="/403" element={<ForbiddenPage />} />
        <Route path="/404" element={<NotFoundPage />} />

        {/* ── Protected routes (require auth) ── */}
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            <Route index element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<DashboardPage />} />

            {/* ── Phase 2+ routes (placeholders) ── */}
            <Route path="/rfqs/*"             element={<PlaceholderPage title="RFQ Management" />} />
            <Route path="/vendor/rfqs/*"      element={<PlaceholderPage title="My RFQs" />} />
            <Route path="/quotations/*"       element={<PlaceholderPage title="Quotations" />} />
            <Route path="/vendor/quotations/*" element={<PlaceholderPage title="My Quotations" />} />
            <Route path="/approvals/*"        element={<PlaceholderPage title="Approvals" />} />
            <Route path="/purchase-orders/*"  element={<PlaceholderPage title="Purchase Orders" />} />
            <Route path="/vendor/purchase-orders/*" element={<PlaceholderPage title="My Orders" />} />
            <Route path="/invoices/*"         element={<PlaceholderPage title="Invoices" />} />
            <Route path="/vendor/invoices/*"  element={<PlaceholderPage title="My Invoices" />} />
            <Route path="/vendors/*"          element={<PlaceholderPage title="Vendors" />} />
            <Route path="/users/*"            element={<PlaceholderPage title="User Management" />} />
            <Route path="/reports/*"          element={<PlaceholderPage title="Reports & Analytics" />} />
            <Route path="/notifications"      element={<PlaceholderPage title="Notifications" />} />
            <Route path="/activity-logs"      element={<PlaceholderPage title="Activity Logs" />} />
            <Route path="/profile"            element={<PlaceholderPage title="My Profile" />} />
            <Route path="/settings"           element={<PlaceholderPage title="Settings" />} />
          </Route>
        </Route>

        {/* ── Catch-all 404 ── */}
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </AnimatePresence>
  )
}

// ── Phase 2 Placeholder ────────────────────────────────────────────────
function PlaceholderPage({ title }: { title: string }) {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold text-foreground">{title}</h1>
      <div className="rounded-2xl border border-dashed border-border bg-muted/30 p-12 flex flex-col items-center justify-center gap-2">
        <p className="text-sm font-medium text-muted-foreground">Coming in Phase 2</p>
        <p className="text-xs text-muted-foreground/60">{title} page will be implemented here</p>
      </div>
    </div>
  )
}
