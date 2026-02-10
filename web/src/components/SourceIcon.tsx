interface SourceIconProps {
  source: string
  size?: number
}

export function SourceIcon({ source, size = 14 }: SourceIconProps) {
  switch (source) {
    case 'claude':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className="source-icon source-icon-claude">
          <path d="M12 2L14.5 8.5L21 6L16.5 12L21 18L14.5 15.5L12 22L9.5 15.5L3 18L7.5 12L3 6L9.5 8.5L12 2Z" fill="#f97316" />
        </svg>
      )
    case 'gemini':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className="source-icon source-icon-gemini">
          <path d="M12 2L17 7L22 12L17 17L12 22L7 17L2 12L7 7L12 2Z" fill="#3b82f6" />
        </svg>
      )
    case 'codex':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className="source-icon source-icon-codex" stroke="#a855f7" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
          <polyline points="7 8 3 12 7 16" />
          <polyline points="17 8 21 12 17 16" />
        </svg>
      )
    case 'web-chat':
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className="source-icon source-icon-web-chat" stroke="#4ade80" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        </svg>
      )
    default:
      return (
        <svg width={size} height={size} viewBox="0 0 24 24" fill="none" className="source-icon" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <circle cx="12" cy="12" r="10" />
        </svg>
      )
  }
}

export function sourceColor(source: string): string {
  switch (source) {
    case 'claude': return '#f97316'
    case 'gemini': return '#3b82f6'
    case 'codex': return '#a855f7'
    case 'web-chat': return '#4ade80'
    default: return '#737373'
  }
}
