/**
 * Artifact type icons and badges.
 *
 * Each artifact type gets a distinct SVG icon and color-coded badge.
 */

import type { CSSProperties } from 'react'

// =============================================================================
// Type metadata
// =============================================================================

export interface ArtifactTypeMeta {
  label: string
  color: string
}

export const ARTIFACT_TYPE_META: Record<string, ArtifactTypeMeta> = {
  code:            { label: 'Code',    color: '#3b82f6' },
  error:           { label: 'Error',   color: '#ef4444' },
  diff:            { label: 'Diff',    color: '#f59e0b' },
  file_path:       { label: 'File',    color: '#8b5cf6' },
  structured_data: { label: 'Data',    color: '#06b6d4' },
  text:            { label: 'Text',    color: '#6b7280' },
  plan:            { label: 'Plan',    color: '#10b981' },
  command_output:  { label: 'Output',  color: '#f97316' },
}

export function getTypeMeta(type: string): ArtifactTypeMeta {
  return ARTIFACT_TYPE_META[type] ?? { label: type, color: '#6b7280' }
}

// =============================================================================
// SVG Icons per type
// =============================================================================

const ICON_PROPS = {
  width: 16,
  height: 16,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
}

/** Code — brackets */
function CodeIcon() {
  return (
    <svg {...ICON_PROPS}>
      <polyline points="16 18 22 12 16 6" />
      <polyline points="8 6 2 12 8 18" />
    </svg>
  )
}

/** Error — warning triangle */
function ErrorIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

/** Diff — split view */
function DiffIcon() {
  return (
    <svg {...ICON_PROPS}>
      <line x1="12" y1="2" x2="12" y2="22" />
      <line x1="4" y1="8" x2="10" y2="8" />
      <line x1="4" y1="12" x2="10" y2="12" />
      <line x1="14" y1="10" x2="20" y2="10" />
      <line x1="14" y1="14" x2="20" y2="14" />
    </svg>
  )
}

/** File path — file */
function FilePathIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z" />
      <polyline points="13 2 13 9 20 9" />
    </svg>
  )
}

/** Structured data — braces */
function StructuredDataIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M8 3H5a2 2 0 0 0-2 2v3m18 0V5a2 2 0 0 0-2-2h-3" />
      <path d="M16 21h3a2 2 0 0 0 2-2v-3M3 16v3a2 2 0 0 0 2 2h3" />
      <line x1="9" y1="10" x2="15" y2="10" />
      <line x1="9" y1="14" x2="15" y2="14" />
    </svg>
  )
}

/** Text — document */
function TextIcon() {
  return (
    <svg {...ICON_PROPS}>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <polyline points="14 2 14 8 20 8" />
      <line x1="16" y1="13" x2="8" y2="13" />
      <line x1="16" y1="17" x2="8" y2="17" />
    </svg>
  )
}

/** Plan — checklist */
function PlanIcon() {
  return (
    <svg {...ICON_PROPS}>
      <line x1="10" y1="6" x2="21" y2="6" />
      <line x1="10" y1="12" x2="21" y2="12" />
      <line x1="10" y1="18" x2="21" y2="18" />
      <polyline points="3 6 4 7 6 5" />
      <polyline points="3 12 4 13 6 11" />
      <polyline points="3 18 4 19 6 17" />
    </svg>
  )
}

/** Command output — terminal */
function CommandOutputIcon() {
  return (
    <svg {...ICON_PROPS}>
      <polyline points="4 17 10 11 4 5" />
      <line x1="12" y1="19" x2="20" y2="19" />
    </svg>
  )
}

/** Fallback icon for unknown types */
function FallbackIcon() {
  return (
    <svg {...ICON_PROPS}>
      <circle cx="12" cy="12" r="10" />
      <line x1="12" y1="8" x2="12" y2="12" />
      <line x1="12" y1="16" x2="12.01" y2="16" />
    </svg>
  )
}

const ICON_MAP: Record<string, () => JSX.Element> = {
  code: CodeIcon,
  error: ErrorIcon,
  diff: DiffIcon,
  file_path: FilePathIcon,
  structured_data: StructuredDataIcon,
  text: TextIcon,
  plan: PlanIcon,
  command_output: CommandOutputIcon,
}

/**
 * Get the icon component for an artifact type.
 */
export function getArtifactIcon(type: string): JSX.Element {
  const IconComponent = ICON_MAP[type] ?? FallbackIcon
  return <IconComponent />
}

// =============================================================================
// Badge Component
// =============================================================================

/**
 * Type badge with icon and label, color-coded per artifact type.
 */
export function ArtifactTypeBadge({
  type,
  showIcon = true,
  style,
}: {
  type: string
  showIcon?: boolean
  style?: CSSProperties
}) {
  const meta = getTypeMeta(type)
  return (
    <span
      className="artifact-type-badge"
      style={{
        borderColor: meta.color,
        color: meta.color,
        display: 'inline-flex',
        alignItems: 'center',
        gap: '0.25rem',
        ...style,
      }}
    >
      {showIcon && getArtifactIcon(type)}
      {meta.label}
    </span>
  )
}
