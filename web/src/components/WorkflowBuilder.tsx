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
import { nodeTypes, getDefaultData, nodeKindToType, NODE_KIND_META, type BaseNodeData } from './workflow-nodes/nodeTypes'
import { ExpressionEditor } from './workflow-nodes/ExpressionEditor'
import { WorkflowPropertyPanel } from './WorkflowPropertyPanel'
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

export interface WorkflowVariable {
  key: string
  value: string
}

export interface WorkflowRule {
  name: string
  when: string
  action: string
  message: string
}

export interface WorkflowBuilderProps {
  workflowId?: string
  workflowName?: string
  workflowType?: 'workflow' | 'pipeline'
  description?: string
  enabled?: boolean
  priority?: number
  sources?: string[] | null
  variables?: WorkflowVariable[]
  rules?: WorkflowRule[]
  exitCondition?: string
  initialNodes?: Node[]
  initialEdges?: Edge[]
  onBack?: () => void
  onSave?: (nodes: Node[], edges: Edge[], name: string) => void
  onExport?: () => void
  onRun?: () => void
  onSettingsSave?: (settings: WorkflowSettings) => void
}

export interface WorkflowSettings {
  name: string
  description: string
  enabled: boolean
  priority: number
  sources: string[]
  variables: WorkflowVariable[]
  rules: WorkflowRule[]
  exitCondition: string
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
  description: initialDescription = '',
  enabled: initialEnabled = true,
  priority: initialPriority = 0,
  sources: initialSources = null,
  variables: initialVariables = [],
  rules: initialRules = [],
  exitCondition: initialExitCondition = '',
  initialNodes: initNodes = [],
  initialEdges: initEdges = [],
  onBack,
  onSave,
  onExport,
  onRun,
  onSettingsSave,
}: WorkflowBuilderProps) {
  const reactFlowWrapper = useRef<HTMLDivElement>(null)
  const { screenToFlowPosition } = useReactFlow()

  const [nodes, setNodes, onNodesChange] = useNodesState(initNodes)
  const [edges, setEdges, onEdgesChange] = useEdgesState(initEdges)
  const [name, setName] = useState(initialName)
  const [panelCollapsed, setPanelCollapsed] = useState(false)
  const [showSettings, setShowSettings] = useState(false)

  // Settings state
  const [settingsDesc, setSettingsDesc] = useState(initialDescription)
  const [settingsEnabled, setSettingsEnabled] = useState(initialEnabled)
  const [settingsPriority, setSettingsPriority] = useState(initialPriority)
  const [settingsSources, setSettingsSources] = useState(initialSources?.join(', ') ?? '')
  const [settingsVariables, setSettingsVariables] = useState<WorkflowVariable[]>(initialVariables)
  const [settingsRules, setSettingsRules] = useState<WorkflowRule[]>(initialRules)
  const [settingsExitCondition, setSettingsExitCondition] = useState(initialExitCondition)

  // Find the currently selected node
  const selectedNode = useMemo(
    () => (nodes.find((n) => n.selected) as Node<BaseNodeData> | undefined) ?? null,
    [nodes],
  )

  // Update node data from property panel
  const handleNodeDataChange = useCallback(
    (nodeId: string, data: BaseNodeData) => {
      setNodes((nds) =>
        nds.map((n) => (n.id === nodeId ? { ...n, data } : n)),
      )
    },
    [setNodes],
  )

  const paletteItems = useMemo(() => {
    const items = workflowType === 'pipeline' ? PIPELINE_PALETTE : WORKFLOW_PALETTE
    return [...items, ...COMMON_PALETTE]
  }, [workflowType])

  const onConnect: OnConnect = useCallback(
    (connection: Connection) => {
      setEdges((eds) =>
        addEdge({ ...connection, animated: true, type: 'smoothstep', className: 'edge-transition' }, eds),
      )
    },
    [setEdges],
  )

  const handleSettingsSave = useCallback(() => {
    const sources = settingsSources.split(',').map((s) => s.trim()).filter(Boolean)
    onSettingsSave?.({
      name,
      description: settingsDesc,
      enabled: settingsEnabled,
      priority: settingsPriority,
      sources,
      variables: settingsVariables.filter((v) => v.key.trim()),
      rules: settingsRules.filter((r) => r.name.trim()),
      exitCondition: settingsExitCondition,
    })
    setShowSettings(false)
  }, [name, settingsDesc, settingsEnabled, settingsPriority, settingsSources, settingsVariables, settingsRules, settingsExitCondition, onSettingsSave])

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
        type: nodeKindToType(kind),
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
          <button className="builder-toolbar-btn" title="Settings" onClick={() => setShowSettings(true)}>
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

        {/* Property panel */}
        <WorkflowPropertyPanel
          selectedNode={selectedNode}
          onChange={handleNodeDataChange}
          collapsed={panelCollapsed}
          onToggleCollapse={() => setPanelCollapsed((v) => !v)}
        />
      </div>

      {/* Settings modal */}
      {showSettings && (
        <div className="builder-settings-overlay" onClick={() => setShowSettings(false)}>
          <div className="builder-settings-modal" onClick={(e) => e.stopPropagation()}>
            <h3>Workflow Settings</h3>

            <div className="builder-settings-field">
              <label>Name</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
              />
            </div>

            <div className="builder-settings-field">
              <label>Description</label>
              <textarea
                value={settingsDesc}
                onChange={(e) => setSettingsDesc(e.target.value)}
                rows={3}
                placeholder="Workflow description..."
              />
            </div>

            <div className="builder-settings-field">
              <label>Enabled</label>
              <div className="builder-settings-toggle-row">
                <div
                  className={`builder-settings-toggle-track ${settingsEnabled ? 'builder-settings-toggle-track--on' : ''}`}
                  onClick={() => setSettingsEnabled((v) => !v)}
                >
                  <div className="builder-settings-toggle-knob" />
                </div>
                <span className="builder-settings-toggle-label">
                  {settingsEnabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
            </div>

            <div className="builder-settings-field">
              <label>Priority</label>
              <input
                type="number"
                value={settingsPriority}
                onChange={(e) => setSettingsPriority(Number(e.target.value))}
                min={0}
                max={100}
              />
            </div>

            <div className="builder-settings-field">
              <label>Sources</label>
              <input
                type="text"
                value={settingsSources}
                onChange={(e) => setSettingsSources(e.target.value)}
                placeholder="Comma-separated: cli, api, web"
              />
            </div>

            {/* Variables editor */}
            <div className="builder-settings-field">
              <label>Variables</label>
              <div className="builder-settings-kv-table">
                {settingsVariables.map((v, i) => (
                  <div key={i} className="builder-settings-kv-row">
                    <input
                      type="text"
                      value={v.key}
                      onChange={(e) => {
                        const next = [...settingsVariables]
                        next[i] = { ...next[i], key: e.target.value }
                        setSettingsVariables(next)
                      }}
                      placeholder="key"
                    />
                    <input
                      type="text"
                      value={v.value}
                      onChange={(e) => {
                        const next = [...settingsVariables]
                        next[i] = { ...next[i], value: e.target.value }
                        setSettingsVariables(next)
                      }}
                      placeholder="value"
                    />
                    <button
                      className="builder-settings-kv-remove"
                      onClick={() => setSettingsVariables(settingsVariables.filter((_, j) => j !== i))}
                      title="Remove"
                    >
                      &times;
                    </button>
                  </div>
                ))}
                <button
                  className="builder-settings-add-btn"
                  onClick={() => setSettingsVariables([...settingsVariables, { key: '', value: '' }])}
                >
                  + Add Variable
                </button>
              </div>
            </div>

            {/* Rules editor */}
            <div className="builder-settings-field">
              <label>Rules</label>
              <div className="builder-settings-rules">
                {settingsRules.map((r, i) => (
                  <div key={i} className="builder-settings-rule-card">
                    <div className="builder-settings-rule-header">
                      <input
                        type="text"
                        value={r.name}
                        onChange={(e) => {
                          const next = [...settingsRules]
                          next[i] = { ...next[i], name: e.target.value }
                          setSettingsRules(next)
                        }}
                        placeholder="Rule name"
                      />
                      <button
                        className="builder-settings-kv-remove"
                        onClick={() => setSettingsRules(settingsRules.filter((_, j) => j !== i))}
                        title="Remove rule"
                      >
                        &times;
                      </button>
                    </div>
                    <input
                      type="text"
                      value={r.when}
                      onChange={(e) => {
                        const next = [...settingsRules]
                        next[i] = { ...next[i], when: e.target.value }
                        setSettingsRules(next)
                      }}
                      placeholder="When condition"
                    />
                    <select
                      value={r.action}
                      onChange={(e) => {
                        const next = [...settingsRules]
                        next[i] = { ...next[i], action: e.target.value }
                        setSettingsRules(next)
                      }}
                    >
                      <option value="block">Block</option>
                      <option value="allow">Allow</option>
                      <option value="warn">Warn</option>
                      <option value="require_approval">Require Approval</option>
                    </select>
                    <input
                      type="text"
                      value={r.message}
                      onChange={(e) => {
                        const next = [...settingsRules]
                        next[i] = { ...next[i], message: e.target.value }
                        setSettingsRules(next)
                      }}
                      placeholder="Message"
                    />
                  </div>
                ))}
                <button
                  className="builder-settings-add-btn"
                  onClick={() => setSettingsRules([...settingsRules, { name: '', when: '', action: 'block', message: '' }])}
                >
                  + Add Rule
                </button>
              </div>
            </div>

            {/* Exit condition */}
            <div className="builder-settings-field">
              <label>Exit Condition</label>
              <ExpressionEditor
                value={settingsExitCondition}
                onChange={setSettingsExitCondition}
                placeholder="Expression, e.g. steps.all_complete"
              />
            </div>

            <div className="builder-settings-actions">
              <button className="builder-settings-cancel" onClick={() => setShowSettings(false)}>
                Cancel
              </button>
              <button className="builder-settings-save" onClick={handleSettingsSave}>
                Apply
              </button>
            </div>
          </div>
        </div>
      )}
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
