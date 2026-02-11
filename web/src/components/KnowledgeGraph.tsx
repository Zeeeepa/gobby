import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import dagre from 'dagre'
import type { KnowledgeGraphData, KnowledgeEntity, KnowledgeRelationship } from '../hooks/useMemory'

interface KnowledgeGraphProps {
  fetchKnowledgeGraph: (limit?: number) => Promise<KnowledgeGraphData | null>
  fetchEntityNeighbors: (name: string) => Promise<KnowledgeGraphData | null>
}

interface GraphNode {
  id: string
  entity: KnowledgeEntity
  x: number
  y: number
}

interface GraphEdge {
  source: string
  target: string
  relationship: KnowledgeRelationship
}

const NODE_WIDTH = 140
const NODE_HEIGHT = 36

const ENTITY_TYPE_COLORS: Record<string, string> = {
  function: '#60a5fa',
  file: '#34d399',
  class: '#c084fc',
  concept: '#fbbf24',
  hook: '#f472b6',
  module: '#2dd4bf',
  config: '#fb923c',
  test: '#a78bfa',
  route: '#38bdf8',
  component: '#4ade80',
}

function getEntityColor(type: string): string {
  return ENTITY_TYPE_COLORS[type.toLowerCase()] || 'var(--text-muted)'
}

/** Simple string hash to generate a hue value for edge colors. */
function hashToHue(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  return Math.abs(hash) % 360
}

function edgeColor(relType: string): string {
  const hue = hashToHue(relType)
  return `hsl(${hue}, 55%, 55%)`
}

function truncate(text: string, max: number): string {
  return text.length > max ? text.slice(0, max) + '\u2026' : text
}

function mergeGraphData(
  existing: KnowledgeGraphData,
  incoming: KnowledgeGraphData
): KnowledgeGraphData {
  const entityMap = new Map(existing.entities.map(e => [e.name, e]))
  for (const e of incoming.entities) {
    if (!entityMap.has(e.name)) {
      entityMap.set(e.name, e)
    }
  }

  const edgeKey = (r: KnowledgeRelationship) => `${r.source}|${r.type}|${r.target}`
  const edgeSet = new Set(existing.relationships.map(edgeKey))
  const mergedRelationships = [...existing.relationships]
  for (const r of incoming.relationships) {
    if (!edgeSet.has(edgeKey(r))) {
      edgeSet.add(edgeKey(r))
      mergedRelationships.push(r)
    }
  }

  return {
    entities: [...entityMap.values()],
    relationships: mergedRelationships,
  }
}

function buildLayout(data: KnowledgeGraphData): { nodes: GraphNode[]; edges: GraphEdge[] } {
  if (data.entities.length === 0) return { nodes: [], edges: [] }

  const entityNames = new Set(data.entities.map(e => e.name))

  const edges: GraphEdge[] = data.relationships.filter(
    r => entityNames.has(r.source) && entityNames.has(r.target)
  ).map(r => ({ source: r.source, target: r.target, relationship: r }))

  // Find connected entities
  const connected = new Set<string>()
  for (const edge of edges) {
    connected.add(edge.source)
    connected.add(edge.target)
  }

  const connectedEntities = data.entities.filter(e => connected.has(e.name))
  const disconnected = data.entities.filter(e => !connected.has(e.name))

  const nodes: GraphNode[] = []

  if (connectedEntities.length > 0) {
    const g = new dagre.graphlib.Graph()
    g.setGraph({ rankdir: 'LR', nodesep: 24, ranksep: 60, marginx: 30, marginy: 30 })
    g.setDefaultEdgeLabel(() => ({}))

    for (const entity of connectedEntities) {
      g.setNode(entity.name, { width: NODE_WIDTH, height: NODE_HEIGHT })
    }
    for (const edge of edges) {
      g.setEdge(edge.source, edge.target)
    }

    dagre.layout(g)

    for (const entity of connectedEntities) {
      const nodeData = g.node(entity.name)
      if (!nodeData) continue
      nodes.push({
        id: entity.name,
        entity,
        x: nodeData.x - NODE_WIDTH / 2,
        y: nodeData.y - NODE_HEIGHT / 2,
      })
    }
  }

  // Grid layout for disconnected nodes below the dagre layout
  if (disconnected.length > 0) {
    const cols = Math.ceil(Math.sqrt(disconnected.length))
    const padX = NODE_WIDTH + 20
    const padY = NODE_HEIGHT + 16
    const gridOffsetY = nodes.length > 0
      ? Math.max(...nodes.map(n => n.y)) + NODE_HEIGHT + 50
      : 30

    for (let i = 0; i < disconnected.length; i++) {
      const col = i % cols
      const row = Math.floor(i / cols)
      nodes.push({
        id: disconnected[i].name,
        entity: disconnected[i],
        x: 30 + col * padX,
        y: gridOffsetY + row * padY,
      })
    }
  }

  return { nodes, edges }
}

export function KnowledgeGraph({ fetchKnowledgeGraph, fetchEntityNeighbors }: KnowledgeGraphProps) {
  const svgRef = useRef<SVGSVGElement>(null)
  const [graphData, setGraphData] = useState<KnowledgeGraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [view, setView] = useState({ x: 0, y: 0, scale: 1 })
  const [dragging, setDragging] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [expandingNode, setExpandingNode] = useState<string | null>(null)
  const dragStart = useRef<{ x: number; y: number; vx: number; vy: number } | null>(null)

  // Initial data fetch
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchKnowledgeGraph().then(data => {
      if (!cancelled && data) {
        setGraphData(data)
      }
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [fetchKnowledgeGraph])

  // Build layout from data
  const { nodes, edges } = useMemo(() => {
    if (!graphData) return { nodes: [], edges: [] }
    return buildLayout(graphData)
  }, [graphData])

  const nodeMap = useMemo(
    () => new Map(nodes.map(n => [n.id, n])),
    [nodes]
  )

  // Search matching
  const searchLower = searchQuery.toLowerCase()
  const isSearchActive = searchQuery.length > 0
  const matchesSearch = useCallback((name: string) => {
    if (!isSearchActive) return true
    return name.toLowerCase().includes(searchLower)
  }, [isSearchActive, searchLower])

  // Double-click handler: fetch neighbors and merge
  const handleDoubleClick = useCallback((entityName: string) => {
    if (expandingNode) return
    setExpandingNode(entityName)
    fetchEntityNeighbors(entityName).then(data => {
      if (data && graphData) {
        setGraphData(mergeGraphData(graphData, data))
      }
      setExpandingNode(null)
    }).catch(() => {
      setExpandingNode(null)
    })
  }, [fetchEntityNeighbors, graphData, expandingNode])

  // Pan & zoom handlers
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
    e.preventDefault()
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
  }, [nodes.length > 0]) // eslint-disable-line react-hooks/exhaustive-deps

  // Tooltip state
  const [tooltip, setTooltip] = useState<{
    x: number; y: number; entity: KnowledgeEntity
  } | null>(null)

  const handleNodeMouseEnter = useCallback((e: React.MouseEvent, entity: KnowledgeEntity) => {
    setHoveredId(entity.name)
    const rect = svgRef.current?.getBoundingClientRect()
    if (!rect) return
    setTooltip({
      x: e.clientX - rect.left,
      y: e.clientY - rect.top,
      entity,
    })
  }, [])

  const handleNodeMouseLeave = useCallback(() => {
    setHoveredId(null)
    setTooltip(null)
  }, [])

  // Loading state
  if (loading) {
    return (
      <div className="knowledge-graph-container">
        <div className="knowledge-graph-empty">Loading knowledge graph...</div>
      </div>
    )
  }

  // Empty state
  if (!graphData || (graphData.entities.length === 0 && graphData.relationships.length === 0)) {
    return (
      <div className="knowledge-graph-container">
        <div className="knowledge-graph-empty">
          <div>Neo4j not configured</div>
          <div style={{ fontSize: 'calc(var(--font-size-base) * 0.8)', marginTop: 4 }}>
            Connect a Neo4j instance to explore knowledge graph entities and relationships.
          </div>
        </div>
      </div>
    )
  }

  // Determine which entity types are present for the legend
  const legendTypes = [...new Set(nodes.map(n => n.entity.type.toLowerCase()))]

  // Arrow marker ID
  const arrowMarkerId = 'knowledge-graph-arrow'

  return (
    <div className="knowledge-graph-container">
      <svg
        ref={svgRef}
        className="knowledge-graph-svg"
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        style={{ cursor: dragging ? 'grabbing' : 'grab' }}
      >
        <defs>
          <marker
            id={arrowMarkerId}
            viewBox="0 0 10 6"
            refX="10"
            refY="3"
            markerWidth="8"
            markerHeight="6"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 3 L 0 6 Z" fill="var(--text-muted)" />
          </marker>
        </defs>

        <g transform={`translate(${view.x}, ${view.y}) scale(${view.scale})`}>
          {/* Edges */}
          {edges.map((edge, i) => {
            const fromNode = nodeMap.get(edge.source)
            const toNode = nodeMap.get(edge.target)
            if (!fromNode || !toNode) return null

            const isHighlighted = hoveredId === edge.source || hoveredId === edge.target
            const color = edgeColor(edge.relationship.type)

            // Source exits from right side, target enters from left side (LR layout)
            const x1 = fromNode.x + NODE_WIDTH
            const y1 = fromNode.y + NODE_HEIGHT / 2
            const x2 = toNode.x
            const y2 = toNode.y + NODE_HEIGHT / 2

            // Bezier control points
            const dx = Math.abs(x2 - x1)
            const cpOffset = Math.max(dx * 0.4, 30)
            const cx1 = x1 + cpOffset
            const cy1 = y1
            const cx2 = x2 - cpOffset
            const cy2 = y2

            // Midpoint for label
            const mx = (x1 + x2) / 2
            const my = (y1 + y2) / 2
            const angle = Math.atan2(y2 - y1, x2 - x1) * (180 / Math.PI)

            const dimmedBySearch = isSearchActive && !matchesSearch(edge.source) && !matchesSearch(edge.target)

            return (
              <g key={`edge-${i}`} opacity={dimmedBySearch ? 0.15 : 1}>
                <path
                  d={`M ${x1} ${y1} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${x2} ${y2}`}
                  fill="none"
                  stroke={isHighlighted ? color : 'var(--border)'}
                  strokeWidth={isHighlighted ? 2 : 1}
                  opacity={isHighlighted ? 1 : 0.6}
                  markerEnd={`url(#${arrowMarkerId})`}
                />
                <text
                  className="knowledge-graph-edge-label"
                  x={mx}
                  y={my}
                  textAnchor="middle"
                  dominantBaseline="central"
                  fontSize={8}
                  fontFamily="var(--font-mono)"
                  fill={isHighlighted ? color : 'var(--text-muted)'}
                  transform={`rotate(${Math.abs(angle) > 90 ? angle + 180 : angle}, ${mx}, ${my})`}
                  dy={-6}
                  style={{ pointerEvents: 'none' }}
                >
                  {edge.relationship.type}
                </text>
              </g>
            )
          })}

          {/* Nodes */}
          {nodes.map(node => {
            const color = getEntityColor(node.entity.type)
            const isHovered = hoveredId === node.id
            const dimmedBySearch = isSearchActive && !matchesSearch(node.id)
            const isExpanding = expandingNode === node.id

            return (
              <g
                key={node.id}
                transform={`translate(${node.x}, ${node.y})`}
                onMouseEnter={e => handleNodeMouseEnter(e, node.entity)}
                onMouseLeave={handleNodeMouseLeave}
                onDoubleClick={e => { e.stopPropagation(); handleDoubleClick(node.id) }}
                style={{ cursor: 'pointer' }}
                opacity={dimmedBySearch ? 0.3 : 1}
              >
                {/* Background rect */}
                <rect
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx={6}
                  fill="var(--bg-secondary)"
                  stroke={isHovered ? color : 'var(--border)'}
                  strokeWidth={isHovered ? 2.5 : 1}
                />
                {/* Left color bar */}
                <rect
                  x={0}
                  y={0}
                  width={4}
                  height={NODE_HEIGHT}
                  rx={2}
                  fill={color}
                />
                {/* Entity type label */}
                <text
                  x={12}
                  y={12}
                  fontSize={8}
                  fontFamily="var(--font-mono)"
                  fill="var(--text-muted)"
                  style={{ textTransform: 'uppercase', userSelect: 'none' }}
                >
                  {node.entity.type}
                </text>
                {/* Entity name */}
                <text
                  x={12}
                  y={NODE_HEIGHT - 8}
                  fontSize={11}
                  fontFamily="var(--font-sans)"
                  fill="var(--text-primary)"
                  style={{ userSelect: 'none' }}
                >
                  {truncate(node.entity.name, 18)}
                </text>
                {/* Expanding indicator */}
                {isExpanding && (
                  <circle
                    cx={NODE_WIDTH - 10}
                    cy={NODE_HEIGHT / 2}
                    r={4}
                    fill="none"
                    stroke={color}
                    strokeWidth={1.5}
                    strokeDasharray="6 4"
                  >
                    <animateTransform
                      attributeName="transform"
                      type="rotate"
                      from={`0 ${NODE_WIDTH - 10} ${NODE_HEIGHT / 2}`}
                      to={`360 ${NODE_WIDTH - 10} ${NODE_HEIGHT / 2}`}
                      dur="1s"
                      repeatCount="indefinite"
                    />
                  </circle>
                )}
              </g>
            )
          })}
        </g>
      </svg>

      {/* Tooltip */}
      {tooltip && (
        <div
          style={{
            position: 'absolute',
            left: tooltip.x + 12,
            top: tooltip.y - 8,
            background: 'var(--bg-secondary)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            padding: '6px 10px',
            zIndex: 20,
            fontSize: 'calc(var(--font-size-base) * 0.75)',
            color: 'var(--text-secondary)',
            maxWidth: 260,
            pointerEvents: 'none',
            whiteSpace: 'pre-wrap',
            boxShadow: '0 2px 8px rgba(0,0,0,0.2)',
          }}
        >
          <div style={{ fontWeight: 600, color: 'var(--text-primary)', marginBottom: 2 }}>
            {tooltip.entity.name}
          </div>
          <div style={{
            color: getEntityColor(tooltip.entity.type),
            fontSize: 'calc(var(--font-size-base) * 0.65)',
            textTransform: 'uppercase',
            fontFamily: 'var(--font-mono)',
            marginBottom: 4,
          }}>
            {tooltip.entity.type}
          </div>
          {Object.keys(tooltip.entity.properties).length > 0 && (
            <div style={{ borderTop: '1px solid var(--border)', paddingTop: 4, marginTop: 2 }}>
              {Object.entries(tooltip.entity.properties).slice(0, 6).map(([key, val]) => (
                <div key={key} style={{ display: 'flex', gap: 6, lineHeight: 1.4 }}>
                  <span style={{ color: 'var(--text-muted)', flexShrink: 0 }}>{key}:</span>
                  <span style={{ color: 'var(--text-primary)', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                    {String(val).length > 40 ? String(val).slice(0, 40) + '\u2026' : String(val)}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Controls overlay (top-right) */}
      <div className="knowledge-graph-controls">
        <button className="knowledge-graph-ctrl-btn" onClick={zoomIn} title="Zoom in">+</button>
        <button className="knowledge-graph-ctrl-btn" onClick={zoomOut} title="Zoom out">&minus;</button>
        <button className="knowledge-graph-ctrl-btn" onClick={fitView} title="Fit to view">&#x2318;</button>
        <span className="knowledge-graph-ctrl-label">{Math.round(view.scale * 100)}%</span>
      </div>

      {/* Info overlay (top-left) */}
      <div className="knowledge-graph-info">
        {nodes.length} entities &middot; {edges.length} relationships
      </div>

      {/* Search overlay (below info, top-left) */}
      <div className="knowledge-graph-search">
        <input
          type="text"
          placeholder="Filter entities..."
          value={searchQuery}
          onChange={e => setSearchQuery(e.target.value)}
          style={{
            background: 'var(--bg-primary)',
            border: '1px solid var(--border)',
            borderRadius: 4,
            padding: '3px 8px',
            fontSize: 'calc(var(--font-size-base) * 0.75)',
            color: 'var(--text-primary)',
            outline: 'none',
            width: 150,
            fontFamily: 'var(--font-mono)',
          }}
        />
      </div>

      {/* Legend overlay (bottom-left) */}
      {legendTypes.length > 0 && (
        <div className="knowledge-graph-legend">
          {legendTypes.map(type => (
            <div key={type} className="knowledge-graph-legend-item">
              <span className="knowledge-graph-legend-dot" style={{ backgroundColor: getEntityColor(type) }} />
              {type}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
