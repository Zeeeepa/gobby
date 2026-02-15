/**
 * StepNode — Visual node for workflow steps (nodeKind: 'step' and 'rule').
 * Shows tool badges, rule count, transition count, description/status_message.
 */

import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { NODE_KIND_META, type BaseNodeData } from './nodeTypes'
import { StepIcon } from './NodeIcons'
import './nodes.css'

type StepNodeType = Node<BaseNodeData, 'step'>

function StepNodeInner({ data, selected }: NodeProps<StepNodeType>) {
  const meta = NODE_KIND_META[data.nodeKind]
  const accentColor = meta?.color ?? '#666'
  const step = data.stepData

  const allowedTools = step.allowed_tools
  const blockedTools = step.blocked_tools as string[] | undefined
  const rules = step.rules as unknown[] | undefined
  const transitions = step.transitions as unknown[] | undefined
  const statusMessage = step.status_message as string | undefined
  const description = (step.description as string) ?? null

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
      className={`wf-node ${selected ? 'wf-node--selected' : ''}`}
      style={{ borderLeftColor: accentColor }}
    >
      <Handle type="target" position={Position.Top} className="wf-node-handle" />

      {/* Header */}
      <div className="wf-node-header">
        <span className="wf-node-icon" style={{ color: accentColor }}>
          <StepIcon />
        </span>
        <span className="wf-node-name">{data.label}</span>
        <span className="wf-node-kind" style={{ color: accentColor }}>
          {data.nodeKind}
        </span>
      </div>

      {/* Description or status message preview */}
      {(description || statusMessage) && (
        <div className="wf-node-desc">
          {description || statusMessage}
        </div>
      )}

      {/* Badges */}
      <div className="wf-node-badges">
        {toolBadge && (
          <span className="wf-node-badge wf-node-badge--tools">{toolBadge}</span>
        )}
        {blockedCount > 0 && (
          <span className="wf-node-badge wf-node-badge--blocked">{blockedCount} blocked</span>
        )}
        {ruleCount > 0 && (
          <span className="wf-node-badge wf-node-badge--rules">{ruleCount} rule{ruleCount !== 1 ? 's' : ''}</span>
        )}
        {transitionCount > 0 && (
          <span className="wf-node-badge wf-node-badge--transitions">{transitionCount} transition{transitionCount !== 1 ? 's' : ''}</span>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="wf-node-handle" />
    </div>
  )
}

export const StepNode = memo(StepNodeInner)
