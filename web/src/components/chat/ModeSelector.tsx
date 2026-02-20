import { useState, useRef, useEffect } from 'react'
import type { ChatMode } from '../../types/chat'
import { CHAT_MODES } from '../../types/chat'
import { cn } from '../../lib/utils'

interface ModeSelectorProps {
  mode: ChatMode
  onModeChange: (mode: ChatMode) => void
  disabled?: boolean
}

export function ModeSelector({ mode, onModeChange, disabled }: ModeSelectorProps) {
  const [open, setOpen] = useState(false)
  const [focusedIndex, setFocusedIndex] = useState(-1)
  const ref = useRef<HTMLDivElement>(null)

  // Close on click outside
  useEffect(() => {
    if (!open) return
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [open])

  const current = CHAT_MODES.find((m) => m.id === mode) ?? CHAT_MODES[0]

  return (
    <div className="relative" ref={ref}>
      <button
        className={cn(
          'flex items-center justify-between gap-1 w-[100px] px-2.5 rounded-lg text-xs transition-colors min-h-[40px]',
          'border border-border',
          open ? 'bg-accent/20 text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted'
        )}
        onClick={() => setOpen(!open)}
        disabled={disabled}
        title={`Mode: ${current.label} — ${current.description}`}
        aria-label={`Chat mode: ${current.label}`}
      >
        <div className="flex items-center gap-1.5">
          <ModeIcon mode={mode} />
          <span>{current.label}</span>
        </div>
        <ChevronIcon open={open} />
      </button>

      {open && (
        <div
          className="absolute bottom-full mb-1 left-0 w-[180px] rounded-md border border-border bg-background shadow-lg z-10"
          role="listbox"
          aria-label="Chat modes"
          onKeyDown={(e) => {
            if (e.key === 'Escape') { setOpen(false); setFocusedIndex(-1) }
            if (e.key === 'ArrowDown') { e.preventDefault(); setFocusedIndex((i) => Math.min(i + 1, CHAT_MODES.length - 1)) }
            if (e.key === 'ArrowUp') { e.preventDefault(); setFocusedIndex((i) => Math.max(i - 1, 0)) }
            if (e.key === 'Enter' && focusedIndex >= 0) { onModeChange(CHAT_MODES[focusedIndex].id); setOpen(false); setFocusedIndex(-1) }
          }}
        >
          {CHAT_MODES.map((m, i) => (
            <button
              key={m.id}
              role="option"
              aria-selected={m.id === mode}
              className={cn(
                'w-full flex items-center gap-2 px-3 py-2 text-left text-xs transition-colors',
                m.id === mode ? 'bg-accent/20 text-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground',
                i === focusedIndex && 'ring-1 ring-accent'
              )}
              onClick={() => { onModeChange(m.id); setOpen(false); setFocusedIndex(-1) }}
            >
              <ModeIcon mode={m.id} />
              <div>
                <div className="font-medium">{m.label}</div>
                <div className="text-[10px] opacity-60">{m.description}</div>
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  )
}

function ModeIcon({ mode }: { mode: ChatMode }) {
  switch (mode) {
    case 'accept_edits':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
      )
    case 'bypass':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2" />
        </svg>
      )
    case 'plan':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <line x1="9" y1="18" x2="15" y2="18" />
          <line x1="10" y1="22" x2="14" y2="22" />
          <path d="M15.09 14c.18-.98.65-1.74 1.41-2.5A4.65 4.65 0 0 0 18 8 6 6 0 0 0 6 8c0 1 .23 2.23 1.5 3.5A4.61 4.61 0 0 1 8.91 14" />
        </svg>
      )
    default:
      return null
  }
}

function ChevronIcon({ open }: { open: boolean }) {
  return (
    <svg
      width="10"
      height="10"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      className={cn('transition-transform', open ? '' : 'rotate-180')}
    >
      <polyline points="6 15 12 9 18 15" />
    </svg>
  )
}
