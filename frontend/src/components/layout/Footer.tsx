import { Boxes } from 'lucide-react'

export function Footer() {
  const year = new Date().getFullYear()
  return (
    <footer className="border-t border-border/50 px-6 py-4 mt-6">
      <div className="mx-auto max-w-7xl flex flex-col sm:flex-row items-center justify-between gap-2">
        <div className="flex items-center gap-2 text-muted-foreground">
          <Boxes className="h-4 w-4" />
          <span className="text-sm font-medium">VendorBridge</span>
        </div>
        <p className="text-xs text-muted-foreground">
          © {year} VendorBridge Procurement ERP. All rights reserved.
        </p>
      </div>
    </footer>
  )
}
