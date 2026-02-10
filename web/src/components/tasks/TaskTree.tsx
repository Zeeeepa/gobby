import { useMemo, useRef, useState } from 'react'
import { Tree, TreeApi, NodeRendererProps } from 'react-arborist'
import type { GobbyTask } from '../../hooks/useTasks'
import { StatusDot, PriorityBadge, TypeBadge } from './TaskBadges'

// =============================================================================
// Tree data type
// =============================================================================

interface TreeNode {
  id: string
  task: GobbyTask
  children: TreeNode[]
}

// =============================================================================
// Closed statuses to filter
// =============================================================================

const CLOSED_STATUSES = new Set(['closed', 'approved'])

// =============================================================================
// Build tree from flat task list
// =============================================================================

function buildTree(tasks: GobbyTask[], hideClosed: boolean): TreeNode[] {
  const filtered = hideClosed ? tasks.filter(t => !CLOSED_STATUSES.has(t.status)) : tasks
  const nodeMap = new Map<string, TreeNode>()
  const roots: TreeNode[] = []

  for (const task of filtered) {
    nodeMap.set(task.id, { id: task.id, task, children: [] })
  }

  for (const task of filtered) {
    const node = nodeMap.get(task.id)!
    if (task.parent_task_id && nodeMap.has(task.parent_task_id)) {
      nodeMap.get(task.parent_task_id)!.children.push(node)
    } else {
      roots.push(node)
    }
  }

  return roots
}

// =============================================================================
// Custom node renderer
// =============================================================================

function TaskNode({ node, style, dragHandle }: NodeRendererProps<TreeNode>) {
  const task = node.data.task
  return (
    <div
      ref={dragHandle}
      style={style}
      className={`tree-node ${node.isSelected ? 'tree-node--selected' : ''}`}
      onClick={() => node.activate()}
    >
      {node.isInternal ? (
        <button
          className="tree-node-toggle"
          onClick={e => { e.stopPropagation(); node.toggle() }}
        >
          {node.isOpen ? '▾' : '▸'}
        </button>
      ) : (
        <span className="tree-node-toggle tree-node-toggle--leaf" />
      )}
      <StatusDot status={task.status} />
      <span className="tree-node-ref">{task.ref}</span>
      <span className="tree-node-title">{task.title}</span>
      <TypeBadge type={task.type} />
      <PriorityBadge priority={task.priority} />
    </div>
  )
}

// =============================================================================
// TaskTree
// =============================================================================

interface TaskTreeProps {
  tasks: GobbyTask[]
  onSelectTask: (id: string) => void
}

export function TaskTree({ tasks, onSelectTask }: TaskTreeProps) {
  const treeRef = useRef<TreeApi<TreeNode> | null>(null)
  const [hideClosed, setHideClosed] = useState(false)
  const treeData = useMemo(() => buildTree(tasks, hideClosed), [tasks, hideClosed])

  return (
    <div className="task-tree-container">
      <div className="task-tree-toolbar">
        <button
          className="task-tree-toolbar-btn"
          onClick={() => treeRef.current?.openAll()}
          title="Expand all"
        >
          Expand all
        </button>
        <button
          className="task-tree-toolbar-btn"
          onClick={() => treeRef.current?.closeAll()}
          title="Collapse all"
        >
          Collapse all
        </button>
        <label className="task-tree-toolbar-check">
          <input
            type="checkbox"
            checked={hideClosed}
            onChange={e => setHideClosed(e.target.checked)}
          />
          Hide closed
        </label>
      </div>
      <Tree<TreeNode>
        ref={treeRef}
        data={treeData}
        width="100%"
        height={560}
        indent={24}
        rowHeight={34}
        openByDefault={false}
        onActivate={node => onSelectTask(node.data.id)}
        disableDrag
        disableDrop
      >
        {TaskNode}
      </Tree>
    </div>
  )
}
