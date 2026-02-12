import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import ForceGraph3D from 'react-force-graph-3d'
import SpriteText from 'three-spritetext'
import type { KnowledgeGraphData, KnowledgeEntity, KnowledgeRelationship } from '../hooks/useMemory'

interface KnowledgeGraphProps {
  fetchKnowledgeGraph: (limit?: number) => Promise<KnowledgeGraphData | null>
  fetchEntityNeighbors: (name: string) => Promise<KnowledgeGraphData | null>
}

interface GraphNode {
  id: string
  name: string
  type: string
  entity: KnowledgeEntity
  color: string
  val: number // node size
}

interface GraphLink {
  source: string
  target: string
  type: string
  color: string
}

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
  return ENTITY_TYPE_COLORS[type.toLowerCase()] || '#8b8b8b'
}

function hashToHue(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = str.charCodeAt(i) + ((hash << 5) - hash)
  }
  return Math.abs(hash) % 360
}

function edgeColor(relType: string): string {
  const hue = hashToHue(relType)
  return `hsl(${hue}, 45%, 50%)`
}

function mergeGraphData(
  existing: KnowledgeGraphData,
  incoming: KnowledgeGraphData
): KnowledgeGraphData {
  const entityMap = new Map(existing.entities.map(e => [e.name, e]))
  for (const e of incoming.entities) {
    if (!entityMap.has(e.name)) entityMap.set(e.name, e)
  }

  const edgeKey = (r: KnowledgeRelationship) => `${r.source}|${r.type}|${r.target}`
  const edgeSet = new Set(existing.relationships.map(edgeKey))
  const merged = [...existing.relationships]
  for (const r of incoming.relationships) {
    if (!edgeSet.has(edgeKey(r))) {
      edgeSet.add(edgeKey(r))
      merged.push(r)
    }
  }

  return { entities: [...entityMap.values()], relationships: merged }
}

function buildForceData(data: KnowledgeGraphData): { nodes: GraphNode[]; links: GraphLink[] } {
  const entityNames = new Set(data.entities.map(e => e.name))

  const nodes: GraphNode[] = data.entities.map(e => ({
    id: e.name,
    name: e.name,
    type: e.type,
    entity: e,
    color: getEntityColor(e.type),
    val: 2,
  }))

  const links: GraphLink[] = data.relationships
    .filter(r => entityNames.has(r.source) && entityNames.has(r.target))
    .map(r => ({
      source: r.source,
      target: r.target,
      type: r.type,
      color: edgeColor(r.type),
    }))

  return { nodes, links }
}

export function KnowledgeGraph({ fetchKnowledgeGraph, fetchEntityNeighbors }: KnowledgeGraphProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const fgRef = useRef<any>(null) // eslint-disable-line @typescript-eslint/no-explicit-any
  const [graphData, setGraphData] = useState<KnowledgeGraphData | null>(null)
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [expandingNode, setExpandingNode] = useState<string | null>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [animateIdle, setAnimateIdle] = useState(() => {
    try { return localStorage.getItem('gobby-kg-animate') === 'true' } catch { return false }
  })

  // Track container size
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const observer = new ResizeObserver(entries => {
      for (const entry of entries) {
        setDimensions({
          width: entry.contentRect.width,
          height: entry.contentRect.height,
        })
      }
    })
    observer.observe(container)
    return () => observer.disconnect()
  }, [])

  // Persist animation toggle
  const toggleAnimate = useCallback(() => {
    setAnimateIdle(prev => {
      const next = !prev
      try { localStorage.setItem('gobby-kg-animate', String(next)) } catch { /* noop */ }
      return next
    })
  }, [])

  // Auto-rotation via OrbitControls
  useEffect(() => {
    const controls = fgRef.current?.controls() as any // eslint-disable-line @typescript-eslint/no-explicit-any
    if (!controls) return
    controls.autoRotate = animateIdle
    controls.autoRotateSpeed = 0.4
  }, [animateIdle])

  // Initial data fetch
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    fetchKnowledgeGraph().then(data => {
      if (!cancelled && data) setGraphData(data)
      if (!cancelled) setLoading(false)
    })
    return () => { cancelled = true }
  }, [fetchKnowledgeGraph])

  // Build force graph data
  const forceData = useMemo(() => {
    if (!graphData) return { nodes: [], links: [] }
    return buildForceData(graphData)
  }, [graphData])

  // Search
  const searchLower = searchQuery.toLowerCase()
  const isSearchActive = searchQuery.length > 0

  // Node click: expand neighbors
  const handleNodeClick = useCallback((node: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
    if (expandingNode) return
    const name = node.id as string
    setExpandingNode(name)
    fetchEntityNeighbors(name).then(data => {
      if (data && graphData) {
        setGraphData(mergeGraphData(graphData, data))
      }
      setExpandingNode(null)
    }).catch(() => setExpandingNode(null))
  }, [fetchEntityNeighbors, graphData, expandingNode])

  // Custom node rendering with three-spritetext
  const nodeThreeObject = useCallback((node: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
    const label = node.name as string
    const color = node.color as string
    const dimmed = isSearchActive && !label.toLowerCase().includes(searchLower)

    const sprite = new SpriteText(label)
    sprite.color = dimmed ? '#444444' : color
    sprite.textHeight = 3
    sprite.fontFace = 'SF Mono, Menlo, monospace'
    sprite.backgroundColor = dimmed ? 'rgba(20,20,20,0.3)' : 'rgba(20,20,30,0.75)'
    sprite.borderColor = dimmed ? 'transparent' : color
    sprite.borderWidth = 0.3
    sprite.borderRadius = 3
    sprite.padding = [2, 4] as any // eslint-disable-line @typescript-eslint/no-explicit-any
    return sprite
  }, [isSearchActive, searchLower])

  // Link styling
  const linkColor = useCallback((link: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
    if (isSearchActive) {
      const srcId = typeof link.source === 'object' ? link.source.id : link.source
      const tgtId = typeof link.target === 'object' ? link.target.id : link.target
      const srcMatch = String(srcId).toLowerCase().includes(searchLower)
      const tgtMatch = String(tgtId).toLowerCase().includes(searchLower)
      if (!srcMatch && !tgtMatch) return 'rgba(60,60,60,0.15)'
    }
    return link.color || 'rgba(120,120,120,0.4)'
  }, [isSearchActive, searchLower])

  const linkLabel = useCallback((link: any) => link.type as string, []) // eslint-disable-line @typescript-eslint/no-explicit-any

  // Node breathing effect when animating (always pass callback to avoid prop change re-renders)
  const animateRef = useRef(animateIdle)
  animateRef.current = animateIdle
  const nodePositionUpdate = useCallback((obj: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
    if (!animateRef.current) {
      obj.scale.set(1, 1, 1)
      return
    }
    const t = performance.now() * 0.001
    const offset = (obj.id % 100) * 0.1
    const scale = 1 + Math.sin(t * 1.5 + offset) * 0.06
    obj.scale.set(scale, scale, scale)
  }, [])

  // Legend types
  const legendTypes = useMemo(() => {
    if (!graphData) return []
    return [...new Set(graphData.entities.map(e => e.type.toLowerCase()))]
  }, [graphData])

  // Loading state
  if (loading) {
    return (
      <div className="knowledge-graph-container" ref={containerRef}>
        <div className="knowledge-graph-empty">Loading knowledge graph...</div>
      </div>
    )
  }

  // Empty state
  if (!graphData || graphData.entities.length === 0) {
    return (
      <div className="knowledge-graph-container" ref={containerRef}>
        <div className="knowledge-graph-empty">
          <div>No entities found</div>
          <div style={{ fontSize: 'calc(var(--font-size-base) * 0.8)', marginTop: 4 }}>
            Connect a Neo4j instance to explore knowledge graph entities and relationships.
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="knowledge-graph-container" ref={containerRef}>
      <ForceGraph3D
        ref={fgRef}
        width={dimensions.width}
        height={dimensions.height}
        graphData={forceData}
        nodeId="id"
        nodeLabel={(node: any) => { // eslint-disable-line @typescript-eslint/no-explicit-any
          const e = node.entity as KnowledgeEntity
          const props = Object.entries(e.properties || {}).slice(0, 4)
            .map(([k, v]) => `${k}: ${String(v).slice(0, 30)}`)
            .join('\n')
          return `<div style="text-align:center;font-family:monospace;font-size:11px;line-height:1.4">
            <b>${e.name}</b><br/>
            <span style="color:${getEntityColor(e.type)};text-transform:uppercase;font-size:9px">${e.type}</span>
            ${props ? '<br/><span style="color:#888;font-size:9px">' + props.replace(/\n/g, '<br/>') + '</span>' : ''}
          </div>`
        }}
        nodeThreeObject={nodeThreeObject}
        nodeThreeObjectExtend={false}
        onNodeClick={handleNodeClick}
        linkSource="source"
        linkTarget="target"
        linkLabel={linkLabel}
        linkColor={linkColor}
        linkWidth={0.5}
        linkOpacity={0.6}
        linkDirectionalArrowLength={3}
        linkDirectionalArrowRelPos={1}
        linkDirectionalParticles={animateIdle ? 2 : 0}
        linkDirectionalParticleSpeed={0.004}
        linkDirectionalParticleWidth={0.8}
        linkDirectionalParticleColor={linkColor}
        nodePositionUpdate={nodePositionUpdate}
        backgroundColor="rgba(0,0,0,0)"
        showNavInfo={false}
        enableNodeDrag={true}
      />

      {/* Expanding indicator */}
      {expandingNode && (
        <div className="knowledge-graph-info" style={{ top: 36, color: 'var(--accent)' }}>
          Expanding {expandingNode}...
        </div>
      )}

      {/* Info overlay (top-left) */}
      <div className="knowledge-graph-info">
        {forceData.nodes.length} entities &middot; {forceData.links.length} relationships
      </div>

      {/* Search overlay */}
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

      {/* Controls (top-right) */}
      <div className="knowledge-graph-controls">
        <button
          className={`knowledge-graph-ctrl-btn${animateIdle ? ' active' : ''}`}
          onClick={toggleAnimate}
          title={animateIdle ? 'Pause idle animation' : 'Animate when idle'}
        >
          {animateIdle ? (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <rect x="6" y="4" width="4" height="16" rx="1" />
              <rect x="14" y="4" width="4" height="16" rx="1" />
            </svg>
          ) : (
            <svg width="14" height="14" viewBox="0 0 24 24" fill="currentColor">
              <path d="M8 5v14l11-7z" />
            </svg>
          )}
        </button>
      </div>
    </div>
  )
}
