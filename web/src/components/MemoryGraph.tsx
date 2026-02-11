import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import dagre from 'dagre'
import type { GobbyMemory, MemoryGraphData, MemoryCrossRef } from '../hooks/useMemory'

interface MemoryGraphProps {
  memories: GobbyMemory[]
  fetchGraphData: () => Promise<MemoryGraphData | null>
  onSelect: (memory: GobbyMemory) => void
}

interface GraphNode {
  id: string
  memory: GobbyMemory
  x: number
  y: number
}

interface GraphEdge {
  from: string
  to: string
  similarity: number
}

const NODE_WIDTH = 180
const NODE_HEIGHT = 44

const TYPE_COLORS: Record<string, string> = {
  fact: 'var(--accent)',
  preference: '#c084fc',
  pattern: '#34d399',
  context: '#fbbf24',
}

function getTypeColor(type: string): string {
  return TYPE_COLORS[type] || 'var(--text-muted)'
}

function buildGraph(
  memories: GobbyMemory[],
  crossrefs: MemoryCrossRef[]
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const memoryMap = new Map(memories.map(m => [m.id, m]))
  const edges: GraphEdge[] = []

  for (const cr of crossrefs) {
    if (memoryMap.has(cr.source_id) && memoryMap.has(cr.target_id)) {
      edges.push({ from: cr.source_id, to: cr.target_id, similarity: cr.similarity })
    }
  }

  // Find connected components
  const connected = new Set<string>()
  for (const edge of edges) {
    connected.add(edge.from)
    connected.add(edge.to)
  }

  const connectedMemories = memories.filter(m => connected.has(m.id))
  const disconnected = memories.filter(m => !connected.has(m.id))

  // Use dagre for connected subgraph
  const nodes: GraphNode[] = []

  if (connectedMemories.length > 0) {
    const g = new dagre.graphlib.Graph()
    g.setGraph({ rankdir: 'TB', nodesep: 30, ranksep: 50, marginx: 30, marginy: 30 })
    g.setDefaultEdgeLabel(() => ({}))

    for (const m of connectedMemories) {
      g.setNode(m.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
    }
    for (const edge of edges) {
      g.setEdge(edge.from, edge.to)
    }

    dagre.layout(g)

    for (const m of connectedMemories) {
      const nodeData = g.node(m.id)
      if (!nodeData) continue
      nodes.push({
        id: m.id,
        memory: m,
        x: nodeData.x - NODE_WIDTH / 2,
        y: nodeData.y - NODE_HEIGHT / 2,
      })
    }
  }

  // Grid layout for disconnected nodes (or all nodes if no edges)
  if (disconnected.length > 0) {
    const cols = Math.ceil(Math.sqrt(disconnected.length))
    const padX = NODE_WIDTH + 24
    const padY = NODE_HEIGHT + 20
    // Offset grid below the dagre layout
    const gridOffsetY = nodes.length > 0
      ? Math.max(...nodes.map(n => n.y)) + NODE_HEIGHT + 60
      : 30

    for (let i = 0; i < disconnected.length; i++) {
      const col = i % cols
      const row = Math.floor(i / cols)
      nodes.push({
        id: disconnected[i].id,
        memory: disconnected[i],
        x: 30 + col * padX,
        y: gridOffsetY + row * padY,
      })
    }
  }

  return { nodes, edges }
}

export function MemoryGraph({ memories, fetchGraphData, onSelect }: MemoryGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [graphData, setGraphData] = useState<{ crossrefs: MemoryCrossRef[] } | null>(null)
  const [loading, setLoading] = useState(true)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 })
  const [dragging, setDragging] = useState(false)
  const dragStart = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchGraphData().then(data => {
      if (!cancelled && data) {
        setGraphData({ crossrefs: data.crossrefs })
      }
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [fetchGraphData])

  const { nodes, edges } = useMemo(() => {
    if (!graphData) return { nodes: [], edges: [] }
    return buildGraph(memories, graphData.crossrefs)
  }, [memories, graphData])

  const nodeMap = useMemo(
    () => new Map(nodes.map(n => [n.id, n])),
    [nodes]
  )

  // Pan & zoom
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return
    setDragging(true)
    dragStart.current = { x: e.clientX, y: e.clientY, vx: view.x, vy: view.y }
  }, [view.x, view.y])

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging || !dragStart.current) return
    const dx = e.clientX - dragStart.current.x
    const dy = e.clientY - dragStart.current.y
    setView(v => ({ ...v, x: dragStart.current!.vx + dx, y: dragStart.current!.vy + dy }))
  }, [dragging])

  const handleMouseUp = useCallback(() => {
    setDragging(false)
    dragStart.current = null
  }, [])

  const handleWheel = useCallback((e: React.WheelEvent) => {
    if (e.currentTarget.contains(e.target as Node)) e.preventDefault()
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    const mx = e.clientX - rect.left
    const my = e.clientY - rect.top
    const delta = e.deltaY > 0 ? 0.9 : 1.1
    setView(v => {
      const newScale = Math.min(3, Math.max(0.2, v.scale * delta))
      const ratio = newScale / v.scale
      return {
        scale: newScale,
        x: mx - (mx - v.x) * ratio,
        y: my - (my - v.y) * ratio,
      }
    })
  }, [])

  const zoomIn = () => setView(v => ({ ...v, scale: Math.min(3, v.scale * 1.2) }))
  const zoomOut = () => setView(v => ({ ...v, scale: Math.max(0.2, v.scale / 1.2) }))

  const fitView = useCallback(() => {
    if (nodes.length === 0 || !svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity
    for (const n of nodes) {
      minX = Math.min(minX, n.x)
      minY = Math.min(minY, n.y)
      maxX = Math.max(maxX, n.x + NODE_WIDTH)
      maxY = Math.max(maxY, n.y + NODE_HEIGHT)
    }
    const gw = maxX - minX
    const gh = maxY - minY
    const scale = Math.min(rect.width / (gw + 60), rect.height / (gh + 60), 2) * 0.9
    setView({
      scale,
      x: (rect.width - gw * scale) / 2 - minX * scale,
      y: (rect.height - gh * scale) / 2 - minY * scale,
    })
  }, [nodes])

  // Fit on first load
  useEffect(() => {
    if (nodes.length > 0) fitView()
  }, [nodes.length, fitView]) // re-fit only when node count changes

  if (loading) {
    return (
      <div className="memory-graph-container">
        <div className="memory-graph-empty">Loading graph data...</div>
      </div>
    )
  }

  if (edges.length === 0 && nodes.length === 0) {
    return (
      <div className="memory-graph-container">
        <div className="memory-graph-empty">
          <div className="memory-empty-icon">&#x1f578;</div>
          <div>No connections found</div>
          <div className="memory-empty-hint">
            Memory crossrefs are created when related memories are detected.
          </div>
        </div>
      </div>
    )
  }

  const legendTypes = [...new Set(nodes.map(n => n.memory.memory_type))]

  return (
    <div className="memory-graph-container">
      <svg
        ref={svgRef}
        className="memory-graph-svg"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        style={{ cursor: dragging ? 'grabbing' : 'grab' }}
      >
        <g transform={`translate(${view.x}, ${view.y}) scale(${view.scale})`}>
          {/* Edges */}
          {edges.map((edge, i) => {
            const from = nodeMap.get(edge.from)
            const to = nodeMap.get(edge.to)
            if (!from || !to) return null
            const x1 = from.x + NODE_WIDTH / 2
            const y1 = from.y + NODE_HEIGHT
            const x2 = to.x + NODE_WIDTH / 2
            const y2 = to.y
            const cy1 = y1 + (y2 - y1) * 0.4
            const cy2 = y2 - (y2 - y1) * 0.4
            const isHighlighted = hoveredId === edge.from || hoveredId === edge.to
            const strokeWidth = 1 + edge.similarity * 2
            return (
              <path
                key={i}
                d={`M ${x1} ${y1} C ${x1} ${cy1}, ${x2} ${cy2}, ${x2} ${y2}`}
                fill="none"
                stroke={isHighlighted ? 'var(--accent)' : 'var(--border)'}
                strokeWidth={isHighlighted ? strokeWidth + 0.5 : strokeWidth}
                opacity={isHighlighted ? 1 : 0.5}
              />
            )
          })}

          {/* Nodes */}
          {nodes.map(node => {
            const color = getTypeColor(node.memory.memory_type)
            const isHovered = hoveredId === node.id
            const scale = 0.8 + node.memory.importance * 0.4
            const w = NODE_WIDTH * scale
            const h = NODE_HEIGHT * scale
            const x = node.x + (NODE_WIDTH - w) / 2
            const y = node.y + (NODE_HEIGHT - h) / 2
            return (
              <g
                key={node.id}
                transform={`translate(${x}, ${y})`}
                onClick={e => { e.stopPropagation(); onSelect(node.memory) }}
                onMouseEnter={() => setHoveredId(node.id)}
                onMouseLeave={() => setHoveredId(null)}
                style={{ cursor: 'pointer' }}
              >
                <rect
                  width={w}
                  height={h}
                  rx={8}
                  fill="var(--bg-secondary)"
                  stroke={isHovered ? 'var(--accent)' : color}
                  strokeWidth={isHovered ? 2 : 1.5}
                />
                {/* Type indicator bar */}
                <rect x={0} y={0} width={4} height={h} rx={2} fill={color} />
                {/* Type label */}
                <text
                  x={12}
                  y={14}
                  fontSize={9}
                  fontFamily="var(--font-mono)"
                  fill="var(--text-muted)"
                  style={{ textTransform: 'uppercase' }}
                >
                  {node.memory.memory_type}
                </text>
                {/* Content preview */}
                <text
                  x={12}
                  y={h - 10}
                  fontSize={11}
                  fontFamily="var(--font-sans)"
                  fill="var(--text-primary)"
                >
                  {node.memory.content.length > 22
                    ? node.memory.content.slice(0, 22) + '...'
                    : node.memory.content}
                </text>
              </g>
            )
          })}
        </g>
      </svg>

      {/* Controls */}
      <div className="memory-graph-controls">
        <button className="memory-graph-ctrl-btn" onClick={zoomIn} title="Zoom in">+</button>
        <button className="memory-graph-ctrl-btn" onClick={zoomOut} title="Zoom out">&minus;</button>
        <button className="memory-graph-ctrl-btn" onClick={fitView} title="Fit to view">&#x2318;</button>
        <span className="memory-graph-ctrl-label">{Math.round(view.scale * 100)}%</span>
      </div>

      {/* Info */}
      <div className="memory-graph-info">
        {nodes.length} nodes &middot; {edges.length} edges
      </div>

      {/* Legend */}
      {legendTypes.length > 0 && (
        <div className="memory-graph-legend">
          {legendTypes.map(type => (
            <div key={type} className="memory-graph-legend-item">
              <span className="memory-graph-legend-dot" style={{ backgroundColor: getTypeColor(type) }} />
              {type}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
