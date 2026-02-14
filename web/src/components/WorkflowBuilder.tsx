import { useState, useCallback, useRef, useMemo, type DragEvent } from 'react'
import {
  ReactFlow,
  useNodesState,
  useEdgesState,
  useReactFlow,
  ReactFlowProvider,
  Controls,
  MiniMap,
  Background,
  Panel,
  addEdge,
  ConnectionLineType,
  BackgroundVariant,
  type Node,
  type Edge,
  type Connection,
  type OnConnect,
} from '@xyflow/react'
import '@xyflow/react/dist/style.css'
import { nodeTypes, getDefaultData, NODE_KIND_META } from './workflow-nodes/nodeTypes'
import './WorkflowBuilder.css'

// ---------------------------------------------------------------------------
// Palette definitions (derived from node kind metadata)
// ---------------------------------------------------------------------------

interface PaletteItem {
  nodeKind: string
  label: string
  description: string
}

const WORKFLOW_PALETTE: PaletteItem[] = ['step', 'trigger-group', 'observer', 'exit-condition']
  .map((k) => ({ nodeKind: k, label: NODE_KIND_META[k].label, description: NODE_KIND_META[k].description }))

const PIPELINE_PALETTE: PaletteItem[] = ['exec', 'prompt', 'mcp', 'pipeline', 'spawn-session', 'approval']
  .map((k) => ({ nodeKind: k, label: NODE_KIND_META[k].label, description: NODE_KIND_META[k].description }))

const COMMON_PALETTE: PaletteItem[] = ['variable', 'rule']
  .map((k) => ({ nodeKind: k, label: NODE_KIND_META[k].label, description: NODE_KIND_META[k].description }))

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface WorkflowBuilderProps {
  workflowId?: string
  workflowName?: string
  workflowType?: 'workflow' | 'pipeline'
  initialNodes?: Node[]
  initialEdges?: Edge[]
  onBack?: () => void
  onSave?: (nodes: Node[], edges: Edge[], name: string) => void
  onExport?: () => void
  onRun?: () => void
}

// ---------------------------------------------------------------------------
// Inner component (needs ReactFlowProvider ancestor)
// ---------------------------------------------------------------------------

let nodeId = 0
function getNextId() {
  return `node_${++nodeId}`
}

function WorkflowBuilderInner({
  workflowName: initialName = 'Untitled',
  workflowType = 'workflow',
  initialNodes: initNodes = [],
  initialEdges: initEdges = [],
  onBack,
  onSave,
  onExport,
  onRun,
}: WorkflowBuilderProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const { screenToFlowPosition } = useReactFlow()

  const [nodes, setNodes, onNodesChange] = useNodesState(initNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initEdges)
  const [name, setName] = useState(initialName)

  const paletteItems = useMemo(() => {
    const items = workflowType === 'pipeline' ? PIPELINE_PALETTE : WORKFLOW_PALETTE
    return [...items, ...COMMON_PALETTE]
  }, [workflowType])

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge({ ...connection, animated: true, type: 'smoothstep' }, eds),
      )
    },
    [setEdges],
  )

  // -- Drag & drop from palette --

  const onDragOver = useCallback((event: DragEvent<HTMLDivElement>) => {
    event.preventDefault()
    event.dataTransfer.dropEffect = 'move'
  }, [])

  const onDrop = useCallback(
    (event: DragEvent<HTMLDivElement>) => {
      event.preventDefault()

      const kind = event.dataTransfer.getData('application/reactflow-kind')
      if (!kind) return

      const position = screenToFlowPosition({
        x: event.clientX,
        y: event.clientY,
      })

      const newNode: Node = {
        id: getNextId(),
        type: 'step',
        position,
        data: getDefaultData(kind),
      }

      setNodes((nds) => [...nds, newNode])
    },
    [screenToFlowPosition, setNodes],
  )

  const onDragStart = useCallback(
    (event: DragEvent<HTMLDivElement>, item: PaletteItem) => {
      event.dataTransfer.setData('application/reactflow-kind', item.nodeKind)
      event.dataTransfer.effectAllowed = 'move'
    },
    [],
  )

  const handleSave = useCallback(() => {
    onSave?.(nodes, edges, name)
  }, [onSave, nodes, edges, name])

  return (
    <div className="builder-layout">
      {/* Toolbar */}
      <div className="builder-toolbar">
        <div className="builder-toolbar-left">
          {onBack && (
            <button className="builder-toolbar-btn" onClick={onBack} title="Back to list">
              &larr;
            </button>
          )}
          <input
            className="builder-name-input"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="Workflow name"
          />
          <span className={`builder-type-badge builder-type-badge--${workflowType}`}>
            {workflowType}
          </span>
        </div>
        <div className="builder-toolbar-right">
          {onSave && (
            <button className="builder-toolbar-btn builder-toolbar-btn--primary" onClick={handleSave}>
              Save
            </button>
          )}
          {onExport && (
            <button className="builder-toolbar-btn" onClick={onExport}>
              Export YAML
            </button>
          )}
          {workflowType === 'pipeline' && onRun && (
            <button className="builder-toolbar-btn builder-toolbar-btn--run" onClick={onRun}>
              Run
            </button>
          )}
          <button className="builder-toolbar-btn" title="Settings">
            &#x2699;
          </button>
        </div>
      </div>

      {/* Main area: sidebar + canvas */}
      <div className="builder-main">
        {/* Palette sidebar */}
        <div className="builder-sidebar">
          <div className="builder-sidebar-header">Palette</div>
          <div className="builder-sidebar-items">
            {paletteItems.map((item) => (
              <div
                key={item.nodeKind}
                className="builder-palette-item"
                draggable
                onDragStart={(e) => onDragStart(e, item)}
              >
                <div className="builder-palette-item-label">{item.label}</div>
                <div className="builder-palette-item-desc">{item.description}</div>
              </div>
            ))}
          </div>
        </div>

        {/* React Flow canvas */}
        <div className="builder-canvas" ref={reactFlowWrapper}>
          <ReactFlow
            nodes={nodes}
            edges={edges}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onDragOver={onDragOver}
            onDrop={onDrop}
            nodeTypes={nodeTypes}
            connectionLineType={ConnectionLineType.SmoothStep}
            fitView
            colorMode="dark"
            defaultEdgeOptions={{ animated: true, type: 'smoothstep' }}
            proOptions={{ hideAttribution: true }}
          >
            <Controls position="bottom-right" />
            <MiniMap
              position="bottom-left"
              pannable
              zoomable
              nodeColor="#3b82f6"
              maskColor="rgba(0,0,0,0.7)"
            />
            <Background variant={BackgroundVariant.Dots} gap={16} size={1} color="#333" />
            <Panel position="top-right">
              <div className="builder-panel-info">
                {nodes.length} node{nodes.length !== 1 ? 's' : ''} &middot;{' '}
                {edges.length} edge{edges.length !== 1 ? 's' : ''}
              </div>
            </Panel>
          </ReactFlow>
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Exported wrapper with ReactFlowProvider
// ---------------------------------------------------------------------------

export function WorkflowBuilder(props: WorkflowBuilderProps) {
  return (
    <ReactFlowProvider>
      <WorkflowBuilderInner {...props} />
    </ReactFlowProvider>
  )
}
