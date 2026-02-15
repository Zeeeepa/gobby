/**
 * PipelineStepNode — Visual node for pipeline step types:
 * exec, prompt, mcp, pipeline, spawn-session, approval.
 * Icon varies by nodeKind. Shows type badge, command/prompt preview, condition.
 */

import { memo } from 'react'
import { Handle, Position, type NodeProps, type Node } from '@xyflow/react'
import { NODE_KIND_META, type BaseNodeData } from './nodeTypes'
import {
  TerminalIcon,
  PromptIcon,
  PlugIcon,
  PipelineIcon,
  SpawnIcon,
  ApprovalIcon,
} from './NodeIcons'
import './nodes.css'

type PipelineStepNodeType = Node<BaseNodeData, 'pipelineStep'>

const PIPELINE_ICONS: Record<string, typeof TerminalIcon> = {
  'exec': TerminalIcon,
  'prompt': PromptIcon,
  'mcp': PlugIcon,
  'pipeline': PipelineIcon,
  'spawn-session': SpawnIcon,
  'approval': ApprovalIcon,
}

function PipelineStepNodeInner({ data, selected }: NodeProps<PipelineStepNodeType>) {
  const meta = NODE_KIND_META[data.nodeKind]
  const accentColor = meta?.color ?? '#06b6d4'
  const step = data.stepData

  const IconComponent = PIPELINE_ICONS[data.nodeKind] ?? TerminalIcon
  const exec = step.exec as string | undefined
  const prompt = step.prompt as string | undefined
  const condition = step.condition as string | undefined
  const mcp = step.mcp as Record<string, unknown> | undefined
  const invokePipeline = step.invoke_pipeline as string | undefined

  // Build preview text
  let preview: string | null = null
  if (exec) {
    preview = exec
  } else if (prompt) {
    preview = prompt.length > 60 ? prompt.slice(0, 60) + '...' : prompt
  } else if (mcp) {
    preview = `${mcp.server || '?'}.${mcp.tool || '?'}`
  } else if (invokePipeline) {
    preview = invokePipeline
  }

  return (
    <div
      className={`wf-node ${selected ? 'wf-node--selected' : ''}`}
      style={{ borderLeftColor: accentColor }}
    >
      <Handle type="target" position={Position.Top} className="wf-node-handle" />

      <div className="wf-node-header">
        <span className="wf-node-icon" style={{ color: accentColor }}>
          <IconComponent />
        </span>
        <span className="wf-node-name">{data.label}</span>
        <span className="wf-node-kind" style={{ color: accentColor }}>
          {meta?.label ?? data.nodeKind}
        </span>
      </div>

      <span className="pipeline-node-type">{data.nodeKind}</span>

      {preview && (
        <div className="pipeline-node-preview">{preview}</div>
      )}

      {condition && (
        <div className="pipeline-node-condition">if: {condition}</div>
      )}

      <Handle type="source" position={Position.Bottom} className="wf-node-handle" />
    </div>
  )
}

export const PipelineStepNode = memo(PipelineStepNodeInner)
