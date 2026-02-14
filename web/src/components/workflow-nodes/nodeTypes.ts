/**
 * Shared node type definitions and registry for the visual workflow builder.
 * The nodeTypes object is defined at module scope to prevent React re-renders.
 */

import type { NodeTypes } from '@xyflow/react'
import { StepNode } from './StepNode'

// ---------------------------------------------------------------------------
// Node data types
// ---------------------------------------------------------------------------

/** Base data shape shared by all custom nodes. */
export interface BaseNodeData extends Record<string, unknown> {
  label: string
  nodeKind: string
  stepIndex: number
  /** Original step data preserved for round-trip serialization. */
  stepData: Record<string, unknown>
}

/** Step node: workflow step with tool restrictions and transitions. */
export interface StepNodeData extends BaseNodeData {
  nodeKind: 'step'
}

/** Trigger group node. */
export interface TriggerNodeData extends BaseNodeData {
  nodeKind: 'trigger-group'
}

/** Observer node. */
export interface ObserverNodeData extends BaseNodeData {
  nodeKind: 'observer'
}

/** Exit condition node. */
export interface ExitConditionNodeData extends BaseNodeData {
  nodeKind: 'exit-condition'
}

/** Pipeline exec step node. */
export interface ExecNodeData extends BaseNodeData {
  nodeKind: 'exec'
}

/** Pipeline prompt step node. */
export interface PromptNodeData extends BaseNodeData {
  nodeKind: 'prompt'
}

/** Pipeline MCP step node. */
export interface McpNodeData extends BaseNodeData {
  nodeKind: 'mcp'
}

/** Pipeline nested pipeline step node. */
export interface PipelineStepNodeData extends BaseNodeData {
  nodeKind: 'pipeline'
}

/** Pipeline spawn session step node. */
export interface SpawnSessionNodeData extends BaseNodeData {
  nodeKind: 'spawn-session'
}

/** Pipeline approval gate node. */
export interface ApprovalNodeData extends BaseNodeData {
  nodeKind: 'approval'
}

/** Variable node. */
export interface VariableNodeData extends BaseNodeData {
  nodeKind: 'variable'
}

/** Rule node. */
export interface RuleNodeData extends BaseNodeData {
  nodeKind: 'rule'
}

/** Union of all node data types. */
export type AnyNodeData =
  | StepNodeData
  | TriggerNodeData
  | ObserverNodeData
  | ExitConditionNodeData
  | ExecNodeData
  | PromptNodeData
  | McpNodeData
  | PipelineStepNodeData
  | SpawnSessionNodeData
  | ApprovalNodeData
  | VariableNodeData
  | RuleNodeData

// ---------------------------------------------------------------------------
// Node kind metadata
// ---------------------------------------------------------------------------

export interface NodeKindMeta {
  label: string
  description: string
  color: string
}

export const NODE_KIND_META: Record<string, NodeKindMeta> = {
  'step':            { label: 'Step',           description: 'A workflow step with tool restrictions', color: '#3b82f6' },
  'trigger-group':   { label: 'Trigger Group',  description: 'Group of trigger conditions',           color: '#f59e0b' },
  'observer':        { label: 'Observer',       description: 'Watches for state changes',             color: '#8b5cf6' },
  'exit-condition':  { label: 'Exit Condition', description: 'Terminates the workflow',               color: '#ef4444' },
  'exec':            { label: 'Exec Step',      description: 'Run a shell command',                   color: '#06b6d4' },
  'prompt':          { label: 'Prompt Step',    description: 'LLM prompt execution',                  color: '#a855f7' },
  'mcp':             { label: 'MCP Step',       description: 'Call an MCP tool',                      color: '#3b82f6' },
  'pipeline':        { label: 'Pipeline Step',  description: 'Nested pipeline',                       color: '#c084fc' },
  'spawn-session':   { label: 'Spawn Session',  description: 'Launch agent session',                  color: '#22d3ee' },
  'approval':        { label: 'Approval Gate',  description: 'Require human approval',                color: '#f97316' },
  'variable':        { label: 'Variable',       description: 'Define or transform a variable',        color: '#10b981' },
  'rule':            { label: 'Rule',           description: 'Conditional branching rule',             color: '#eab308' },
}

// ---------------------------------------------------------------------------
// Default data factory
// ---------------------------------------------------------------------------

export function getDefaultData(nodeKind: string): BaseNodeData {
  const meta = NODE_KIND_META[nodeKind]
  const label = meta?.label ?? nodeKind

  const base: BaseNodeData = {
    label,
    nodeKind,
    stepIndex: -1,
    stepData: {},
  }

  // Provide sensible defaults per kind
  switch (nodeKind) {
    case 'step':
      base.stepData = { name: label, allowed_tools: 'all' }
      break
    case 'exec':
      base.stepData = { id: label, exec: '' }
      break
    case 'prompt':
      base.stepData = { id: label, prompt: '' }
      break
    case 'mcp':
      base.stepData = { id: label, mcp: { server: '', tool: '' } }
      break
    case 'pipeline':
      base.stepData = { id: label, invoke_pipeline: '' }
      break
    case 'spawn-session':
      base.stepData = { id: label, spawn_session: {} }
      break
    case 'approval':
      base.stepData = { id: label, approval: { required: true } }
      break
    case 'observer':
      base.stepData = { name: label, on: '' }
      break
    case 'trigger-group':
      base.stepData = { name: label, actions: [] }
      break
    case 'exit-condition':
      base.stepData = { exit_condition: '' }
      break
    case 'variable':
      base.stepData = { name: label, value: '' }
      break
    case 'rule':
      base.stepData = { name: label, when: '', action: 'block' }
      break
  }

  return base
}

// ---------------------------------------------------------------------------
// Node types registry — defined at module scope to prevent re-renders
// ---------------------------------------------------------------------------

export const nodeTypes: NodeTypes = {
  step: StepNode,
}
