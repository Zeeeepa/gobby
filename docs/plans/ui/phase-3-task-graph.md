# Phase 3: Task Graph Visualization

> **Framework:** Cytoscape.js
> **Goal:** Visual task dependency management
> **Depends on:** Phase 2 (Real-time Updates)

## 3.1 Graph Library Setup

### 3.1.1 Installation

- [ ] Install Cytoscape.js: `npm install cytoscape`
- [ ] Install layout algorithms: `npm install cytoscape-dagre cytoscape-fcose`
- [ ] Install React wrapper: `npm install react-cytoscapejs`
- [ ] Add TypeScript types: `npm install @types/cytoscape`

### 3.1.2 Base Configuration

- [ ] Create `components/TaskGraph/index.tsx` component
- [ ] Configure Cytoscape with dark theme matching design system
- [ ] Set up zoom controls (scroll, buttons)
- [ ] Configure pan behavior (drag)
- [ ] Set min/max zoom levels

## 3.2 Graph Data

### 3.2.1 Data Transformation

- [ ] Create `lib/graph/transform.ts` for data conversion
- [ ] Map Task to Cytoscape node format
- [ ] Map TaskDependency to Cytoscape edge format
- [ ] Calculate node positions with dagre layout
- [ ] Handle circular dependency detection

### 3.2.2 Node Styling

- [ ] Define node shape by task type (epic=diamond, task=rectangle, bug=triangle)
- [ ] Set node color by status (open=gray, in_progress=blue, closed=green, blocked=red)
- [ ] Size nodes by subtask count
- [ ] Add icon overlay for priority
- [ ] Style selected node with highlight ring

### 3.2.3 Edge Styling

- [ ] Color edges by dependency type (blocks=red, related=gray)
- [ ] Add arrow heads for direction
- [ ] Style edges on hover
- [ ] Highlight path to selected node

## 3.3 Graph Interactions

### 3.3.1 Selection

- [ ] Click node to select
- [ ] Update task detail panel on selection
- [ ] Highlight connected nodes
- [ ] Show dependency path

### 3.3.2 Navigation

- [ ] Double-click to open task detail sheet
- [ ] Right-click for context menu
- [ ] Keyboard navigation (arrow keys when node selected)
- [ ] Focus on node (center and zoom)

### 3.3.3 Context Menu

- [ ] Create `GraphContextMenu` component
- [ ] Add "Edit Task" action
- [ ] Add "Expand with AI" action
- [ ] Add "Add Dependency" action
- [ ] Add "Close Task" action

### 3.3.4 Dependency Creation

- [ ] Shift+click to start edge creation
- [ ] Draw line to target node
- [ ] Show valid drop targets
- [ ] Create dependency via MCP tool

## 3.4 Layout Options

### 3.4.1 Layout Algorithms

- [ ] Implement dagre (hierarchical) layout - default
- [ ] Implement fcose (force-directed) layout
- [ ] Add layout selector dropdown
- [ ] Animate layout transitions

### 3.4.2 Filtering

- [ ] Add status filter (show/hide closed)
- [ ] Add type filter
- [ ] Add priority filter
- [ ] Highlight filtered nodes

### 3.4.3 Grouping

- [ ] Group by parent task (collapse subtasks)
- [ ] Group by epic
- [ ] Expand/collapse groups
- [ ] Show group summary

## 3.5 Task Detail Panel

### 3.5.1 Panel Layout

- [ ] Create `TaskDetailPanel` as slide-out from right
- [ ] Show full task information
- [ ] Display dependency graph minimap
- [ ] Add action buttons row

### 3.5.2 Inline Editing

- [ ] Edit title inline
- [ ] Edit description with markdown preview
- [ ] Edit priority with dropdown
- [ ] Save on blur or Ctrl+Enter

### 3.5.3 Actions

- [ ] "Expand with AI" button (calls expand_task)
- [ ] "Close" button with commit input
- [ ] "Delete" button with confirmation
- [ ] "Add Subtask" button

## 3.6 Export

- [ ] Add "Export PNG" button
- [ ] Add "Export SVG" button
- [ ] Include legend in export
- [ ] Add title/date stamp
