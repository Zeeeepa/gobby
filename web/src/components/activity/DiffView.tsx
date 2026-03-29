import { memo, useCallback } from 'react'

interface DiffViewProps {
  diff: string
  path: string
}

export const DiffView = memo(function DiffView({ diff, path }: DiffViewProps) {
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(diff)
  }, [diff])

  if (!diff) {
    return (
      <div className="activity-tab-empty">
        <p>No diff available</p>
      </div>
    )
  }

  const lines = diff.split('\n')

  return (
    <div className="flex flex-col h-full">
      <div
        className="flex items-center gap-2 px-3 border-b border-border shrink-0"
        style={{ height: 36, background: 'var(--bg-secondary)' }}
      >
        <span className="text-xs font-mono text-muted-foreground truncate flex-1">
          {path}
        </span>
        <button
          onClick={handleCopy}
          className="text-xs text-muted-foreground hover:text-foreground shrink-0"
          title="Copy diff"
        >
          Copy
        </button>
      </div>
      <pre className="flex-1 overflow-auto p-0 m-0 text-xs leading-5 font-mono">
        {lines.map((line, i) => {
          let className = 'diff-line'
          if (line.startsWith('+') && !line.startsWith('+++')) {
            className += ' diff-add'
          } else if (line.startsWith('-') && !line.startsWith('---')) {
            className += ' diff-remove'
          } else if (line.startsWith('@@')) {
            className += ' diff-hunk'
          } else if (line.startsWith('diff ') || line.startsWith('index ') || line.startsWith('---') || line.startsWith('+++')) {
            className += ' diff-meta'
          }
          return (
            <div key={i} className={className}>
              {line || '\u00a0'}
            </div>
          )
        })}
      </pre>
    </div>
  )
})
