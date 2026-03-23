import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import ForceGraph3D from 'react-force-graph-3d'
import SpriteText from 'three-spritetext'
import { useCodeGraph, mergeCodeGraphData } from '../../hooks/useCodeGraph'
import type { CodeGraphData, CodeGraphNode, CodeGraphSearchResult } from '../../hooks/useCodeGraph'
import { IS_MOBILE } from '../../utils/platform'
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
      val: 2,
    }
    gn.color = getNodeColor(gn)
    return gn
  })

  const links: GraphLink[] = data.links
    .filter(l => nodeIds.has(l.source) && nodeIds.has(l.target))
    .map(l => ({
      source: l.source,
      target: l.target,
      type: l.type,
      color: EDGE_COLORS[l.type] || '#2a2a3a',
    }))

  return { nodes, links }
}

function edgeColor(relType: string): string {
  return EDGE_COLORS[relType] || 'rgba(120,120,120,0.4)'
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

// ── Component ──────────────────────────────────────────────────

export function CodeGraphExplorer({ projectId }: CodeGraphExplorerProps) {
  // react-force-graph-3d does not export a usable instance type
  const fgRef = useRef<any>(null) // eslint-disable-line @typescript-eslint/no-explicit-any
  const containerRef = useRef<HTMLDivElement>(null)
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 })
  const [graphData, setGraphData] = useState<CodeGraphData>({ nodes: [], links: [] })
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null)
  const [blastMode, setBlastMode] = useState(false)
  const [blastData, setBlastData] = useState<Set<string> | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [searchResults, setSearchResults] = useState<CodeGraphSearchResult[]>([])
  const [isLoading, setIsLoading] = useState(false)
  const [expandedNodes, setExpandedNodes] = useState<Set<string>>(new Set())
  const [webglError, setWebglError] = useState(false)
  const searchDebounceRef = useRef<number | null>(null)

  const { fetchFileGraph, expandFile, expandSymbol, fetchBlastRadius, searchSymbols } = useCodeGraph()

  // WebGL error handling (from KnowledgeGraph pattern)
  useEffect(() => {
    const handleError = (e: ErrorEvent) => {
      const msg = (e.message || '').toLowerCase()
      if (msg.includes('webgl') || msg.includes('three') || msg.includes('context lost')) {
        e.preventDefault()
        setWebglError(true)
      }
    }
    window.addEventListener('error', handleError)
    return () => window.removeEventListener('error', handleError)
  }, [])

  // Clean up search debounce on unmount
  useEffect(() => {
    return () => {
      if (searchDebounceRef.current) clearTimeout(searchDebounceRef.current)
    }
  }, [])

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
    }).catch(e => {
      console.error('CodeGraphExplorer: fetchFileGraph failed', e)
    }).finally(() => {
      setIsLoading(false)
    })
  }, [projectId, fetchFileGraph])

  // Build force data
  const forceData = useMemo(() => buildForceData(graphData), [graphData])

  // Configure forces after data loads
  useEffect(() => {
    const fg = fgRef.current
    if (!fg) return
    fg.d3Force('charge')?.strength(-200)
    fg.d3Force('link')?.distance(80)
    fg.d3Force('center')?.strength(0.05)
    if (IS_MOBILE) {
      try { fg.renderer().setPixelRatio(Math.min(window.devicePixelRatio, 2)) } catch (e) { console.warn('CodeGraphExplorer: setPixelRatio failed', e) }
    }
  }, [forceData])

  // Search
  const searchLower = searchQuery.toLowerCase()
  const isSearchActive = searchQuery.length > 0

  // Node click handler
  const handleNodeClick = useCallback(async (node: any) => {
    if (!projectId) return
    setSelectedNode(node as GraphNode)

    if (blastMode) {
      const opts = node.type === 'file'
        ? { filePath: node.id }
        : { symbolName: node.name }
      const data = await fetchBlastRadius(projectId, opts)
      if (data) {
        const affected = new Set(data.nodes.map((n: any) => n.id))
        setBlastData(affected)
        setGraphData(prev => mergeCodeGraphData(prev, data))
      }
      return
    }

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
    if (!query.trim() || !projectId) { setSearchResults([]); return }
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

    const exists = graphData.nodes.some(n => n.id === result.id)
    if (!exists) {
      const data = await expandSymbol(projectId, result.id)
      if (data) {
        const resultNode: CodeGraphNode = {
          id: result.id, name: result.name,
          type: result.type || result.kind || 'function',
          kind: result.kind, file_path: result.file_path,
        }
        const merged = mergeCodeGraphData({ nodes: [resultNode], links: [] }, data)
        setGraphData(prev => mergeCodeGraphData(prev, merged))
      }
    }

    // Center on node in 3D
    if (fgRef.current) {
      const node = fgRef.current.graphData().nodes.find((n: any) => n.id === result.id)
      if (node) {
        const distance = 200
        const hyp = Math.hypot(node.x, node.y, node.z)
        const distRatio = hyp === 0 ? 1 : 1 + distance / hyp
        fgRef.current.cameraPosition(
          { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
          node, 1000
        )
      }
    }
  }, [projectId, graphData.nodes, expandSymbol])

  // Zoom to fit
  const handleZoomToFit = useCallback(() => {
    fgRef.current?.zoomToFit(400, 40)
  }, [])

  // Toggle blast radius mode
  const toggleBlastMode = useCallback(() => {
    setBlastMode(prev => {
      if (prev) setBlastData(null)
      return !prev
    })
  }, [])

  // 3D node rendering — SpriteText (same pattern as KnowledgeGraph)
  const nodeThreeObject = useCallback((node: any) => {
    try {
      const label = node.type === 'file'
        ? (node.name as string).split('/').pop() || node.name
        : node.name as string
      const color = node.color as string
      const dimmed = blastData ? !blastData.has(node.id) : false
      const searchDimmed = isSearchActive && !label.toLowerCase().includes(searchLower)
      const isDimmed = dimmed || searchDimmed

      const sprite = new SpriteText(label)
      sprite.color = isDimmed ? '#333333' : color
      sprite.fontFace = 'JetBrains Mono, SF Mono, Menlo, monospace'

      if (IS_MOBILE) {
        sprite.textHeight = 2
      } else {
        sprite.textHeight = 3
        sprite.backgroundColor = isDimmed ? 'rgba(20,20,20,0.3)' : 'rgba(10,10,20,0.75)'
        sprite.borderColor = isDimmed ? 'transparent' : color
        sprite.borderWidth = 0.3
        sprite.borderRadius = 3
        sprite.padding = [2, 4] as any
      }
      return sprite
    } catch {
      const fallback = new SpriteText('?')
      fallback.color = '#888'
      fallback.textHeight = 3
      return fallback
    }
  }, [blastData, isSearchActive, searchLower])

  // Link color — must always return a visible color by default
  const linkColor = useCallback((link: any) => {
    const srcId = typeof link.source === 'object' ? link.source.id : link.source
    const tgtId = typeof link.target === 'object' ? link.target.id : link.target

    if (blastData) {
      if (!blastData.has(srcId) || !blastData.has(tgtId)) return 'rgba(60,60,60,0.1)'
    }
    if (isSearchActive) {
      const srcMatch = String(srcId).toLowerCase().includes(searchLower)
      const tgtMatch = String(tgtId).toLowerCase().includes(searchLower)
      if (!srcMatch && !tgtMatch) return 'rgba(60,60,60,0.15)'
    }
    return link.color || edgeColor(link.type) || 'rgba(120,120,120,0.4)'
  }, [blastData, isSearchActive, searchLower])

  const linkLabel = useCallback((link: any) => link.type as string, [])

  if (!projectId) {
    return (
      <div className="code-graph-empty">
        Select a project to explore its code graph.
      </div>
    )
  }

  if (webglError) {
    return (
      <div className="code-graph-empty">
        WebGL error — your browser may not support 3D rendering.
        Try refreshing the page.
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
          {blastMode ? 'Blast On' : 'Blast Radius'}
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
                <span className="code-graph-search-kind" style={{ color: (r.kind ? NODE_COLORS[r.kind] : undefined) || '#6b7280' }}>
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

      {/* 3D Graph */}
      <ForceGraph3D
        ref={fgRef}
        graphData={forceData}
        width={dimensions.width}
        height={dimensions.height}
        nodeId="id"
        nodeThreeObject={nodeThreeObject}
        nodeThreeObjectExtend={false}
        onNodeClick={handleNodeClick}
        nodeLabel={(node: any) => {
          const name = escapeHtml(String(node.name || ''))
          const parts = [`<b>${name}</b>`]
          if (node.kind) parts.push(`<br/><span style="color:${NODE_COLORS[node.type] || '#6b7280'};text-transform:uppercase;font-size:9px">${escapeHtml(String(node.kind))}</span>`)
          if (node.signature) parts.push(`<br/><span style="color:#e6b450;font-size:9px">${escapeHtml(String(node.signature))}</span>`)
          if (node.file_path && node.type !== 'file') parts.push(`<br/><span style="color:#888;font-size:9px">${escapeHtml(String(node.file_path))}${node.line_start ? ':' + node.line_start : ''}</span>`)
          return `<div style="text-align:center;font-family:monospace;font-size:11px;line-height:1.4">${parts.join('')}</div>`
        }}
        linkSource="source"
        linkTarget="target"
        linkColor={linkColor}
        linkLabel={linkLabel}
        linkWidth={0.5}
        linkOpacity={0.6}
        linkDirectionalArrowLength={IS_MOBILE ? 0 : 3}
        linkDirectionalArrowRelPos={1}
        linkDirectionalParticles={IS_MOBILE ? 0 : 2}
        linkDirectionalParticleSpeed={0.004}
        linkDirectionalParticleWidth={0.8}
        linkDirectionalParticleColor={linkColor}
        backgroundColor="rgba(0,0,0,0)"
        showNavInfo={false}
        enableNodeDrag={true}
        {...(IS_MOBILE ? { rendererConfig: { antialias: false, powerPreference: 'low-power' as const } } : {})}
      />
    </div>
  )
}
