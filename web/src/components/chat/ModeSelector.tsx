import type { ChatMode } from '../../types/chat'
import { CHAT_MODES } from '../../types/chat'
import { cn } from '../../lib/utils'

interface ModeSelectorProps {
  mode: ChatMode
  onModeChange: (mode: ChatMode) => void
  disabled?: boolean
}

export function ModeSelector({ mode, onModeChange, disabled }: ModeSelectorProps) {
  return (
    <div className="flex rounded-md border border-border text-xs" role="radiogroup" aria-label="Chat mode">
      {CHAT_MODES.map((m, i) => (
        <button
          key={m.id}
          role="radio"
          aria-checked={m.id === mode}
          className={cn(
            'px-2 py-1 transition-colors',
            i === 0 && 'rounded-l-md',
            i === CHAT_MODES.length - 1 && 'rounded-r-md',
            m.id === mode
              ? 'bg-accent text-accent-foreground'
              : 'text-muted-foreground hover:bg-muted'
          )}
          onClick={() => onModeChange(m.id)}
          disabled={disabled}
          title={m.description}
        >
          {m.label}
        </button>
      ))}
    </div>
  )
}
