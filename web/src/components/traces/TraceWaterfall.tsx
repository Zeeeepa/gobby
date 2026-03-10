import { useMemo, useRef } from 'react'
import type { SpanRecord } from '../../hooks/useTraces'

interface TraceWaterfallProps {
  spans: SpanRecord[]
  onSelectSpan: (id: string) => void
  selectedSpanId: string | null
}

const ROW_HEIGHT = 32
const ROW_GAP = 4
const HEADER_HEIGHT = 40
const LABEL_WIDTH = 250
const TIMELINE_WIDTH = 800

interface SpanRow {
  span: SpanRecord
  depth: number
  row: number
}

function buildRows(spans: SpanRecord[]): SpanRow[] {
  const childrenMap = new Map<string, SpanRecord[]>()
  const rootSpans: SpanRecord[] = []
  
  for (const span of spans) {
    if (!span.parent_id) {
      rootSpans.push(span)
    } else {
      const children = childrenMap.get(span.parent_id) || []
      children.push(span)
      childrenMap.set(span.parent_id, children)
    }
  }

  for (const children of childrenMap.values()) {
    children.sort((a, b) => a.start_time_ns - b.start_time_ns)
  }
  rootSpans.sort((a, b) => a.start_time_ns - b.start_time_ns)

  const rows: SpanRow[] = []
  let currentRow = 0

  function traverse(span: SpanRecord, depth: number) {
    rows.push({ span, depth, row: currentRow++ })
    const children = childrenMap.get(span.span_id) || []
    for (const child of children) {
      traverse(child, depth + 1)
    }
  }

  for (const root of rootSpans) {
    traverse(root, 0)
  }

  const visited = new Set(rows.map(r => r.span.span_id))
  for (const span of spans) {
    if (!visited.has(span.span_id)) {
      rows.push({ span, depth: 0, row: currentRow++ })
    }
  }

  return rows
}

function formatNsToMs(ns: number): string {
  return (ns / 1_000_000).toFixed(2) + 'ms'
}

export function TraceWaterfall({ spans, onSelectSpan, selectedSpanId }: TraceWaterfallProps) {
  const svgRef = useRef<SVGSVGElement>(null)

  const rows = useMemo(() => buildRows(spans), [spans])

  const { minTime, totalTime } = useMemo(() => {
    if (spans.length === 0) return { minTime: 0, maxTime: 1, totalTime: 1 }
    let min = spans[0].start_time_ns
    let max = spans[0].end_time_ns
    for (const s of spans) {
      if (s.start_time_ns < min) min = s.start_time_ns
      if (s.end_time_ns > max) max = s.end_time_ns
    }
    return { minTime: min, maxTime: max, totalTime: Math.max(max - min, 1) }
  }, [spans])

  const svgWidth = LABEL_WIDTH + TIMELINE_WIDTH
  const svgHeight = Math.max(HEADER_HEIGHT + rows.length * (ROW_HEIGHT + ROW_GAP) + 20, 200)

  const timeToX = (t: number) => {
    const frac = (t - minTime) / totalTime
    return LABEL_WIDTH + frac * TIMELINE_WIDTH
  }

  const rowToY = (row: number) => HEADER_HEIGHT + row * (ROW_HEIGHT + ROW_GAP)

  const gridLines = [0, 0.25, 0.5, 0.75, 1]

  return (
    <div className="trace-waterfall-wrapper">
      <div className="trace-waterfall-scroll">
        <svg
          ref={svgRef}
          width={svgWidth}
          height={svgHeight}
          className="trace-waterfall-svg"
        >
          {/* Header background */}
          <rect x={0} y={0} width={svgWidth} height={HEADER_HEIGHT} className="trace-waterfall-header-bg" />

          {/* Grid lines */}
          {gridLines.map((frac, i) => {
            const x = LABEL_WIDTH + frac * TIMELINE_WIDTH
            const timeNs = minTime + frac * totalTime
            const relativeMs = ((timeNs - minTime) / 1_000_000).toFixed(1) + 'ms'
            return (
              <g key={i}>
                <line x1={x} y1={HEADER_HEIGHT} x2={x} y2={svgHeight} className="trace-waterfall-grid-line" />
                <text x={x} y={HEADER_HEIGHT - 10} className="trace-waterfall-header-text" textAnchor={i === 0 ? 'start' : i === 4 ? 'end' : 'middle'}>
                  {relativeMs}
                </text>
              </g>
            )
          })}

          {/* Rows */}
          {rows.map(({ span, depth, row }) => {
            const y = rowToY(row)
            const isSelected = selectedSpanId === span.span_id
            
            const x = timeToX(span.start_time_ns)
            const w = Math.max(timeToX(span.end_time_ns) - x, 2)
            
            const statusClass = `trace-waterfall-bar--${span.status.toLowerCase()}`

            return (
              <g key={span.span_id}>
                {/* Row stripe */}
                {row % 2 === 0 && (
                  <rect x={0} y={y} width={svgWidth} height={ROW_HEIGHT} className="trace-waterfall-row-stripe" />
                )}
                
                {/* Label */}
                <text
                  x={8 + depth * 12}
                  y={y + ROW_HEIGHT / 2 + 4}
                  className="trace-waterfall-row-label"
                >
                  {span.name.length > 25 ? span.name.slice(0, 25) + '...' : span.name}
                </text>

                {/* Bar */}
                <rect
                  x={x} y={y + 6} width={w} height={ROW_HEIGHT - 12}
                  rx={2} ry={2}
                  className={`trace-waterfall-bar ${statusClass} ${isSelected ? 'selected' : ''}`}
                  onClick={() => onSelectSpan(span.span_id)}
                >
                  <title>{span.name} ({formatNsToMs(span.end_time_ns - span.start_time_ns)})</title>
                </rect>
              </g>
            )
          })}
        </svg>
      </div>
    </div>
  )
}
