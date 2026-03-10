import { useMemo } from 'react'
import type { Span } from '../../hooks/useTraces'

interface TraceWaterfallProps {
  spans: Span[]
  selectedSpanId: string | null
  onSelectSpan: (spanId: string) => void
}

const ROW_HEIGHT = 32
const LABEL_WIDTH = 200
const HEADER_HEIGHT = 40
const MIN_BAR_WIDTH = 2

export function TraceWaterfall({ spans, selectedSpanId, onSelectSpan }: TraceWaterfallProps) {
  const { timelineStart, timelineEnd, duration } = useMemo(() => {
    if (spans.length === 0) return { timelineStart: 0, timelineEnd: 0, duration: 0 }
    
    let min = spans[0].start_time_ns
    let max = spans[0].end_time_ns || spans[0].start_time_ns
    
    for (const span of spans) {
      if (span.start_time_ns < min) min = span.start_time_ns
      const end = span.end_time_ns || span.start_time_ns
      if (end > max) max = end
    }
    
    return { timelineStart: min, timelineEnd: max, duration: max - min }
  }, [spans])

  const sortedSpans = useMemo(() => {
    // Basic tree layout: DFS order
    const childrenMap = new Map<string | null, Span[]>()
    for (const span of spans) {
      const parentId = span.parent_span_id
      if (!childrenMap.has(parentId)) childrenMap.set(parentId, [])
      childrenMap.get(parentId)!.push(span)
    }

    // Sort children by start time
    for (const children of childrenMap.values()) {
      children.sort((a, b) => a.start_time_ns - b.start_time_ns)
    }

    const result: { span: Span; depth: number }[] = []
    const walk = (parentId: string | null, depth: number) => {
      const children = childrenMap.get(parentId) || []
      for (const child of children) {
        result.push({ span: child, depth })
        walk(child.span_id, depth + 1)
      }
    }

    // Start from roots
    const roots = spans.filter(s => !s.parent_span_id || !spans.find(p => p.span_id === s.parent_span_id))
    roots.sort((a, b) => a.start_time_ns - b.start_time_ns)
    
    for (const root of roots) {
      result.push({ span: root, depth: 0 })
      walk(root.span_id, 1)
    }

    return result
  }, [spans])

  const svgWidth = LABEL_WIDTH + 800 // Fixed width for now, could be dynamic
  const svgHeight = HEADER_HEIGHT + sortedSpans.length * ROW_HEIGHT

  const timeToX = (timeNs: number) => {
    if (duration === 0) return LABEL_WIDTH
    const frac = (timeNs - timelineStart) / duration
    return LABEL_WIDTH + frac * 750 // 750px for timeline
  }

  const formatDuration = (ns: number) => {
    if (ns < 1000) return `${ns}ns`
    if (ns < 1000000) return `${(ns / 1000).toFixed(2)}µs`
    if (ns < 1000000000) return `${(ns / 1000000).toFixed(2)}ms`
    return `${(ns / 1000000000).toFixed(2)}s`
  }

  return (
    <div className="trace-waterfall-container">
      <svg width={svgWidth} height={svgHeight} className="trace-waterfall-svg">
        {/* Header */}
        <rect x={0} y={0} width={svgWidth} height={HEADER_HEIGHT} fill="var(--bg-secondary)" />
        <text x={10} y={25} className="trace-waterfall-label" style={{ fontWeight: 600 }}>Span Name</text>
        <text x={LABEL_WIDTH + 10} y={25} className="trace-waterfall-label" style={{ fontWeight: 600 }}>Timeline</text>
        <line x1={0} y1={HEADER_HEIGHT} x2={svgWidth} y2={HEADER_HEIGHT} stroke="var(--border)" />

        {/* Timeline grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map(frac => {
          const x = LABEL_WIDTH + frac * 750
          return (
            <g key={frac}>
              <line x1={x} y1={HEADER_HEIGHT} x2={x} y2={svgHeight} className="trace-waterfall-grid-line" strokeDasharray="4 4" />
              <text x={x} y={15} className="trace-waterfall-label" textAnchor="middle" style={{ fontSize: '10px' }}>
                {formatDuration(frac * duration)}
              </text>
            </g>
          )
        })}

        {/* Rows */}
        {sortedSpans.map(({ span, depth }, i) => {
          const y = HEADER_HEIGHT + i * ROW_HEIGHT
          const x = timeToX(span.start_time_ns)
          const endX = timeToX(span.end_time_ns || span.start_time_ns)
          const width = Math.max(endX - x, MIN_BAR_WIDTH)
          const isSelected = selectedSpanId === span.span_id
          const statusClass = !span.status || span.status === 'UNSET' ? 'unset' : span.status.toLowerCase() === 'error' ? 'error' : 'ok'

          return (
            <g key={span.span_id} onClick={() => onSelectSpan(span.span_id)}>
              {/* Row background */}
              <rect x={0} y={y} width={svgWidth} height={ROW_HEIGHT} className="trace-waterfall-row-bg" fill={isSelected ? 'var(--bg-secondary)' : 'transparent'} />
              
              {/* Span Label */}
              <text x={10 + depth * 12} y={y + 20} className="trace-waterfall-label" style={{ fontWeight: isSelected ? 600 : 400 }}>
                {span.name}
              </text>

              {/* Span Bar */}
              <rect
                x={x}
                y={y + 8}
                width={width}
                height={ROW_HEIGHT - 16}
                className={`trace-waterfall-bar trace-waterfall-bar--${statusClass} ${isSelected ? 'selected' : ''}`}
              />
              
              {/* Duration text next to bar */}
              <text x={x + width + 5} y={y + 20} className="trace-waterfall-label" style={{ fontSize: '10px', opacity: 0.7 }}>
                {formatDuration((span.end_time_ns || span.start_time_ns) - span.start_time_ns)}
              </text>

              <line x1={0} y1={y + ROW_HEIGHT} x2={svgWidth} y2={y + ROW_HEIGHT} stroke="var(--border)" opacity={0.3} />
            </g>
          )
        })}
      </svg>
    </div>
  )
}
