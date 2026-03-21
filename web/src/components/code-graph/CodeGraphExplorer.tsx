import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import ForceGraph2D from 'react-force-graph-2d'
import { useCodeGraph, mergeCodeGraphData } from '../../hooks/useCodeGraph'
import type { CodeGraphData, CodeGraphNode, CodeGraphLink } from '../../hooks/useCodeGraph'
import './CodeGraphExplorer.css'

interface CodeGraphExplorerProps {
  projectId: string | null
}

// ── GitNexus-inspired node colors ──────────────────────────────

const NODE_COLORS: Record<string, string> = {
  file: '#3b82f6',
  folder: '#6366f1',
  class: '#f59e0b',
  function: '#10b981',
  method: '#14b8a6',
  interface: '#ec4899',
  module: '#8b5cf6',
  constant: '#f97316',
  variable: '#64748b',
  type: '#a78bfa',
}

const NODE_SIZES: Record<string, number> = {
  file: 6, folder: 10, class: 8, function: 4,
  method: 3, interface: 7, module: 13, constant: 2,
  variable: 2, type: 3,
}

const EDGE_COLORS: Record<string, string> = {
  CALLS: '#7c3aed',
  IMPORTS: '#1d4ed8',
  DEFINES: '#0e7490',
}

const BLAST_COLORS = ['#ef4444', '#f97316', '#eab308', '#a3e635']

function getNodeColor(node: GraphNode): string {
  if (node.blast_distance !== undefined && node.blast_distance >= 0) {
    const idx = Math.min(node.blast_distance, BLAST_COLORS.length - 1)
    return BLAST_COLORS[idx]
  }
  return NODE_COLORS[node.type] || '#6b7280'
}

function getNodeSize(node: GraphNode): number {
  return NODE_SIZES[node.type] || 4
}

// ── Force graph data types ─────────────────────────────────────

interface GraphNode {
  id: string
  name: string
  type: string
  kind?: string
  file_path?: string
  line_start?: number
  signature?: string
  symbol_count?: number
  blast_distance?: number
  color: string
  val: number
}

interface GraphLink {
  source: string
  target: string
  type: string
  color: string
  curvature: number
  line?: number
}

function buildForceData(data: CodeGraphData): { nodes: GraphNode[]; links: GraphLink[] } {
  const nodeIds = new Set(data.nodes.map(n => n.id))

  const nodes: GraphNode[] = data.nodes.map(n => {
    const gn: GraphNode = {
      id: n.id,
      name: n.name,
      type: n.type,
      kind: n.kind,
      file_path: n.file_path,
      line_start: n.line_start,
      signature: n.signature,
      symbol_count: n.symbol_count,
      blast_distance: n.blast_distance,
      color: '',
      val: 0,
    }
    gn.color = getNodeColor(gn)
    gn.val = getNodeSize(gn)
    return gn
  })

  const links: GraphLink[] = data.links
    .filter(l => nodeIds.has(l.source) && nodeIds.has(l.target))
    .map(l => ({
      source: l.source,
      target: l.target,
      type: l.type,
      color: EDGE_COLORS[l.type] || '#2a2a3a',
      curvature: 0.12 + Math.random() * 0.08,
      line: l.line,
    }))

  return { nodes, links }
}

// ── Component ──────────────────────────────────────────────────

export function CodeGraphExplorer({ projectId }: CodeGraphExplorerProps) {
  const graphRef = useRef<any>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [graphData, setGraphData] = useState<CodeGraphData>({ nodes: [], links: [] })
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [blastMode, setBlastMode] = useState(false)
  const [blastData, setBlastData] = useState<Set<string> | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<any[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set())
  const searchDebounceRef = useRef<number | null>(null)

  const { fetchFileGraph, expandFile, expandSymbol, fetchBlastRadius, searchSymbols } = useCodeGraph()

  // Resize observer
  useEffect(() => {
    const container = containerRef.current
    if (!container) return

    const ro = new ResizeObserver(entries => {
      const { width, height } = entries[0].contentRect
      setDimensions({ width, height })
    })
    ro.observe(container)
    return () => ro.disconnect()
  }, [])

  // Initial load
  useEffect(() => {
    if (!projectId) return
    setIsLoading(true)
    fetchFileGraph(projectId).then(data => {
      if (data) setGraphData(data)
      setIsLoading(false)
    })
  }, [projectId, fetchFileGraph])

  // Build force data
  const forceData = useMemo(() => buildForceData(graphData), [graphData])

  // Node click handler
  const handleNodeClick = useCallback(async (node: GraphNode) => {
    if (!projectId) return
    setSelectedNode(node)

    if (blastMode) {
      // Blast radius mode: fetch and highlight
      const opts = node.type === 'file'
        ? { filePath: node.id }
        : { symbolName: node.name }
      const data = await fetchBlastRadius(projectId, opts)
      if (data) {
        const affected = new Set(data.nodes.map(n => n.id))
        setBlastData(affected)
        // Merge blast radius nodes into graph
        setGraphData(prev => mergeCodeGraphData(prev, data))
      }
      return
    }

    // Normal mode: expand on click
    if (expandedNodes.has(node.id)) return
    setExpandedNodes(prev => new Set(prev).add(node.id))

    let newData: CodeGraphData | null = null
    if (node.type === 'file') {
      newData = await expandFile(projectId, node.id)
    } else {
      newData = await expandSymbol(projectId, node.id)
    }

    if (newData) {
      setGraphData(prev => mergeCodeGraphData(prev, newData!))
    }
  }, [projectId, blastMode, expandedNodes, fetchBlastRadius, expandFile, expandSymbol])

  // Search handler
  const handleSearch = useCallback((query: string) => {
    setSearchQuery(query)
    if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current)

    if (!query.trim() || !projectId) {
      setSearchResults([])
      return
    }

    searchDebounceRef.current = window.setTimeout(async () => {
      const results = await searchSymbols(projectId, query)
      setSearchResults(results)
    }, 300)
  }, [projectId, searchSymbols])

  // Search result click
  const handleSearchResultClick = useCallback(async (result: any) => {
    if (!projectId) return
    setSearchQuery('')
    setSearchResults([])

    // Check if node exists in graph already
    const exists = graphData.nodes.some(n => n.id === result.id)
    if (!exists) {
      // Expand the symbol to add it
      const data = await expandSymbol(projectId, result.id)
      if (data) {
        // Also add the result node itself
        const resultNode: CodeGraphNode = {
          id: result.id,
          name: result.name,
          type: result.type || result.kind || 'function',
          kind: result.kind,
          file_path: result.file_path,
          line_start: result.line_start,
          signature: result.signature,
        }
        const merged = mergeCodeGraphData(
          { nodes: [resultNode], links: [] },
          data
        )
        setGraphData(prev => mergeCodeGraphData(prev, merged))
      }
    }

    // Center on node
    if (graphRef.current) {
      const node = graphRef.current.graphData().nodes.find((n: any) => n.id === result.id)
      if (node) {
        graphRef.current.centerAt(node.x, node.y, 400)
        graphRef.current.zoom(3, 400)
      }
    }
  }, [projectId, graphData.nodes, expandSymbol])

  // Zoom to fit
  const handleZoomToFit = useCallback(() => {
    graphRef.current?.zoomToFit(400, 40)
  }, [])

  // Toggle blast radius mode
  const toggleBlastMode = useCallback(() => {
    setBlastMode(prev => !prev)
    if (blastMode) {
      setBlastData(null)
    }
  }, [blastMode])

  // Canvas node renderer
  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const isSelected = selectedNode?.id === node.id
    const isBlastAffected = blastData ? blastData.has(node.id) : true
    const isDimmed = (blastData && !isBlastAffected) || false

    const size = (node.val || 4) * (isSelected ? 1.8 : 1)
    const alpha = isDimmed ? 0.1 : 1

    ctx.save()
    ctx.globalAlpha = alpha

    if (node.type === 'file') {
      // Rounded rectangle for files
      const w = size * 3
      const h = size * 2
      const r = 3
      ctx.beginPath()
      ctx.moveTo(node.x - w / 2 + r, node.y - h / 2)
      ctx.lineTo(node.x + w / 2 - r, node.y - h / 2)
      ctx.quadraticCurveTo(node.x + w / 2, node.y - h / 2, node.x + w / 2, node.y - h / 2 + r)
      ctx.lineTo(node.x + w / 2, node.y + h / 2 - r)
      ctx.quadraticCurveTo(node.x + w / 2, node.y + h / 2, node.x + w / 2 - r, node.y + h / 2)
      ctx.lineTo(node.x - w / 2 + r, node.y + h / 2)
      ctx.quadraticCurveTo(node.x - w / 2, node.y + h / 2, node.x - w / 2, node.y + h / 2 - r)
      ctx.lineTo(node.x - w / 2, node.y - h / 2 + r)
      ctx.quadraticCurveTo(node.x - w / 2, node.y - h / 2, node.x - w / 2 + r, node.y - h / 2)
      ctx.closePath()
      ctx.fillStyle = node.color
      ctx.fill()
    } else {
      // Circle for symbols
      ctx.beginPath()
      ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
      ctx.fillStyle = node.color
      ctx.fill()
    }

    // Glow ring on selection
    if (isSelected) {
      ctx.beginPath()
      ctx.arc(node.x, node.y, size + 4, 0, 2 * Math.PI)
      ctx.strokeStyle = node.color
      ctx.globalAlpha = 0.3
      ctx.lineWidth = 2
      ctx.stroke()
      ctx.globalAlpha = alpha
    }

    // Label
    if (globalScale > 1.2 || isSelected || node.type === 'file') {
      const label = node.type === 'file'
        ? node.name.split('/').pop() || node.name
        : node.name
      const fontSize = Math.max(10 / globalScale, 2)
      ctx.font = `500 ${fontSize}px "JetBrains Mono", "SF Mono", monospace`
      ctx.textAlign = 'center'
      ctx.textBaseline = 'top'
      ctx.fillStyle = '#e5e5e5'
      ctx.globalAlpha = isDimmed ? 0.1 : 0.9
      ctx.fillText(label, node.x, node.y + size + 2)
    }

    ctx.restore()
  }, [selectedNode, blastData])

  // Link canvas renderer
  const linkCanvasObject = useCallback((link: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
    const isDimmed = blastData && !(blastData.has(link.source.id) && blastData.has(link.target.id))

    ctx.save()
    ctx.globalAlpha = isDimmed ? 0.05 : 0.6
    ctx.strokeStyle = link.color || '#2a2a3a'
    ctx.lineWidth = link.type === 'DEFINES' ? 0.5 : 1

    // Curved path
    const dx = link.target.x - link.source.x
    const dy = link.target.y - link.source.y
    const cx = (link.source.x + link.target.x) / 2 - dy * (link.curvature || 0.15)
    const cy = (link.source.y + link.target.y) / 2 + dx * (link.curvature || 0.15)

    ctx.beginPath()
    ctx.moveTo(link.source.x, link.source.y)
    ctx.quadraticCurveTo(cx, cy, link.target.x, link.target.y)

    if (link.type === 'DEFINES') {
      ctx.setLineDash([2, 3])
    }
    ctx.stroke()
    ctx.setLineDash([])

    // Arrow for CALLS
    if (link.type === 'CALLS' && globalScale > 0.8) {
      const angle = Math.atan2(link.target.y - cy, link.target.x - cx)
      const arrowLen = 4
      ctx.beginPath()
      ctx.moveTo(link.target.x, link.target.y)
      ctx.lineTo(
        link.target.x - arrowLen * Math.cos(angle - Math.PI / 6),
        link.target.y - arrowLen * Math.sin(angle - Math.PI / 6)
      )
      ctx.moveTo(link.target.x, link.target.y)
      ctx.lineTo(
        link.target.x - arrowLen * Math.cos(angle + Math.PI / 6),
        link.target.y - arrowLen * Math.sin(angle + Math.PI / 6)
      )
      ctx.stroke()
    }

    ctx.restore()
  }, [blastData])

  // Hover tooltip
  const nodeLabel = useCallback((node: any) => {
    const parts = [node.name]
    if (node.kind && node.kind !== node.type) parts.push(`(${node.kind})`)
    if (node.signature) parts.push(`\n${node.signature}`)
    if (node.file_path && node.type !== 'file') parts.push(`\n${node.file_path}${node.line_start ? `:${node.line_start}` : ''}`)
    if (node.symbol_count) parts.push(`\n${node.symbol_count} symbols`)
    return parts.join('')
  }, [])

  if (!projectId) {
    return (
      <div className="code-graph-empty">
        Select a project to explore its code graph.
      </div>
    )
  }

  return (
    <div className="code-graph-explorer" ref={containerRef}>
      {/* Controls */}
      <div className="code-graph-controls">
        <button
          className={`code-graph-btn ${blastMode ? 'active' : ''}`}
          onClick={toggleBlastMode}
          title="Blast Radius Mode"
        >
          {blastMode ? '💥 Blast On' : 'Blast Radius'}
        </button>
        <button className="code-graph-btn" onClick={handleZoomToFit} title="Zoom to Fit">
          Fit
        </button>
      </div>

      {/* Search */}
      <div className="code-graph-search">
        <input
          type="text"
          placeholder="Search symbols..."
          value={searchQuery}
          onChange={e => handleSearch(e.target.value)}
          className="code-graph-search-input"
        />
        {searchResults.length > 0 && (
          <div className="code-graph-search-results">
            {searchResults.map(r => (
              <button
                key={r.id}
                className="code-graph-search-result"
                onClick={() => handleSearchResultClick(r)}
              >
                <span className="code-graph-search-kind" style={{ color: NODE_COLORS[r.kind] || '#6b7280' }}>
                  {r.kind || r.type}
                </span>
                <span className="code-graph-search-name">{r.name}</span>
                {r.file_path && (
                  <span className="code-graph-search-path">{r.file_path}</span>
                )}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Info overlay */}
      <div className="code-graph-info">
        {forceData.nodes.length} nodes &middot; {forceData.links.length} edges
        {isLoading && ' (loading...)'}
      </div>

      {/* Legend */}
      <div className="code-graph-legend">
        {Object.entries(NODE_COLORS).slice(0, 7).map(([type, color]) => (
          <div key={type} className="code-graph-legend-item">
            <span className="code-graph-legend-dot" style={{ background: color }} />
            <span>{type}</span>
          </div>
        ))}
        <div className="code-graph-legend-separator" />
        {Object.entries(EDGE_COLORS).map(([type, color]) => (
          <div key={type} className="code-graph-legend-item">
            <span className="code-graph-legend-line" style={{ background: color }} />
            <span>{type.toLowerCase()}</span>
          </div>
        ))}
      </div>

      {/* Detail panel */}
      {selectedNode && (
        <div className="code-graph-detail">
          <div className="code-graph-detail-header">
            <span className="code-graph-detail-type" style={{ color: NODE_COLORS[selectedNode.type] || '#6b7280' }}>
              {selectedNode.type}
            </span>
            <button className="code-graph-detail-close" onClick={() => setSelectedNode(null)}>&times;</button>
          </div>
          <div className="code-graph-detail-name">{selectedNode.name}</div>
          {selectedNode.signature && (
            <div className="code-graph-detail-sig">{selectedNode.signature}</div>
          )}
          {selectedNode.file_path && selectedNode.type !== 'file' && (
            <div className="code-graph-detail-path">
              {selectedNode.file_path}{selectedNode.line_start ? `:${selectedNode.line_start}` : ''}
            </div>
          )}
          {selectedNode.symbol_count !== undefined && (
            <div className="code-graph-detail-meta">{selectedNode.symbol_count} symbols</div>
          )}
        </div>
      )}

      {/* Graph */}
      <ForceGraph2D
        ref={graphRef}
        graphData={forceData}
        width={dimensions.width}
        height={dimensions.height}
        nodeCanvasObject={nodeCanvasObject}
        nodePointerAreaPaint={(node: any, color, ctx) => {
          const size = (node.val || 4) * 2
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(node.x, node.y, size, 0, 2 * Math.PI)
          ctx.fill()
        }}
        linkCanvasObject={linkCanvasObject}
        onNodeClick={handleNodeClick}
        nodeLabel={nodeLabel}
        backgroundColor="transparent"
        d3AlphaDecay={0.02}
        d3VelocityDecay={0.3}
        cooldownTicks={100}
        linkDirectionalParticles={(link: any) => link.type === 'CALLS' ? 2 : 0}
        linkDirectionalParticleWidth={2}
        linkDirectionalParticleColor={(link: any) => link.color}
        enableNodeDrag={true}
        enableZoomInteraction={true}
        enablePanInteraction={true}
      />
    </div>
  )
}
