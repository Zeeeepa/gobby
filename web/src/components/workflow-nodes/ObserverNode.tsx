/**
 * ObserverNode — Visual node for observers (nodeKind: 'observer').
 * Shows observer icon, event type (on field), and variable assignments preview.
 */

import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { NODE_KIND_META, type BaseNodeData } from './nodeTypes'
import { ObserverIcon } from './NodeIcons'
import './nodes.css'

type ObserverNodeType = Node<BaseNodeData, 'observer'>

function ObserverNodeInner({ data, selected }: NodeProps<ObserverNodeType>) {
  const meta = NODE_KIND_META[data.nodeKind]
  const accentColor = meta?.color ?? '#8b5cf6'
  const step = data.stepData

  const onEvent = (step.on as string) || ''
  const setVars = step.set as Record<string, unknown> | undefined
  const varsPreview = setVars
    ? Object.entries(setVars).map(([k, v]) => `${k}=${v}`).join(', ')
    : null

  return (
    <div
      className={`wf-node ${selected ? 'wf-node--selected' : ''}`}
      style={{ borderLeftColor: accentColor }}
    >
      <Handle type="target" position={Position.Top} className="wf-node-handle" />

      <div className="wf-node-header">
        <span className="wf-node-icon" style={{ color: accentColor }}>
          <ObserverIcon />
        </span>
        <span className="wf-node-name">{data.label}</span>
        <span className="wf-node-kind" style={{ color: accentColor }}>
          observer
        </span>
      </div>

      {onEvent && (
        <div className="observer-node-event">on: {onEvent}</div>
      )}

      {varsPreview && (
        <div className="observer-node-vars">{varsPreview}</div>
      )}

      <Handle type="source" position={Position.Bottom} className="wf-node-handle" />
    </div>
  )
}

export const ObserverNode = memo(ObserverNodeInner)
