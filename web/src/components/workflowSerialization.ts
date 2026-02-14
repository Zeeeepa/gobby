/**
 * Serialization utilities for converting between workflow/pipeline JSON
 * definitions and React Flow nodes/edges.
 */

import dagre from '@dagrejs/dagre'
import type { Node, Edge } from '@xyflow/react'
import { nodeKindToType } from './workflow-nodes/nodeTypes'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

/** Data attached to every custom node on the canvas. */
export interface StepNodeData extends Record<string, unknown> {
  label: string
  nodeKind: string
  stepIndex: number
  /** Original step data preserved for round-trip. */
  stepData: Record<string, unknown>
}

export type FlowNode = Node<StepNodeData, string>

/** Saved canvas positions keyed by node ID. */
export interface CanvasPositions {
  [nodeId: string]: { x: number; y: number }
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const NODE_WIDTH = 280
const NODE_HEIGHT = 80

// ---------------------------------------------------------------------------
// dagre auto-layout
// ---------------------------------------------------------------------------

export function getLayoutedElements(
  nodes: FlowNode[],
  edges: Edge[],
  direction: 'TB' | 'LR' = 'TB',
): { nodes: FlowNode[]; edges: Edge[] } {
  const g = new dagre.graphlib.Graph()
  g.setDefaultEdgeLabel(() => ({}))
  g.setGraph({ rankdir: direction, nodesep: 50, ranksep: 80 })

  for (const node of nodes) {
    g.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT })
  }

  for (const edge of edges) {
    g.setEdge(edge.source, edge.target)
  }

  dagre.layout(g)

  const layoutedNodes = nodes.map((node) => {
    const pos = g.node(node.id)
    return {
      ...node,
      position: {
        x: pos.x - NODE_WIDTH / 2,
        y: pos.y - NODE_HEIGHT / 2,
      },
    }
  })

  return { nodes: layoutedNodes, edges }
}

// ---------------------------------------------------------------------------
// definitionToFlow — JSON definition -> React Flow nodes/edges
// ---------------------------------------------------------------------------

export function definitionToFlow(
  definition: Record<string, unknown>,
  canvasJson?: string | null,
): { nodes: FlowNode[]; edges: Edge[] } {
  const isPipeline =
    definition.type === 'pipeline' ||
    (Array.isArray(definition.steps) &&
      (definition.steps as Record<string, unknown>[]).some(
        (s) => 'id' in s && !('name' in s),
      ))

  if (isPipeline) {
    return pipelineToFlow(definition, canvasJson)
  }
  return workflowToFlow(definition, canvasJson)
}

function workflowToFlow(
  definition: Record<string, unknown>,
  canvasJson?: string | null,
): { nodes: FlowNode[]; edges: Edge[] } {
  const steps = (definition.steps || []) as Record<string, unknown>[]
  const observers = (definition.observers || []) as Record<string, unknown>[]
  const triggers = (definition.triggers || {}) as Record<string, unknown>
  const exitCondition = definition.exit_condition as string | undefined

  let savedPositions: CanvasPositions | null = null
  if (canvasJson) {
    try {
      savedPositions = JSON.parse(canvasJson) as CanvasPositions
    } catch {
      // ignore invalid canvas JSON
    }
  }

  const nodes: FlowNode[] = []
  const edges: Edge[] = []

  // Map step name -> node ID for edge creation
  const stepIdMap = new Map<string, string>()

  // Steps
  steps.forEach((step, index) => {
    const name = (step.name as string) || `step-${index}`
    const nodeId = `step-${index}`
    stepIdMap.set(name, nodeId)

    nodes.push({
      id: nodeId,
      type: nodeKindToType('step'),
      position: { x: 0, y: 0 },
      data: {
        label: name,
        nodeKind: 'step',
        stepIndex: index,
        stepData: step,
      },
    })
  })

  // Observers
  observers.forEach((obs, index) => {
    const name = (obs.name as string) || `observer-${index}`
    const nodeId = `observer-${index}`

    nodes.push({
      id: nodeId,
      type: nodeKindToType('observer'),
      position: { x: 0, y: 0 },
      data: {
        label: name,
        nodeKind: 'observer',
        stepIndex: -1,
        stepData: obs,
      },
    })
  })

  // Trigger groups
  const triggerKeys = Object.keys(triggers)
  triggerKeys.forEach((key, index) => {
    const nodeId = `trigger-${index}`

    nodes.push({
      id: nodeId,
      type: nodeKindToType('trigger-group'),
      position: { x: 0, y: 0 },
      data: {
        label: key,
        nodeKind: 'trigger-group',
        stepIndex: -1,
        stepData: { name: key, actions: triggers[key] },
      },
    })
  })

  // Exit condition
  if (exitCondition) {
    const nodeId = 'exit-condition-0'
    nodes.push({
      id: nodeId,
      type: nodeKindToType('exit-condition'),
      position: { x: 0, y: 0 },
      data: {
        label: 'Exit Condition',
        nodeKind: 'exit-condition',
        stepIndex: -1,
        stepData: { exit_condition: exitCondition },
      },
    })
  }

  // Edges from step transitions
  steps.forEach((step, index) => {
    const sourceId = `step-${index}`
    const transitions = (step.transitions || []) as Record<string, unknown>[]

    transitions.forEach((tr, trIdx) => {
      const targetName = tr.to as string
      const targetId = stepIdMap.get(targetName)
      if (targetId) {
        const hasCondition = !!(tr.when as string)
        edges.push({
          id: `e-${sourceId}-${targetId}-${trIdx}`,
          source: sourceId,
          target: targetId,
          animated: false,
          type: 'smoothstep',
          label: (tr.when as string) || undefined,
          className: hasCondition ? 'edge-conditional' : 'edge-transition',
          style: hasCondition ? { strokeDasharray: '6 3' } : undefined,
        })
      }
    })

    // If no transitions but there's a next step, create implicit sequential edge
    if (transitions.length === 0 && index < steps.length - 1) {
      const targetId = `step-${index + 1}`
      edges.push({
        id: `e-${sourceId}-${targetId}-implicit`,
        source: sourceId,
        target: targetId,
        animated: true,
        type: 'smoothstep',
        className: 'edge-sequential',
      })
    }
  })

  // Apply saved positions or auto-layout
  if (savedPositions && nodes.every((n) => savedPositions![n.id])) {
    for (const node of nodes) {
      node.position = savedPositions[node.id]
    }
    return { nodes, edges }
  }

  return getLayoutedElements(nodes, edges)
}

function pipelineToFlow(
  definition: Record<string, unknown>,
  canvasJson?: string | null,
): { nodes: FlowNode[]; edges: Edge[] } {
  const steps = (definition.steps || []) as Record<string, unknown>[]

  let savedPositions: CanvasPositions | null = null
  if (canvasJson) {
    try {
      savedPositions = JSON.parse(canvasJson) as CanvasPositions
    } catch {
      // ignore
    }
  }

  const nodes: FlowNode[] = []
  const edges: Edge[] = []

  steps.forEach((step, index) => {
    const id = (step.id as string) || `pstep-${index}`
    const nodeId = `pipeline-${index}`

    // Determine step kind — exec/prompt/mcp take priority over approval
    let nodeKind = 'exec'
    if (step.exec) nodeKind = 'exec'
    else if (step.prompt) nodeKind = 'prompt'
    else if (step.mcp) nodeKind = 'mcp'
    else if (step.invoke_pipeline) nodeKind = 'pipeline'
    else if (step.spawn_session) nodeKind = 'spawn-session'
    else if (step.approval) nodeKind = 'approval'

    nodes.push({
      id: nodeId,
      type: nodeKindToType(nodeKind),
      position: { x: 0, y: 0 },
      data: {
        label: id,
        nodeKind,
        stepIndex: index,
        stepData: step,
      },
    })

    // Sequential edges
    if (index > 0) {
      const prevId = `pipeline-${index - 1}`
      const hasCondition = !!(step.condition as string)
      edges.push({
        id: `e-${prevId}-${nodeId}`,
        source: prevId,
        target: nodeId,
        animated: !hasCondition,
        type: 'smoothstep',
        className: hasCondition ? 'edge-conditional' : 'edge-sequential',
        label: hasCondition ? (step.condition as string) : undefined,
        style: hasCondition ? { strokeDasharray: '6 3' } : undefined,
      })
    }
  })

  // Apply saved positions or auto-layout
  if (savedPositions && nodes.every((n) => savedPositions![n.id])) {
    for (const node of nodes) {
      node.position = savedPositions[node.id]
    }
    return { nodes, edges }
  }

  return getLayoutedElements(nodes, edges)
}

// ---------------------------------------------------------------------------
// flowToDefinition — React Flow nodes/edges -> JSON definition + canvas
// ---------------------------------------------------------------------------

export function flowToDefinition(
  nodes: FlowNode[],
  edges: Edge[],
  isPipeline: boolean,
): { definition: Record<string, unknown>; canvasJson: string } {
  // Save canvas positions
  const positions: CanvasPositions = {}
  for (const node of nodes) {
    positions[node.id] = { x: node.position.x, y: node.position.y }
  }
  const canvasJson = JSON.stringify(positions)

  if (isPipeline) {
    return { definition: flowToPipeline(nodes, edges), canvasJson }
  }
  return { definition: flowToWorkflow(nodes, edges), canvasJson }
}

function flowToWorkflow(
  nodes: FlowNode[],
  edges: Edge[],
): Record<string, unknown> {
  const stepNodes = nodes
    .filter((n) => n.data.nodeKind === 'step')
    .sort((a, b) => a.data.stepIndex - b.data.stepIndex)

  const observerNodes = nodes.filter((n) => n.data.nodeKind === 'observer')
  const triggerNodes = nodes.filter((n) => n.data.nodeKind === 'trigger-group')
  const exitNodes = nodes.filter((n) => n.data.nodeKind === 'exit-condition')

  // Build node ID -> step name map
  const nodeToStep = new Map<string, string>()
  for (const n of stepNodes) {
    nodeToStep.set(n.id, n.data.label)
  }

  // Build steps with transitions from edges
  const steps = stepNodes.map((node) => {
    const step = { ...node.data.stepData }
    step.name = node.data.label

    // Find outgoing edges that go to other step nodes
    const outEdges = edges.filter(
      (e) => e.source === node.id && nodeToStep.has(e.target),
    )

    // Only include explicit transitions (skip implicit sequential ones)
    const transitions = outEdges
      .filter((e) => !e.id.endsWith('-implicit'))
      .map((e) => {
        const tr: Record<string, unknown> = { to: nodeToStep.get(e.target)! }
        if (e.label) tr.when = e.label
        return tr
      })

    if (transitions.length > 0) {
      step.transitions = transitions
    }

    return step
  })

  // Observers
  const observers = observerNodes.map((n) => ({ ...n.data.stepData }))

  // Triggers
  const triggers: Record<string, unknown> = {}
  for (const n of triggerNodes) {
    const data = n.data.stepData
    triggers[n.data.label] = data.actions
  }

  // Exit condition
  const exitCondition = exitNodes.length > 0
    ? (exitNodes[0].data.stepData.exit_condition as string)
    : undefined

  const result: Record<string, unknown> = { steps }
  if (observers.length > 0) result.observers = observers
  if (Object.keys(triggers).length > 0) result.triggers = triggers
  if (exitCondition) result.exit_condition = exitCondition

  return result
}

function flowToPipeline(
  nodes: FlowNode[],
  _edges: Edge[],
): Record<string, unknown> {
  // Pipeline steps are ordered by stepIndex
  const stepNodes = nodes
    .filter((n) => n.data.stepIndex >= 0)
    .sort((a, b) => a.data.stepIndex - b.data.stepIndex)

  const steps = stepNodes.map((node) => {
    const step = { ...node.data.stepData }
    step.id = node.data.label
    return step
  })

  return { type: 'pipeline', steps }
}
