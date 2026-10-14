import { X } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode, type TouchEvent } from 'react'
import { createPortal } from 'react-dom'
import { Button } from './Button'

interface ModalProps {
  open: boolean
  title: string
  onClose: () => void
  /** Let the user drag the sheet down to close it (when its content is scrolled to the top). */
  swipeToClose?: boolean
  children: ReactNode
}

/** How far (px) the sheet must be dragged down before letting go closes it. */
const SWIPE_CLOSE_DISTANCE = 80

/** Bottom sheet on phones, centred dialog on larger screens. */
export function Modal({ open, title, onClose, swipeToClose = false, children }: ModalProps) {
  const panelRef = useRef<HTMLDivElement>(null)
  const bodyRef = useRef<HTMLDivElement>(null)
  const dragStart = useRef<number | null>(null)
  const [dragOffset, setDragOffset] = useState(0)

  useEffect(() => {
    if (!open) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    panelRef.current?.focus()
    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener('keydown', onKey)
    }
  }, [open, onClose])

  if (!open) return null

  const swipeHandlers = swipeToClose
    ? {
        onTouchStart: (event: TouchEvent) => {
          // Only start a drag when the content is not scrolled, so scrolling up inside the sheet still works.
          dragStart.current = (bodyRef.current?.scrollTop ?? 0) > 0 ? null : (event.touches[0]?.clientY ?? null)
        },
        onTouchMove: (event: TouchEvent) => {
          if (dragStart.current === null) return
          setDragOffset(Math.max(0, (event.touches[0]?.clientY ?? dragStart.current) - dragStart.current))
        },
        onTouchEnd: () => {
          if (dragStart.current !== null && dragOffset > SWIPE_CLOSE_DISTANCE) onClose()
          dragStart.current = null
          setDragOffset(0)
        },
      }
    : {}

  return createPortal(
    <div className="fixed inset-0 z-50 flex items-end justify-center sm:items-center">
      <div className="absolute inset-0 bg-ink/45" onClick={onClose} aria-hidden />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        tabIndex={-1}
        className="relative flex max-h-[92dvh] w-full max-w-lg flex-col rounded-t-3xl bg-paper shadow-xl sm:rounded-3xl"
        style={dragOffset ? { transform: `translateY(${dragOffset}px)` } : undefined}
        {...swipeHandlers}
      >
        {swipeToClose && <div className="mx-auto mt-2 h-1.5 w-10 rounded-full bg-line sm:hidden" aria-hidden />}
        <div className="flex items-center justify-between gap-3 px-5 pb-2 pt-4">
          <h2 className="text-xl font-semibold">{title}</h2>
          <button type="button" onClick={onClose} aria-label="Close" className="grid size-11 place-items-center rounded-full text-muted hover:bg-wash">
            <X className="size-5" />
          </button>
        </div>
        <div ref={bodyRef} className="overflow-y-auto px-5 pb-[calc(env(safe-area-inset-bottom)+1.25rem)] pt-2">{children}</div>
      </div>
    </div>,
    document.body,
  )
}

interface ConfirmDialogProps {
  open: boolean
  title: string
  message: string
  confirmLabel?: string
  cancelLabel?: string
  loading?: boolean
  error?: string | null
  onConfirm: () => void
  onCancel: () => void
}

export function ConfirmDialog({ open, title, message, confirmLabel = 'Delete', cancelLabel = 'Cancel', loading, error, onConfirm, onCancel }: ConfirmDialogProps) {
  return (
    <Modal open={open} title={title} onClose={onCancel}>
      <p className="text-base text-muted">{message}</p>
      {error && (
        <p role="alert" className="mt-3 rounded-xl bg-danger-50 p-3 text-sm text-danger-700">
          {error}
        </p>
      )}
      <div className="mt-5 grid grid-cols-2 gap-3">
        <Button variant="secondary" onClick={onCancel} disabled={loading}>
          {cancelLabel}
        </Button>
        <Button variant="danger" onClick={onConfirm} loading={loading}>
          {confirmLabel}
        </Button>
      </div>
    </Modal>
  )
}
