/**
 * StepNode — Custom React Flow node for workflow steps, pipeline steps,
 * observers, triggers, and other node kinds.
 */

import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { NODE_KIND_META, type BaseNodeData } from './nodeTypes'
import './StepNode.css'

type StepNodeType = Node<BaseNodeData, 'step'>

function StepNodeInner({ data, selected }: NodeProps<StepNodeType>) {
  const meta = NODE_KIND_META[data.nodeKind]
  const accentColor = meta?.color ?? '#666'
  const step = data.stepData

  // Extract badge info from step data
  const allowedTools = step.allowed_tools
  const blockedTools = step.blocked_tools as string[] | undefined
  const rules = step.rules as unknown[] | undefined
  const transitions = step.transitions as unknown[] | undefined
  const statusMessage = step.status_message as string | undefined
  const description = (step.description as string) ?? null
  const condition = step.condition as string | undefined
  const exec = step.exec as string | undefined
  const prompt = step.prompt as string | undefined

  // Tool restriction summary
  let toolBadge: string | null = null
  if (allowedTools === 'all') {
    toolBadge = 'all tools'
  } else if (Array.isArray(allowedTools)) {
    toolBadge = `${allowedTools.length} tool${allowedTools.length !== 1 ? 's' : ''}`
  }

  const blockedCount = Array.isArray(blockedTools) ? blockedTools.length : 0
  const ruleCount = Array.isArray(rules) ? rules.length : 0
  const transitionCount = Array.isArray(transitions) ? transitions.length : 0

  return (
    <div
      className={`step-node ${selected ? 'step-node--selected' : ''}`}
      style={{ borderLeftColor: accentColor }}
    >
      <Handle type="target" position={Position.Top} className="step-node-handle" />

      {/* Header */}
      <div className="step-node-header">
        <span className="step-node-name">{data.label}</span>
        <span className="step-node-kind" style={{ color: accentColor }}>
          {data.nodeKind}
        </span>
      </div>

      {/* Description or status message preview */}
      {(description || statusMessage) && (
        <div className="step-node-desc">
          {description || statusMessage}
        </div>
      )}

      {/* Command preview for exec/prompt steps */}
      {exec && (
        <div className="step-node-command">{exec}</div>
      )}
      {prompt && !exec && (
        <div className="step-node-command">{prompt.length > 50 ? prompt.slice(0, 50) + '...' : prompt}</div>
      )}

      {/* Condition */}
      {condition && (
        <div className="step-node-condition">if: {condition}</div>
      )}

      {/* Badges */}
      <div className="step-node-badges">
        {toolBadge && (
          <span className="step-node-badge step-node-badge--tools">{toolBadge}</span>
        )}
        {blockedCount > 0 && (
          <span className="step-node-badge step-node-badge--blocked">{blockedCount} blocked</span>
        )}
        {ruleCount > 0 && (
          <span className="step-node-badge step-node-badge--rules">{ruleCount} rule{ruleCount !== 1 ? 's' : ''}</span>
        )}
        {transitionCount > 0 && (
          <span className="step-node-badge step-node-badge--transitions">{transitionCount} transition{transitionCount !== 1 ? 's' : ''}</span>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="step-node-handle" />
    </div>
  )
}

export const StepNode = memo(StepNodeInner)
