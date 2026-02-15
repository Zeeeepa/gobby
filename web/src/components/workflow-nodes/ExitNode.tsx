/**
 * ExitNode — Visual node for exit conditions (nodeKind: 'exit-condition').
 * Shows exit icon and condition expression in monospace block.
 */

import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { NODE_KIND_META, type BaseNodeData } from './nodeTypes'
import { ExitIcon } from './NodeIcons'
import './nodes.css'

type ExitNodeType = Node<BaseNodeData, 'exit'>

function ExitNodeInner({ data, selected }: NodeProps<ExitNodeType>) {
  const meta = NODE_KIND_META[data.nodeKind]
  const accentColor = meta?.color ?? '#ef4444'
  const step = data.stepData

  const expression = (step.exit_condition as string) || ''

  return (
    <div
      className={`wf-node ${selected ? 'wf-node--selected' : ''}`}
      style={{ borderLeftColor: accentColor }}
    >
      <Handle type="target" position={Position.Top} className="wf-node-handle" />

      <div className="wf-node-header">
        <span className="wf-node-icon" style={{ color: accentColor }}>
          <ExitIcon />
        </span>
        <span className="wf-node-name">{data.label}</span>
        <span className="wf-node-kind" style={{ color: accentColor }}>
          exit
        </span>
      </div>

      {expression && (
        <div className="exit-node-expr">{expression}</div>
      )}

      <Handle type="source" position={Position.Bottom} className="wf-node-handle" />
    </div>
  )
}

export const ExitNode = memo(ExitNodeInner)
