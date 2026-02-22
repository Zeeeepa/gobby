import type { ChatMode } from '../../types/chat'

interface SessionStatusBarProps {
  sessionRef: string | null
  title: string | null
  mode: ChatMode
}

const MODE_CONFIG: Record<ChatMode, { dot: string; label: string; restriction: string }> = {
  plan: { dot: 'bg-blue-400', label: 'Plan', restriction: 'read-only' },
  accept_edits: { dot: 'bg-green-400', label: 'Act', restriction: 'edit gated' },
  bypass: { dot: 'bg-amber-400', label: 'Auto', restriction: 'unrestricted' },
}

export function SessionStatusBar({ sessionRef, title, mode }: SessionStatusBarProps) {
  const { dot, label, restriction } = MODE_CONFIG[mode]

  return (
    <div className="flex items-center justify-between px-4 py-1.5 bg-muted border-b border-border text-xs">
      <div className="flex items-center gap-1.5 min-w-0">
        {sessionRef && (
          <span className="font-mono text-accent shrink-0">{sessionRef}</span>
        )}
        <span className="text-muted-foreground truncate">
          {sessionRef && title ? ': ' : ''}{title ?? 'New conversation'}
        </span>
      </div>
      <div className="flex items-center gap-1.5 shrink-0 whitespace-nowrap ml-4">
        <span className={`inline-block w-1.5 h-1.5 rounded-full ${dot}`} />
        <span className="text-muted-foreground">{label}</span>
        <span className="hidden sm:inline text-muted-foreground/60">&middot; {restriction}</span>
      </div>
    </div>
  )
}
