import { useMemo } from 'react'
import { Tree, NodeRendererProps } from 'react-arborist'
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
// Build tree from flat task list
// =============================================================================

function buildTree(tasks: GobbyTask[]): TreeNode[] {
  const nodeMap = new Map<string, TreeNode>()
  const roots: TreeNode[] = []

  // Create nodes
  for (const task of tasks) {
    nodeMap.set(task.id, { id: task.id, task, children: [] })
  }

  // Wire parent-child relationships
  for (const task of tasks) {
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
  const treeData = useMemo(() => buildTree(tasks), [tasks])

  return (
    <div className="task-tree-container">
      <Tree<TreeNode>
        data={treeData}
        width="100%"
        height={600}
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
