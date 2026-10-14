import { X } from 'lucide-react'
import type { ReactNode } from 'react'

interface ToggleChipProps {
  selected: boolean
  onClick: () => void
  children: ReactNode
}

/** A pill the user can switch on and off (used for filters). */
export function ToggleChip({ selected, onClick, children }: ToggleChipProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={selected}
      className={`inline-flex min-h-11 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-full border px-3.5 text-sm font-medium transition ${
        selected ? 'border-brand-700 bg-brand-700 text-white' : 'border-line bg-white text-ink hover:bg-wash'
      }`}
    >
      {children}
    </button>
  )
}

export function TagPill({ children, onRemove }: { children: ReactNode; onRemove?: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full bg-brand-50 px-2.5 py-1 text-xs font-medium text-brand-800">
      {children}
      {onRemove && (
        <button type="button" onClick={onRemove} aria-label={`Remove tag ${String(children)}`} className="-my-2.5 -ml-1 -mr-2.5 grid size-11 shrink-0 place-items-center rounded-full hover:bg-brand-100">
          <X className="size-3.5" />
        </button>
      )}
    </span>
  )
}
