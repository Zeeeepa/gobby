/**
 * WorkflowPropertyPanel — Right-side panel for editing selected node properties.
 * Dynamically renders forms based on node kind.
 */

import { useState, useCallback } from 'react'
import type { Node } from '@xyflow/react'
import type { BaseNodeData } from './workflow-nodes/nodeTypes'
import { NODE_KIND_META } from './workflow-nodes/nodeTypes'
import { ExpressionEditor } from './workflow-nodes/ExpressionEditor'
import './WorkflowPropertyPanel.css'

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface WorkflowPropertyPanelProps {
  selectedNode: Node<BaseNodeData> | null
  onChange: (nodeId: string, data: BaseNodeData) => void
  collapsed?: boolean
  onToggleCollapse?: () => void
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function WorkflowPropertyPanel({
  selectedNode,
  onChange,
  collapsed = false,
  onToggleCollapse,
}: WorkflowPropertyPanelProps) {
  if (collapsed) {
    return (
      <div className="property-panel property-panel--collapsed">
        <button className="property-panel-toggle" onClick={onToggleCollapse} title="Expand panel">
          &laquo;
        </button>
      </div>
    )
  }

  return (
    <div className="property-panel">
      <div className="property-panel-header">
        <span className="property-panel-title">Properties</span>
        {onToggleCollapse && (
          <button className="property-panel-toggle" onClick={onToggleCollapse} title="Collapse panel">
            &raquo;
          </button>
        )}
      </div>

      <div className="property-panel-content">
        {selectedNode ? (
          <NodeForm node={selectedNode} onChange={onChange} />
        ) : (
          <div className="property-panel-empty">
            Select a node to edit properties
          </div>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Dynamic form router
// ---------------------------------------------------------------------------

function NodeForm({
  node,
  onChange,
}: {
  node: Node<BaseNodeData>
  onChange: (nodeId: string, data: BaseNodeData) => void
}) {
  const { nodeKind } = node.data
  const meta = NODE_KIND_META[nodeKind]

  const handleChange = useCallback(
    (updates: Partial<BaseNodeData>) => {
      onChange(node.id, { ...node.data, ...updates })
    },
    [node.id, node.data, onChange],
  )

  const handleStepDataChange = useCallback(
    (key: string, value: unknown) => {
      onChange(node.id, {
        ...node.data,
        stepData: { ...node.data.stepData, [key]: value },
      })
    },
    [node.id, node.data, onChange],
  )

  return (
    <div className="property-form">
      {/* Kind badge */}
      <div className="property-form-kind" style={{ borderLeftColor: meta?.color ?? '#666' }}>
        <span className="property-form-kind-label">{meta?.label ?? nodeKind}</span>
      </div>

      {/* Common fields */}
      <FormSection title="General">
        <FormField label="Label">
          <input
            type="text"
            value={node.data.label}
            onChange={(e) => handleChange({ label: e.target.value })}
          />
        </FormField>
      </FormSection>

      {/* Kind-specific fields */}
      {nodeKind === 'step' && (
        <StepForm stepData={node.data.stepData} onChange={handleStepDataChange} />
      )}
      {(nodeKind === 'exec' || nodeKind === 'prompt' || nodeKind === 'mcp' ||
        nodeKind === 'pipeline' || nodeKind === 'spawn-session' || nodeKind === 'approval') && (
        <PipelineStepForm nodeKind={nodeKind} stepData={node.data.stepData} onChange={handleStepDataChange} />
      )}
      {nodeKind === 'observer' && (
        <ObserverForm stepData={node.data.stepData} onChange={handleStepDataChange} />
      )}
      {nodeKind === 'trigger-group' && (
        <TriggerForm stepData={node.data.stepData} onChange={handleStepDataChange} />
      )}
      {nodeKind === 'exit-condition' && (
        <ExitConditionForm stepData={node.data.stepData} onChange={handleStepDataChange} />
      )}
      {nodeKind === 'variable' && (
        <VariableForm stepData={node.data.stepData} onChange={handleStepDataChange} />
      )}
      {nodeKind === 'rule' && (
        <RuleForm stepData={node.data.stepData} onChange={handleStepDataChange} />
      )}
    </div>
  )
}

// ---------------------------------------------------------------------------
// Kind-specific forms
// ---------------------------------------------------------------------------

function StepForm({
  stepData,
  onChange,
}: {
  stepData: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
}) {
  const allowedTools = stepData.allowed_tools as string | string[] | undefined
  const toolsValue = allowedTools === 'all'
    ? 'all'
    : Array.isArray(allowedTools) ? allowedTools.join(', ') : ''

  return (
    <>
      <FormSection title="Step Configuration">
        <FormField label="Name">
          <input
            type="text"
            value={(stepData.name as string) ?? ''}
            onChange={(e) => onChange('name', e.target.value)}
          />
        </FormField>
        <FormField label="Description">
          <textarea
            value={(stepData.description as string) ?? ''}
            onChange={(e) => onChange('description', e.target.value)}
            rows={2}
          />
        </FormField>
        <FormField label="Status Message">
          <input
            type="text"
            value={(stepData.status_message as string) ?? ''}
            onChange={(e) => onChange('status_message', e.target.value)}
          />
        </FormField>
      </FormSection>
      <FormSection title="Tool Restrictions">
        <FormField label="Allowed Tools">
          <input
            type="text"
            value={toolsValue}
            onChange={(e) => {
              const v = e.target.value.trim()
              onChange('allowed_tools', v === 'all' ? 'all' : v.split(',').map((s) => s.trim()).filter(Boolean))
            }}
            placeholder="all, or comma-separated list"
          />
        </FormField>
      </FormSection>
      <FormSection title="Transitions">
        <FormField label="Exit When">
          <ExpressionEditor
            value={(stepData.exit_when as string) ?? ''}
            onChange={(v) => onChange('exit_when', v)}
            placeholder="Condition expression"
          />
        </FormField>
      </FormSection>
    </>
  )
}

function PipelineStepForm({
  nodeKind,
  stepData,
  onChange,
}: {
  nodeKind: string
  stepData: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
}) {
  return (
    <FormSection title="Pipeline Step">
      <FormField label="Step ID">
        <input
          type="text"
          value={(stepData.id as string) ?? ''}
          onChange={(e) => onChange('id', e.target.value)}
        />
      </FormField>
      {nodeKind === 'exec' && (
        <FormField label="Command">
          <ExpressionEditor
            value={(stepData.exec as string) ?? ''}
            onChange={(v) => onChange('exec', v)}
            placeholder="shell command"
            language="command"
          />
        </FormField>
      )}
      {nodeKind === 'prompt' && (
        <FormField label="Prompt">
          <ExpressionEditor
            value={(stepData.prompt as string) ?? ''}
            onChange={(v) => onChange('prompt', v)}
            placeholder="LLM prompt text"
            singleLine={false}
            language="template"
          />
        </FormField>
      )}
      {nodeKind === 'mcp' && (
        <>
          <FormField label="Server">
            <input
              type="text"
              value={((stepData.mcp as Record<string, unknown>)?.server as string) ?? ''}
              onChange={(e) => onChange('mcp', { ...(stepData.mcp as Record<string, unknown> ?? {}), server: e.target.value })}
            />
          </FormField>
          <FormField label="Tool">
            <input
              type="text"
              value={((stepData.mcp as Record<string, unknown>)?.tool as string) ?? ''}
              onChange={(e) => onChange('mcp', { ...(stepData.mcp as Record<string, unknown> ?? {}), tool: e.target.value })}
            />
          </FormField>
        </>
      )}
      <FormField label="Condition">
        <ExpressionEditor
          value={(stepData.condition as string) ?? ''}
          onChange={(v) => onChange('condition', v)}
          placeholder="Optional condition"
        />
      </FormField>
    </FormSection>
  )
}

function ObserverForm({
  stepData,
  onChange,
}: {
  stepData: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
}) {
  return (
    <FormSection title="Observer">
      <FormField label="Name">
        <input
          type="text"
          value={(stepData.name as string) ?? ''}
          onChange={(e) => onChange('name', e.target.value)}
        />
      </FormField>
      <FormField label="On Event">
        <input
          type="text"
          value={(stepData.on as string) ?? ''}
          onChange={(e) => onChange('on', e.target.value)}
          placeholder="e.g., tool_error"
        />
      </FormField>
    </FormSection>
  )
}

function TriggerForm({
  stepData,
  onChange,
}: {
  stepData: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
}) {
  return (
    <FormSection title="Trigger Group">
      <FormField label="Event Name">
        <input
          type="text"
          value={(stepData.name as string) ?? ''}
          onChange={(e) => onChange('name', e.target.value)}
          placeholder="e.g., on_session_start"
        />
      </FormField>
    </FormSection>
  )
}

function ExitConditionForm({
  stepData,
  onChange,
}: {
  stepData: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
}) {
  return (
    <FormSection title="Exit Condition">
      <FormField label="Condition">
        <ExpressionEditor
          value={(stepData.exit_condition as string) ?? ''}
          onChange={(v) => onChange('exit_condition', v)}
          placeholder="Expression, e.g. steps.all_complete"
        />
      </FormField>
    </FormSection>
  )
}

function VariableForm({
  stepData,
  onChange,
}: {
  stepData: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
}) {
  return (
    <FormSection title="Variable">
      <FormField label="Name">
        <input
          type="text"
          value={(stepData.name as string) ?? ''}
          onChange={(e) => onChange('name', e.target.value)}
        />
      </FormField>
      <FormField label="Value">
        <input
          type="text"
          value={(stepData.value as string) ?? ''}
          onChange={(e) => onChange('value', e.target.value)}
        />
      </FormField>
    </FormSection>
  )
}

function RuleForm({
  stepData,
  onChange,
}: {
  stepData: Record<string, unknown>
  onChange: (key: string, value: unknown) => void
}) {
  return (
    <FormSection title="Rule">
      <FormField label="Name">
        <input
          type="text"
          value={(stepData.name as string) ?? ''}
          onChange={(e) => onChange('name', e.target.value)}
        />
      </FormField>
      <FormField label="When">
        <ExpressionEditor
          value={(stepData.when as string) ?? ''}
          onChange={(v) => onChange('when', v)}
          placeholder="Condition expression"
        />
      </FormField>
      <FormField label="Action">
        <select
          value={(stepData.action as string) ?? 'block'}
          onChange={(e) => onChange('action', e.target.value)}
        >
          <option value="block">Block</option>
          <option value="allow">Allow</option>
          <option value="warn">Warn</option>
          <option value="require_approval">Require Approval</option>
        </select>
      </FormField>
      <FormField label="Message">
        <input
          type="text"
          value={(stepData.message as string) ?? ''}
          onChange={(e) => onChange('message', e.target.value)}
          placeholder="Optional message"
        />
      </FormField>
    </FormSection>
  )
}

// ---------------------------------------------------------------------------
// Shared form primitives
// ---------------------------------------------------------------------------

function FormSection({
  title,
  children,
}: {
  title: string
  children: React.ReactNode
}) {
  const [expanded, setExpanded] = useState(true)

  return (
    <div className="property-section">
      <button
        className="property-section-header"
        onClick={() => setExpanded(!expanded)}
      >
        <span className="property-section-chevron">{expanded ? '\u25BE' : '\u25B8'}</span>
        <span>{title}</span>
      </button>
      {expanded && <div className="property-section-body">{children}</div>}
    </div>
  )
}

function FormField({
  label,
  children,
}: {
  label: string
  children: React.ReactNode
}) {
  return (
    <div className="property-field">
      <label className="property-field-label">{label}</label>
      {children}
    </div>
  )
}
