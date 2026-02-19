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
          'flex items-center gap-1 px-2 py-1 rounded text-xs transition-colors',
          'border border-border',
          open ? 'bg-accent/20 text-foreground' : 'text-muted-foreground hover:text-foreground hover:bg-muted'
        )}
        onClick={() => setOpen(!open)}
        disabled={disabled}
        title={`Mode: ${current.label} — ${current.description}`}
        aria-label={`Chat mode: ${current.label}`}
      >
        <ModeIcon mode={mode} />
        <span>{current.label}</span>
        <ChevronIcon open={open} />
      </button>

      {open && (
        <div className="absolute bottom-full mb-1 left-0 w-52 rounded-md border border-border bg-background shadow-lg z-10">
          {CHAT_MODES.map((m) => (
            <button
              key={m.id}
              className={cn(
                'w-full flex items-center gap-2 px-3 py-2 text-left text-xs transition-colors',
                m.id === mode ? 'bg-accent/20 text-foreground' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
              )}
              onClick={() => { onModeChange(m.id); setOpen(false) }}
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
    case 'normal':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
        </svg>
      )
    case 'accept_edits':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M17 3a2.85 2.83 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z" />
          <path d="m15 5 4 4" />
        </svg>
      )
    case 'bypass':
      return (
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M20 13c0 5-3.5 7.5-7.66 8.95a1 1 0 0 1-.67-.01C7.5 20.5 4 18 4 13V6a1 1 0 0 1 1-1c2 0 4.5-1.2 6.24-2.72a1.17 1.17 0 0 1 1.52 0C14.51 3.81 17 5 19 5a1 1 0 0 1 1 1z" />
          <path d="m2 2 20 20" />
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
