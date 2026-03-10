import { useMemo } from 'react'
import type { Span } from '../../hooks/useTraces'
import { formatDuration } from '../../utils/formatTime'

interface TraceWaterfallProps {
  spans: Span[]
  selectedSpanId: string | null
  onSelectSpan: (id: string) => void
}

interface SpanNode extends Span {
  depth: number
  children: SpanNode[]
}

const ROW_HEIGHT = 32
const LABEL_WIDTH = 200
const HEADER_HEIGHT = 40

export function TraceWaterfall({ spans, selectedSpanId, onSelectSpan }: TraceWaterfallProps) {
  // 1. Build tree to calculate depths
  const tree = useMemo(() => {
    const spanMap = new Map<string, SpanNode>()
    const roots: SpanNode[] = []

    // Initialize nodes
    spans.forEach(s => {
      spanMap.set(s.span_id, { ...s, depth: 0, children: [] })
    })

    // Link parents/children
    spans.forEach(s => {
      const node = spanMap.get(s.span_id)!
      if (s.parent_span_id && spanMap.has(s.parent_span_id)) {
        spanMap.get(s.parent_span_id)!.children.push(node)
      } else {
        roots.push(node)
      }
    })

    // DFS to set depths and flatten in order
    const flattened: SpanNode[] = []
    const walk = (node: SpanNode, depth: number) => {
      node.depth = depth
      flattened.push(node)
      // Sort children by start time
      node.children.sort((a, b) => a.start_time_ns - b.start_time_ns)
      node.children.forEach(child => walk(child, depth + 1))
    }

    roots.sort((a, b) => a.start_time_ns - b.start_time_ns)
    roots.forEach(r => walk(r, 0))

    return flattened
  }, [spans])

  // 2. Calculate time range
  const { minTime, maxTime, totalDuration } = useMemo(() => {
    if (spans.length === 0) return { minTime: 0, maxTime: 0, totalDuration: 0 }
    const startTimes = spans.map(s => s.start_time_ns)
    const endTimes = spans.map(s => s.end_time_ns || s.start_time_ns)
    const min = Math.min(...startTimes)
    const max = Math.max(...endTimes)
    return { minTime: min, maxTime: max, totalDuration: max - min }
  }, [spans])

  const svgWidth = 1200 // Could be dynamic
  const timelineWidth = svgWidth - LABEL_WIDTH - 40
  const svgHeight = HEADER_HEIGHT + tree.length * ROW_HEIGHT + 20

  const timeToX = (ns: number) => {
    if (totalDuration === 0) return LABEL_WIDTH
    const offset = ns - minTime
    return LABEL_WIDTH + (offset / totalDuration) * timelineWidth
  }

  // 3. Grid lines (e.g., 4 intervals)
  const gridLines = useMemo(() => {
    const lines = []
    for (let i = 0; i <= 4; i++) {
      const t = minTime + (totalDuration * i) / 4
      lines.push({ x: timeToX(t), label: formatDuration((totalDuration * i) / 4 / 1_000_000) })
    }
    return lines
  }, [minTime, totalDuration, timelineWidth])

  return (
    <div className="trace-waterfall-container">
      <svg width={svgWidth} height={svgHeight} className="trace-waterfall-svg">
        <rect x={0} y={0} width={svgWidth} height={HEADER_HEIGHT} className="trace-waterfall-header-bg" />
        
        {/* Grid lines */}
        {gridLines.map((line, i) => (
          <g key={i}>
            <line x1={line.x} y1={HEADER_HEIGHT} x2={line.x} y2={svgHeight} className="trace-waterfall-grid-line" />
            <text x={line.x} y={HEADER_HEIGHT - 10} textAnchor="middle" className="trace-waterfall-header-text">
              {line.label}
            </text>
          </g>
        ))}

        {/* Rows */}
        {tree.map((node, i) => {
          const y = HEADER_HEIGHT + i * ROW_HEIGHT
          const x = timeToX(node.start_time_ns)
          const endX = timeToX(node.end_time_ns || node.start_time_ns)
          const w = Math.max(endX - x, 2)
          const isSelected = node.span_id === selectedSpanId
          const statusClass = `trace-waterfall-bar--${(node.status || 'unset').toLowerCase()}`

          return (
            <g key={node.span_id} onClick={() => onSelectSpan(node.span_id)}>
              {i % 2 === 0 && (
                <rect x={0} y={y} width={svgWidth} height={ROW_HEIGHT} className="trace-waterfall-row-stripe" />
              )}
              
              {/* Span label with indentation */}
              <text x={10 + node.depth * 12} y={y + ROW_HEIGHT / 2 + 5} className="trace-waterfall-row-label">
                {node.name}
              </text>

              {/* Span bar */}
              <rect
                x={x}
                y={y + 8}
                width={w}
                height={ROW_HEIGHT - 16}
                rx={2}
                className={`trace-waterfall-bar ${statusClass} ${isSelected ? 'selected' : ''}`}
              />
              {isSelected && (
                <rect
                  x={x - 2}
                  y={y + 6}
                  width={w + 4}
                  height={ROW_HEIGHT - 12}
                  rx={3}
                  fill="none"
                  stroke="var(--accent)"
                  strokeWidth={2}
                />
              )}
            </g>
          )
        })}
      </svg>
    </div>
  )
}
