// =============================================================================
// Risk classification for tool actions
// =============================================================================

export type RiskLevel = 'critical' | 'high' | 'medium' | 'low' | 'none'

interface RiskDef {
  level: RiskLevel
  label: string
  color: string
  bg: string
}

const RISK_DEFS: Record<RiskLevel, RiskDef> = {
  critical: { level: 'critical', label: 'Critical', color: '#dc2626', bg: 'rgba(220, 38, 38, 0.1)' },
  high:     { level: 'high',     label: 'High',     color: '#ef4444', bg: 'rgba(239, 68, 68, 0.1)' },
  medium:   { level: 'medium',   label: 'Medium',   color: '#f59e0b', bg: 'rgba(245, 158, 11, 0.1)' },
  low:      { level: 'low',      label: 'Low',      color: '#737373', bg: 'rgba(115, 115, 115, 0.08)' },
  none:     { level: 'none',     label: '',          color: 'transparent', bg: 'transparent' },
}

// Patterns for risk classification by tool name
const CRITICAL_PATTERNS = [
  /deploy/i, /push.*force/i, /reset.*hard/i, /drop.*table/i,
  /destroy/i, /rm\s+-rf/i, /force.?push/i,
]

const HIGH_PATTERNS = [
  /delete/i, /remove/i, /^bash$/i, /run_command/i,
  /git.*push/i, /migrate/i, /alter.*table/i,
]

const MEDIUM_PATTERNS = [
  /write/i, /edit/i, /create/i, /update/i, /insert/i,
  /patch/i, /put/i, /post/i, /webhook/i,
  /fetch/i, /http/i, /api.*call/i, /send/i,
]

/** Classify a tool action by risk level. */
export function classifyRisk(toolName: string, toolInput?: string | null): RiskLevel {
  const combined = toolInput ? `${toolName} ${toolInput}` : toolName

  for (const pattern of CRITICAL_PATTERNS) {
    if (pattern.test(combined)) return 'critical'
  }
  for (const pattern of HIGH_PATTERNS) {
    if (pattern.test(toolName)) return 'high'
  }
  for (const pattern of MEDIUM_PATTERNS) {
    if (pattern.test(toolName)) return 'medium'
  }
  return 'none'
}

// Patterns for task-level risk classification by title/type
const TASK_CRITICAL_PATTERNS = [/deploy/i, /production/i, /migration/i, /drop/i]
const TASK_HIGH_PATTERNS = [/delete/i, /remove.*data/i, /payment/i, /billing/i, /auth/i, /security/i, /credential/i]
const TASK_MEDIUM_PATTERNS = [/api/i, /external/i, /webhook/i, /integration/i, /database/i]

/** Classify task-level risk from title and type. */
export function classifyTaskRisk(title: string, taskType?: string): RiskLevel {
  const text = `${title} ${taskType || ''}`
  for (const p of TASK_CRITICAL_PATTERNS) { if (p.test(text)) return 'critical' }
  for (const p of TASK_HIGH_PATTERNS) { if (p.test(text)) return 'high' }
  for (const p of TASK_MEDIUM_PATTERNS) { if (p.test(text)) return 'medium' }
  return 'none'
}

/** Get the highest risk level from a list of tool names. */
export function highestRisk(toolNames: string[]): RiskLevel {
  const levels: RiskLevel[] = ['critical', 'high', 'medium', 'low', 'none']
  let highest = 4 // 'none'
  for (const name of toolNames) {
    const risk = classifyRisk(name)
    const idx = levels.indexOf(risk)
    if (idx < highest) highest = idx
  }
  return levels[highest]
}

// =============================================================================
// RiskBadge component
// =============================================================================

interface RiskBadgeProps {
  level: RiskLevel
  compact?: boolean
}

export function RiskBadge({ level, compact }: RiskBadgeProps) {
  if (level === 'none' || level === 'low') return null

  const def = RISK_DEFS[level]

  return (
    <span
      className={`risk-badge ${compact ? 'risk-badge--compact' : ''}`}
      style={{ color: def.color, background: def.bg, borderColor: def.color }}
      title={`${def.label} risk`}
    >
      <svg className="risk-badge-icon" width="10" height="10" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2L3 20h18L12 2zm0 4l6.9 12H5.1L12 6zm-1 5v4h2v-4h-2zm0 5v2h2v-2h-2z" />
      </svg>
      {!compact && <span className="risk-badge-label">{def.label}</span>}
    </span>
  )
}

/** Inline risk dot for action feed items. */
export function RiskDot({ level }: { level: RiskLevel }) {
  if (level === 'none' || level === 'low') return null
  const def = RISK_DEFS[level]
  return (
    <span
      className="risk-dot"
      style={{ background: def.color }}
      title={`${def.label} risk`}
    />
  )
}
