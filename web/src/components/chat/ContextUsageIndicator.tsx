interface ContextUsageIndicatorProps {
  inputTokens: number
  outputTokens: number
  contextWindow: number | null
}

export function ContextUsageIndicator({ inputTokens, outputTokens, contextWindow }: ContextUsageIndicatorProps) {
  const totalTokens = inputTokens + outputTokens
  const percentage = contextWindow ? Math.min((totalTokens / contextWindow) * 100, 100) : 0
  const displayPercent = Math.round(percentage)

  // SVG pie/ring chart
  const size = 20
  const strokeWidth = 3
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const dashOffset = circumference - (percentage / 100) * circumference

  // Color based on usage: green < 50%, yellow 50-80%, red > 80%
  const color = percentage > 80 ? 'var(--destructive, #ef4444)' : percentage > 50 ? 'var(--warning, #f59e0b)' : 'var(--success, #22c55e)'

  const formatTokens = (n: number) => {
    if (n >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
    if (n >= 1_000) return `${(n / 1_000).toFixed(0)}K`
    return String(n)
  }

  return (
    <div
      className="flex items-center gap-1.5 text-xs text-muted-foreground"
      title={contextWindow ? `Context: ${formatTokens(totalTokens)} / ${formatTokens(contextWindow)} tokens (${displayPercent}%)\nInput: ${formatTokens(inputTokens)} | Output: ${formatTokens(outputTokens)}` : 'Context usage: 0%'}
    >
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} className="shrink-0" style={{ transform: 'rotate(-90deg)' }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={strokeWidth}
          opacity={0.15}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeDasharray={circumference}
          strokeDashoffset={dashOffset}
          strokeLinecap="round"
        />
      </svg>
      <span className="tabular-nums">{displayPercent}%</span>
    </div>
  )
}
