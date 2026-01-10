# Phase 4: Agent Orchestrator

> **Framework:** Web UI + Daemon integration
> **Goal:** Spawn, monitor, and control agents from UI
> **Depends on:** Phase 3 (Task Graph for task assignment)

## 4.1 Worktree List View

### 4.1.1 Worktree Table

- [ ] Create `WorktreesPage` with DataTable
- [ ] Add columns: Status, ID, Branch, Task, Agent, Updated
- [ ] Color status badges (active=green, stale=yellow, merged=gray)
- [ ] Show ahead/behind counts relative to base branch
- [ ] Add conflict warning indicator

### 4.1.2 Worktree Row

- [ ] Create `WorktreeRow` component
- [ ] Link to task (clickable)
- [ ] Show agent session if active
- [ ] Display last activity timestamp
- [ ] Add quick action buttons

### 4.1.3 Filters

- [ ] Filter by status (active, stale, merged, abandoned)
- [ ] Filter by has_agent (with/without active agent)
- [ ] Filter by task assignment
- [ ] Search by branch name

## 4.2 Worktree Actions

### 4.2.1 Create Worktree

- [ ] Create `CreateWorktreeDialog` modal
- [ ] Branch name input (auto-generated from task title)
- [ ] Task selector (required)
- [ ] Base branch selector (defaults to main)
- [ ] Submit calls `create_worktree` MCP tool

### 4.2.2 Worktree Operations

- [ ] "Sync from Main" button (calls daemon endpoint)
- [ ] "Delete" button with confirmation
- [ ] "Mark Merged" button for manual merge tracking
- [ ] "Open Terminal" button (deep link or instruction)

### 4.2.3 Bulk Actions

- [ ] Select multiple worktrees
- [ ] "Cleanup Stale" action
- [ ] "Delete Merged" action
- [ ] Confirmation with list

## 4.3 Agent Spawning

### 4.3.1 Spawn Agent Dialog

- [ ] Create `SpawnAgentDialog` modal
- [ ] Task selector (auto-filled from context)
- [ ] Worktree selector or "Create New"
- [ ] Initial prompt textarea
- [ ] Provider selector (Claude, Gemini, Codex)
- [ ] Model override (optional)

### 4.3.2 Spawn Options

- [ ] Mode selector: terminal, headless, embedded
- [ ] Max turns limit
- [ ] Tool filter (workflow-based)
- [ ] Context injection options (summary, compact, transcript)

### 4.3.3 Terminal Integration

- [ ] Detect available terminals (iTerm, Ghostty, Terminal.app)
- [ ] Show terminal launch instructions
- [ ] Copy launch command to clipboard
- [ ] Track spawned session in UI

## 4.4 Agent Monitoring

### 4.4.1 Agent List

- [ ] Create `AgentsPage` with running agents
- [ ] Show agent tree (parent/child hierarchy)
- [ ] Display status: Running, Pending, Completed, Failed, Cancelled
- [ ] Show tool call count (real-time via WebSocket)
- [ ] Show elapsed time

### 4.4.2 Agent Card

- [ ] Create `AgentCard` component
- [ ] Show provider icon and model
- [ ] Display linked task and worktree
- [ ] Show progress indicator
- [ ] Add expand button for children

### 4.4.3 Agent Detail

- [ ] Create `AgentDetailSheet` slide-out
- [ ] Show original prompt
- [ ] Display result (if completed)
- [ ] Show error message (if failed)
- [ ] List tool calls

### 4.4.4 Agent Actions

- [ ] "Cancel" button (calls `cancel_agent` MCP tool)
- [ ] "View Session" link to Sessions view
- [ ] "View Worktree" link to Worktrees view
- [ ] "Copy Result" button

## 4.5 Agent Tree Visualization

### 4.5.1 Tree Layout

- [ ] Create `AgentTree` component with tree visualization
- [ ] Show hierarchy: Primary Session → Child Agents → Grandchildren
- [ ] Use indentation for depth
- [ ] Collapsible nodes

### 4.5.2 Tree Node

- [ ] Show agent status icon
- [ ] Display prompt preview (truncated)
- [ ] Show tool call count
- [ ] Animate running agents

### 4.5.3 Tree Actions

- [ ] Click to select and show detail
- [ ] Cancel from tree node
- [ ] Expand/collapse subtrees

## 4.6 Merge Preview

### 4.6.1 Merge Preview Modal

- [ ] Create `MergePreviewModal` component
- [ ] Call daemon merge preview endpoint
- [ ] List files with change type (added, modified, deleted)
- [ ] Show conflict indicators

### 4.6.2 Conflict Resolution

- [ ] Display conflicting files
- [ ] Show diff preview for each file
- [ ] "Resolve with AI" button (future)
- [ ] "Manual Resolve" instructions
- [ ] "Abort Merge" button

### 4.6.3 Merge Execution

- [ ] "Merge" button with confirmation
- [ ] Show merge progress
- [ ] Handle merge errors
- [ ] Update worktree status on success
