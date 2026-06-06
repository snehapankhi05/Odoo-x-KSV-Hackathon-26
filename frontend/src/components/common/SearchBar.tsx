import { useState } from 'react'
import { Search, X } from 'lucide-react'
import { cn } from '@/utils/cn'
import { useDebounce } from '@/hooks/useCommon'

interface SearchBarProps {
  placeholder?: string
  onSearch: (value: string) => void
  className?: string
  debounceMs?: number
}

export function SearchBar({
  placeholder = 'Search…',
  onSearch,
  className,
  debounceMs = 300,
}: SearchBarProps) {
  const [value, setValue] = useState('')
  const debouncedValue = useDebounce(value, debounceMs)

  // Trigger search when debounced value changes
  useState(() => {
    onSearch(debouncedValue)
  })

  const handleClear = () => {
    setValue('')
    onSearch('')
  }

  return (
    <div className={cn('relative flex items-center', className)}>
      <Search className="absolute left-3 h-4 w-4 text-muted-foreground pointer-events-none" />
      <input
        type="search"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder={placeholder}
        className={cn(
          'h-9 w-full rounded-xl border border-border bg-background pl-9 pr-9 text-sm',
          'placeholder:text-muted-foreground',
          'focus:outline-none focus:ring-2 focus:ring-ring focus:border-primary',
          'transition-colors duration-150'
        )}
      />
      {value && (
        <button
          onClick={handleClear}
          className="absolute right-3 text-muted-foreground hover:text-foreground transition-colors"
          aria-label="Clear search"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  )
}
