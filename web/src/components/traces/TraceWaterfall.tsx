import { useMemo, useRef } from 'react'
import type { Span } from '../../hooks/useTraces'

interface TraceWaterfallProps {
  spans: Span[]
  selectedSpanId: string | null
  onSelectSpan: (id: string) => void
}

const ROW_HEIGHT = 32
const LABEL_WIDTH = 200
const HEADER_HEIGHT = 40

export function TraceWaterfall({ spans, selectedSpanId, onSelectSpan }: TraceWaterfallProps) {
  const containerRef = useRef<HTMLDivElement>(null)

  // Sort and build hierarchy
  const processedSpans = useMemo(() => {
    if (spans.length === 0) return []

    // 1. Build child map
    const childrenByParent = new Map<string, Span[]>()
    const roots: Span[] = []

    for (const span of spans) {
      if (!span.parent_span_id) {
        roots.push(span)
      } else {
        const children = childrenByParent.get(span.parent_span_id) || []
        children.push(span)
        childrenByParent.set(span.parent_span_id, children)
      }
    }

    if (roots.length === 0 && spans.length > 0) roots.push(spans[0])

    // 2. Flatten into depth-first order
    const flattened: { span: Span; depth: number }[] = []
    function walk(span: Span, depth: number) {
      flattened.push({ span, depth })
      const children = childrenByParent.get(span.span_id) || []
      // Sort children by start time
      children.sort((a, b) => a.start_time_ns - b.start_time_ns)
      for (const child of children) {
        walk(child, depth + 1)
      }
    }

    // Sort roots by start time
    roots.sort((a, b) => a.start_time_ns - b.start_time_ns)
    for (const root of roots) {
      walk(root, 0)
    }
    return flattened
  }, [spans])

  // Compute timeline
  const { timelineStart, duration } = useMemo(() => {
    if (spans.length === 0) return { timelineStart: 0, duration: 0 }
    
    let start = spans[0].start_time_ns
    let end = spans[0].end_time_ns || spans[0].start_time_ns

    for (const s of spans) {
      if (s.start_time_ns < start) start = s.start_time_ns
      const sEnd = s.end_time_ns || s.start_time_ns
      if (sEnd > end) end = sEnd
    }

    return { timelineStart: start, duration: Math.max(end - start, 1) }
  }, [spans])

  const svgWidth = Math.max(800, 1200) // Could be responsive
  const svgHeight = HEADER_HEIGHT + processedSpans.length * ROW_HEIGHT + 20

  const timeToX = (time: number) => {
    const fraction = (time - timelineStart) / duration
    return LABEL_WIDTH + fraction * (svgWidth - LABEL_WIDTH - 20)
  }

  const formatDuration = (ns: number) => {
    const ms = ns / 1_000_000
    if (ms < 1) return `${(ns / 1000).toFixed(2)}µs`
    if (ms < 1000) return `${ms.toFixed(2)}ms`
    return `${(ms / 1000).toFixed(2)}s`
  }

  return (
    <div className="trace-waterfall">
      <div className="trace-waterfall-header">
        <span className="trace-waterfall-duration">
          Total Duration: {formatDuration(duration)}
        </span>
        <span className="trace-waterfall-span-count">
          {spans.length} spans
        </span>
      </div>

      <div className="trace-waterfall-scroll" ref={containerRef}>
        <svg
          width={svgWidth}
          height={svgHeight}
          className="trace-waterfall-svg"
        >
          {/* Header background */}
          <rect x={0} y={0} width={svgWidth} height={HEADER_HEIGHT} fill="var(--bg-secondary)" />
          
          {/* Time markers */}
          {[0, 0.25, 0.5, 0.75, 1].map((pct) => {
            const time = timelineStart + duration * pct
            const x = timeToX(time)
            return (
              <g key={pct}>
                <line x1={x} y1={0} x2={x} y2={svgHeight} className="trace-waterfall-grid" />
                <text x={x} y={HEADER_HEIGHT - 10} className="trace-waterfall-time" textAnchor="middle">
                  {formatDuration(time - timelineStart)}
                </text>
              </g>
            )
          })}

          {processedSpans.map(({ span, depth }, i) => {
            const y = HEADER_HEIGHT + i * ROW_HEIGHT
            const x = timeToX(span.start_time_ns)
            const w = Math.max(timeToX(span.end_time_ns || span.start_time_ns) - x, 2)
            const isSelected = span.span_id === selectedSpanId
            const statusClass = `trace-waterfall-bar--${(span.status || 'UNSET').toLowerCase()}`

            return (
              <g key={span.span_id} onClick={() => onSelectSpan(span.span_id)}>
                {/* Row stripe */}
                {i % 2 === 0 && (
                  <rect x={0} y={y} width={svgWidth} height={ROW_HEIGHT} fill="var(--bg-secondary)" opacity="0.3" />
                )}
                
                {/* Span label */}
                <text
                  x={10 + depth * 12}
                  y={y + ROW_HEIGHT / 2 + 5}
                  className="trace-waterfall-label"
                >
                  {span.name}
                </text>

                {/* Duration bar */}
                <rect
                  x={x}
                  y={y + 8}
                  width={w}
                  height={ROW_HEIGHT - 16}
                  rx={2}
                  className={`trace-waterfall-bar ${statusClass} ${isSelected ? 'trace-waterfall-bar--selected' : ''}`}
                />
                
                <title>{span.name} ({formatDuration((span.end_time_ns || span.start_time_ns) - span.start_time_ns)})</title>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
