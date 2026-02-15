/**
 * TriggerNode — Visual node for trigger groups (nodeKind: 'trigger-group').
 * Shows trigger icon, event name, and action count badge.
 */

import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { NODE_KIND_META, type BaseNodeData } from './nodeTypes'
import { TriggerIcon } from './NodeIcons'
import './nodes.css'

type TriggerNodeType = Node<BaseNodeData, 'trigger'>

function TriggerNodeInner({ data, selected }: NodeProps<TriggerNodeType>) {
  const meta = NODE_KIND_META[data.nodeKind]
  const accentColor = meta?.color ?? '#f59e0b'
  const step = data.stepData

  const eventName = (step.name as string) || data.label
  const actions = step.actions as unknown[] | undefined
  const actionCount = Array.isArray(actions) ? actions.length : 0

  return (
    <div
      className={`wf-node ${selected ? 'wf-node--selected' : ''}`}
      style={{ borderLeftColor: accentColor }}
    >
      <Handle type="target" position={Position.Top} className="wf-node-handle" />

      <div className="wf-node-header">
        <span className="wf-node-icon" style={{ color: accentColor }}>
          <TriggerIcon />
        </span>
        <span className="wf-node-name">{data.label}</span>
        <span className="wf-node-kind" style={{ color: accentColor }}>
          trigger
        </span>
      </div>

      {eventName && (
        <div className="trigger-node-event">on: {eventName}</div>
      )}

      <div className="wf-node-badges">
        {actionCount > 0 && (
          <span className="wf-node-badge">{actionCount} action{actionCount !== 1 ? 's' : ''}</span>
        )}
      </div>

      <Handle type="source" position={Position.Bottom} className="wf-node-handle" />
    </div>
  )
}

export const TriggerNode = memo(TriggerNodeInner)
