import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { Compass, ArrowLeft, Home } from 'lucide-react'
import { Button } from '@/components/ui/Button'

export function NotFoundPage() {
  const navigate = useNavigate()
  return (
    <div className="min-h-screen flex items-center justify-center bg-background px-6">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="flex flex-col items-center text-center space-y-5 max-w-sm"
      >
        {/* Animated icon */}
        <motion.div
          animate={{ rotate: [0, -10, 10, -10, 0] }}
          transition={{ delay: 0.4, duration: 0.6 }}
          className="flex h-20 w-20 items-center justify-center rounded-3xl bg-accent"
        >
          <Compass className="h-9 w-9 text-primary" />
        </motion.div>

        <div className="space-y-2">
          <h1 className="text-6xl font-black text-foreground tracking-tight">404</h1>
          <h2 className="text-xl font-semibold text-foreground">Page Not Found</h2>
          <p className="text-muted-foreground text-sm">
            The page you're looking for doesn't exist or has been moved.
          </p>
        </div>

        <div className="flex gap-3">
          <Button
            onClick={() => navigate(-1)}
            variant="outline"
            leftIcon={<ArrowLeft className="h-4 w-4" />}
          >
            Go Back
          </Button>
          <Button
            onClick={() => navigate('/dashboard')}
            leftIcon={<Home className="h-4 w-4" />}
          >
            Dashboard
          </Button>
        </div>
      </motion.div>
    </div>
  )
}
