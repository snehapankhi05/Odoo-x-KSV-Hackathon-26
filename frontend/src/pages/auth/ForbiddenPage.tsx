import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { ShieldOff, ArrowLeft } from 'lucide-react'
import { Button } from '@/components/ui/Button'

export function ForbiddenPage() {
  const navigate = useNavigate()
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-6">
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 0.3 }}
        className="flex flex-col items-center text-center space-y-5 max-w-sm"
      >
        <div className="flex h-20 w-20 items-center justify-center rounded-3xl bg-destructive/10">
          <ShieldOff className="h-9 w-9 text-destructive" />
        </div>
        <div className="space-y-2">
          <h1 className="text-6xl font-black text-foreground tracking-tight">403</h1>
          <h2 className="text-xl font-semibold text-foreground">Access Denied</h2>
          <p className="text-muted-foreground text-sm">
            You don't have permission to view this page.
            Please contact your administrator if you believe this is an error.
          </p>
        </div>
        <Button
          onClick={() => navigate(-1)}
          variant="outline"
          leftIcon={<ArrowLeft className="h-4 w-4" />}
        >
          Go Back
        </Button>
      </motion.div>
    </div>
  )
}
