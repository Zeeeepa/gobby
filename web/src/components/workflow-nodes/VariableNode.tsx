/**
 * VariableNode — Visual node for variables (nodeKind: 'variable').
 * Shows variable icon, name/value pair, and scope badge.
 */

import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { NODE_KIND_META, type BaseNodeData } from './nodeTypes'
import { VariableIcon } from './NodeIcons'
import './nodes.css'

type VariableNodeType = Node<BaseNodeData, 'variable'>

function VariableNodeInner({ data, selected }: NodeProps<VariableNodeType>) {
  const meta = NODE_KIND_META[data.nodeKind]
  const accentColor = meta?.color ?? '#10b981'
  const step = data.stepData

  const varName = (step.name as string) || data.label
  const varValue = step.value as string | undefined
  const scope = (step.scope as string) || 'workflow'

  return (
    <div
      className={`wf-node ${selected ? 'wf-node--selected' : ''}`}
      style={{ borderLeftColor: accentColor }}
    >
      <Handle type="target" position={Position.Top} className="wf-node-handle" />

      <div className="wf-node-header">
        <span className="wf-node-icon" style={{ color: accentColor }}>
          <VariableIcon />
        </span>
        <span className="wf-node-name">{data.label}</span>
        <span className="wf-node-kind" style={{ color: accentColor }}>
          variable
        </span>
      </div>

      <div className="variable-node-pair">
        <span className="variable-key">{varName}</span> = {varValue || '""'}
      </div>

      <div className="wf-node-badges">
        <span className="variable-node-scope">{scope}</span>
      </div>

      <Handle type="source" position={Position.Bottom} className="wf-node-handle" />
    </div>
  )
}

export const VariableNode = memo(VariableNodeInner)
