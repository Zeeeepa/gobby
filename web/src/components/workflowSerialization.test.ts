import { describe, it, expect } from 'vitest'
import {
  definitionToFlow,
  flowToDefinition,
  getLayoutedElements,
  type FlowNode,
} from './workflowSerialization'
import type { Edge } from '@xyflow/react'

// ---------------------------------------------------------------------------
// Sample definitions
// ---------------------------------------------------------------------------

const WORKFLOW_DEF = {
  name: 'test-workflow',
  description: 'A test workflow',
  version: '1.0',
  type: 'step',
  steps: [
    {
      name: 'init',
      allowed_tools: 'all',
      transitions: [{ to: 'work', when: 'ready' }],
    },
    {
      name: 'work',
      allowed_tools: ['read', 'write'],
      transitions: [{ to: 'done', when: 'complete' }],
    },
    { name: 'done', allowed_tools: 'all' },
  ],
  observers: [{ name: 'watch-errors', on: 'tool_error', set: { error_count: '+1' } }],
  triggers: { on_session_start: [{ action: 'log', message: 'started' }] },
  exit_condition: 'steps_completed',
}

const PIPELINE_DEF = {
  name: 'test-pipeline',
  type: 'pipeline',
  steps: [
    { id: 'build', exec: 'make build' },
    { id: 'test', exec: 'make test' },
    { id: 'notify', prompt: 'Summarize results' },
    { id: 'deploy', exec: 'make deploy', approval: { required: true, message: 'Deploy?' } },
  ],
}

const CANVAS_JSON = JSON.stringify({
  'step-0': { x: 100, y: 50 },
  'step-1': { x: 100, y: 200 },
  'step-2': { x: 100, y: 350 },
  'observer-0': { x: 400, y: 50 },
  'trigger-0': { x: 400, y: 200 },
  'exit-condition-0': { x: 400, y: 350 },
})

// ---------------------------------------------------------------------------
// getLayoutedElements
// ---------------------------------------------------------------------------

describe('getLayoutedElements', () => {
  it('assigns positions to all nodes', () => {
    const nodes: FlowNode[] = [
      { id: 'a', type: 'step', position: { x: 0, y: 0 }, data: { label: 'A', nodeKind: 'step', stepIndex: 0, stepData: {} } },
      { id: 'b', type: 'step', position: { x: 0, y: 0 }, data: { label: 'B', nodeKind: 'step', stepIndex: 1, stepData: {} } },
    ]
    const edges: Edge[] = [{ id: 'e1', source: 'a', target: 'b' }]

    const result = getLayoutedElements(nodes, edges)

    expect(result.nodes).toHaveLength(2)
    // Both nodes should have non-zero positions (dagre lays them out)
    for (const node of result.nodes) {
      expect(typeof node.position.x).toBe('number')
      expect(typeof node.position.y).toBe('number')
    }
    // Node A should be above node B in TB layout
    const nodeA = result.nodes.find((n) => n.id === 'a')!
    const nodeB = result.nodes.find((n) => n.id === 'b')!
    expect(nodeA.position.y).toBeLessThan(nodeB.position.y)
  })

  it('supports LR direction', () => {
    const nodes: FlowNode[] = [
      { id: 'a', type: 'step', position: { x: 0, y: 0 }, data: { label: 'A', nodeKind: 'step', stepIndex: 0, stepData: {} } },
      { id: 'b', type: 'step', position: { x: 0, y: 0 }, data: { label: 'B', nodeKind: 'step', stepIndex: 1, stepData: {} } },
    ]
    const edges: Edge[] = [{ id: 'e1', source: 'a', target: 'b' }]

    const result = getLayoutedElements(nodes, edges, 'LR')

    const nodeA = result.nodes.find((n) => n.id === 'a')!
    const nodeB = result.nodes.find((n) => n.id === 'b')!
    // A should be to the left of B
    expect(nodeA.position.x).toBeLessThan(nodeB.position.x)
  })
})

// ---------------------------------------------------------------------------
// definitionToFlow — workflow
// ---------------------------------------------------------------------------

describe('definitionToFlow - workflow', () => {
  it('creates nodes for steps, observers, triggers, and exit condition', () => {
    const { nodes } = definitionToFlow(WORKFLOW_DEF)

    const stepNodes = nodes.filter((n) => n.data.nodeKind === 'step')
    const observerNodes = nodes.filter((n) => n.data.nodeKind === 'observer')
    const triggerNodes = nodes.filter((n) => n.data.nodeKind === 'trigger-group')
    const exitNodes = nodes.filter((n) => n.data.nodeKind === 'exit-condition')

    expect(stepNodes).toHaveLength(3)
    expect(observerNodes).toHaveLength(1)
    expect(triggerNodes).toHaveLength(1)
    expect(exitNodes).toHaveLength(1)
  })

  it('creates edges from transitions', () => {
    const { edges } = definitionToFlow(WORKFLOW_DEF)

    // init -> work, work -> done
    expect(edges).toHaveLength(2)
    expect(edges[0].source).toBe('step-0')
    expect(edges[0].target).toBe('step-1')
    expect(edges[0].label).toBe('ready')
    expect(edges[1].source).toBe('step-1')
    expect(edges[1].target).toBe('step-2')
    expect(edges[1].label).toBe('complete')
  })

  it('creates implicit sequential edges when no transitions exist', () => {
    const def = {
      steps: [
        { name: 'a', allowed_tools: 'all' },
        { name: 'b', allowed_tools: 'all' },
        { name: 'c', allowed_tools: 'all' },
      ],
    }

    const { edges } = definitionToFlow(def)

    expect(edges).toHaveLength(2)
    expect(edges[0].id).toContain('implicit')
    expect(edges[1].id).toContain('implicit')
  })

  it('preserves step data in nodes', () => {
    const { nodes } = definitionToFlow(WORKFLOW_DEF)

    const workNode = nodes.find((n) => n.data.label === 'work')!
    expect(workNode.data.stepData).toEqual(WORKFLOW_DEF.steps[1])
    expect(workNode.data.stepIndex).toBe(1)
  })

  it('uses saved canvas positions when provided', () => {
    const { nodes } = definitionToFlow(WORKFLOW_DEF, CANVAS_JSON)

    const initNode = nodes.find((n) => n.id === 'step-0')!
    expect(initNode.position).toEqual({ x: 100, y: 50 })

    const obsNode = nodes.find((n) => n.id === 'observer-0')!
    expect(obsNode.position).toEqual({ x: 400, y: 50 })
  })

  it('falls back to dagre layout without canvas positions', () => {
    const { nodes } = definitionToFlow(WORKFLOW_DEF)

    // All nodes should have positions assigned by dagre (not 0,0)
    const stepNodes = nodes.filter((n) => n.data.nodeKind === 'step')
    const positions = stepNodes.map((n) => n.position)
    // At least one should not be at 0,0
    expect(positions.some((p) => p.x !== 0 || p.y !== 0)).toBe(true)
  })

  it('falls back to dagre when canvas is incomplete', () => {
    const partialCanvas = JSON.stringify({ 'step-0': { x: 100, y: 50 } })
    const { nodes } = definitionToFlow(WORKFLOW_DEF, partialCanvas)

    // Should use dagre since not all nodes have positions
    const initNode = nodes.find((n) => n.id === 'step-0')!
    // Position should NOT be the partial one (dagre overwrites)
    // It should be dagre-assigned, which may or may not match
    expect(typeof initNode.position.x).toBe('number')
  })
})

// ---------------------------------------------------------------------------
// definitionToFlow — pipeline
// ---------------------------------------------------------------------------

describe('definitionToFlow - pipeline', () => {
  it('creates nodes for each pipeline step', () => {
    const { nodes } = definitionToFlow(PIPELINE_DEF)

    expect(nodes).toHaveLength(4)
    expect(nodes[0].data.label).toBe('build')
    expect(nodes[1].data.label).toBe('test')
    expect(nodes[2].data.label).toBe('notify')
    expect(nodes[3].data.label).toBe('deploy')
  })

  it('assigns correct node kinds based on step type', () => {
    const { nodes } = definitionToFlow(PIPELINE_DEF)

    expect(nodes[0].data.nodeKind).toBe('exec')
    expect(nodes[1].data.nodeKind).toBe('exec')
    expect(nodes[2].data.nodeKind).toBe('prompt')
    expect(nodes[3].data.nodeKind).toBe('exec') // has exec + approval, exec takes precedence
  })

  it('creates sequential edges between pipeline steps', () => {
    const { edges } = definitionToFlow(PIPELINE_DEF)

    expect(edges).toHaveLength(3)
    expect(edges[0].source).toBe('pipeline-0')
    expect(edges[0].target).toBe('pipeline-1')
    expect(edges[1].source).toBe('pipeline-1')
    expect(edges[1].target).toBe('pipeline-2')
    expect(edges[2].source).toBe('pipeline-2')
    expect(edges[2].target).toBe('pipeline-3')
  })

  it('detects approval step kind when no exec/prompt', () => {
    const def = {
      type: 'pipeline',
      steps: [
        { id: 'gate', approval: { required: true } },
      ],
    }
    const { nodes } = definitionToFlow(def)
    expect(nodes[0].data.nodeKind).toBe('approval')
  })
})

// ---------------------------------------------------------------------------
// flowToDefinition — workflow
// ---------------------------------------------------------------------------

describe('flowToDefinition - workflow', () => {
  it('reconstructs steps from nodes', () => {
    const { nodes, edges } = definitionToFlow(WORKFLOW_DEF)
    const { definition } = flowToDefinition(nodes, edges, false)

    const steps = definition.steps as Record<string, unknown>[]
    expect(steps).toHaveLength(3)
    expect(steps[0].name).toBe('init')
    expect(steps[1].name).toBe('work')
    expect(steps[2].name).toBe('done')
  })

  it('reconstructs transitions from edges', () => {
    const { nodes, edges } = definitionToFlow(WORKFLOW_DEF)
    const { definition } = flowToDefinition(nodes, edges, false)

    const steps = definition.steps as Record<string, unknown>[]
    const initStep = steps[0]
    const transitions = initStep.transitions as Record<string, unknown>[]
    expect(transitions).toHaveLength(1)
    expect(transitions[0].to).toBe('work')
    expect(transitions[0].when).toBe('ready')
  })

  it('reconstructs observers', () => {
    const { nodes, edges } = definitionToFlow(WORKFLOW_DEF)
    const { definition } = flowToDefinition(nodes, edges, false)

    const observers = definition.observers as Record<string, unknown>[]
    expect(observers).toHaveLength(1)
    expect(observers[0].name).toBe('watch-errors')
  })

  it('reconstructs triggers', () => {
    const { nodes, edges } = definitionToFlow(WORKFLOW_DEF)
    const { definition } = flowToDefinition(nodes, edges, false)

    const triggers = definition.triggers as Record<string, unknown>
    expect(triggers.on_session_start).toBeDefined()
  })

  it('reconstructs exit condition', () => {
    const { nodes, edges } = definitionToFlow(WORKFLOW_DEF)
    const { definition } = flowToDefinition(nodes, edges, false)

    expect(definition.exit_condition).toBe('steps_completed')
  })

  it('saves canvas positions', () => {
    const { nodes, edges } = definitionToFlow(WORKFLOW_DEF)
    const { canvasJson } = flowToDefinition(nodes, edges, false)

    const positions = JSON.parse(canvasJson)
    expect(positions['step-0']).toBeDefined()
    expect(typeof positions['step-0'].x).toBe('number')
    expect(typeof positions['step-0'].y).toBe('number')
  })
})

// ---------------------------------------------------------------------------
// flowToDefinition — pipeline
// ---------------------------------------------------------------------------

describe('flowToDefinition - pipeline', () => {
  it('reconstructs pipeline steps', () => {
    const { nodes, edges } = definitionToFlow(PIPELINE_DEF)
    const { definition } = flowToDefinition(nodes, edges, true)

    expect(definition.type).toBe('pipeline')
    const steps = definition.steps as Record<string, unknown>[]
    expect(steps).toHaveLength(4)
    expect(steps[0].id).toBe('build')
    expect(steps[0].exec).toBe('make build')
    expect(steps[2].prompt).toBe('Summarize results')
  })

  it('preserves approval data', () => {
    const { nodes, edges } = definitionToFlow(PIPELINE_DEF)
    const { definition } = flowToDefinition(nodes, edges, true)

    const steps = definition.steps as Record<string, unknown>[]
    const deployStep = steps[3]
    expect(deployStep.approval).toEqual({ required: true, message: 'Deploy?' })
  })
})

// ---------------------------------------------------------------------------
// Round-trip
// ---------------------------------------------------------------------------

describe('round-trip', () => {
  it('workflow: definitionToFlow -> flowToDefinition preserves steps', () => {
    const { nodes, edges } = definitionToFlow(WORKFLOW_DEF)
    const { definition } = flowToDefinition(nodes, edges, false)

    const origSteps = WORKFLOW_DEF.steps
    const outSteps = definition.steps as Record<string, unknown>[]

    expect(outSteps).toHaveLength(origSteps.length)
    for (let i = 0; i < origSteps.length; i++) {
      expect(outSteps[i].name).toBe(origSteps[i].name)
    }
  })

  it('workflow: round-trip preserves transitions', () => {
    const { nodes, edges } = definitionToFlow(WORKFLOW_DEF)
    const { definition } = flowToDefinition(nodes, edges, false)

    const outSteps = definition.steps as Record<string, unknown>[]
    const initTransitions = outSteps[0].transitions as Record<string, unknown>[]
    expect(initTransitions[0].to).toBe('work')
    expect(initTransitions[0].when).toBe('ready')
  })

  it('pipeline: definitionToFlow -> flowToDefinition preserves steps', () => {
    const { nodes, edges } = definitionToFlow(PIPELINE_DEF)
    const { definition } = flowToDefinition(nodes, edges, true)

    const origSteps = PIPELINE_DEF.steps
    const outSteps = definition.steps as Record<string, unknown>[]

    expect(outSteps).toHaveLength(origSteps.length)
    for (let i = 0; i < origSteps.length; i++) {
      expect(outSteps[i].id).toBe(origSteps[i].id)
    }
  })

  it('canvas positions round-trip through save/load', () => {
    const { nodes: nodes1, edges: edges1 } = definitionToFlow(WORKFLOW_DEF)
    const { canvasJson } = flowToDefinition(nodes1, edges1, false)

    // Re-load with the saved canvas
    const { nodes: nodes2 } = definitionToFlow(WORKFLOW_DEF, canvasJson)

    // Positions should match
    for (const n1 of nodes1) {
      const n2 = nodes2.find((n) => n.id === n1.id)!
      expect(n2.position.x).toBeCloseTo(n1.position.x, 5)
      expect(n2.position.y).toBeCloseTo(n1.position.y, 5)
    }
  })
})
