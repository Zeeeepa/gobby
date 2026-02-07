# Phase 0: TUI Dashboard

> **Framework:** Textual (Python)
> **Goal:** Fast, keyboard-driven task management without leaving terminal
> **Priority:** MVP - This is the first UI to build

## Scope Boundaries

The TUI is optimized for **speed and keyboard efficiency**. It deliberately excludes complex visualizations that are better suited to the web UI.

### TUI Does (Phase 0)
- **Tables and lists** - Task list, session timeline, agent list, memory search
- **Text-based trees** - Dependency trees as indented text, agent hierarchy
- **Quick actions** - Copy task ID, set session_task, cancel agent
- **Keyboard navigation** - vim-style movement, shortcuts for everything

### Web Only (Phase 1+)
- **Kanban board** - Drag-and-drop column layout
- **Task graph visualization** - Cytoscape.js interactive dependency graph
- **Rich editing** - Inline markdown editing, drag-to-reorder
- **Mobile/touch** - PWA, swipe gestures, responsive layouts

This separation ensures the TUI stays fast and focused while the web UI handles visual complexity.

---

## 0.1 Project Setup

- [ ] Create `src/gobby/tui/` package with `__init__.py`
- [ ] Add `textual>=0.47.0` dependency to pyproject.toml
- [ ] Create `gobby ui` CLI command in `src/gobby/cli.py`
- [ ] Create main app class `GobbyApp(App)` in `src/gobby/tui/app.py`
- [ ] Set up CSS file `src/gobby/tui/gobby.tcss` with design tokens
- [ ] Add hot-reload dev script: `textual run --dev src/gobby/tui/app.py`

## 0.2 Core Layout

- [ ] Implement header widget with daemon status (connected/disconnected)
- [ ] Create sidebar with navigation tabs (T)asks, (S)essions, (A)gents, (M)emory, Me(t)rics
- [ ] Add footer with context-sensitive keyboard hints
- [ ] Implement TabContent container for swapping views
- [ ] Add global keyboard bindings (j/k navigation, Tab, Enter, Esc, Q quit)
- [ ] Create `DaemonStatus` widget showing connection state

## 0.3 Task View (Critical Path)

### 0.3.1 Task List

- [ ] Create `TaskListView` screen with DataTable
- [ ] Add columns: Status, ID, Title, Type, Priority
- [ ] Implement status filtering (Ready, In Progress, Blocked, All)
- [ ] Add type filtering (bug, feature, task, epic, chore)
- [ ] Color-code rows by status using design tokens
- [ ] Show ready task count in tab label

### 0.3.2 Task Detail Panel

- [ ] Create `TaskDetailPanel` as side drawer (25% width)
- [ ] Display full task details (title, description, validation_criteria)
- [ ] Show dependencies (blocked_by, blocking)
- [ ] Display commits linked to task
- [ ] Show session history (created_in, closed_in)

### 0.3.3 Task Actions

- [ ] Enter on task: copy ID to clipboard, show confirmation
- [ ] `s` key: set as session_task (calls set_variable MCP tool)
- [ ] `e` key: expand task with AI (calls expand_task MCP tool)
- [ ] `c` key: close task (calls close_task MCP tool)
- [ ] `n` key: create new task (opens modal)
- [ ] `d` key: show dependency tree (text-based inline expansion, not graph)

### 0.3.4 Create Task Modal

- [ ] Create `CreateTaskModal` with form fields
- [ ] Add title input (required)
- [ ] Add description textarea
- [ ] Add type selector (dropdown)
- [ ] Add priority selector (0-4)
- [ ] Add parent task selector (optional)
- [ ] Submit calls create_task MCP tool

## 0.4 Session View

### 0.4.1 Session List

- [ ] Create `SessionListView` with DataTable
- [ ] Add columns: Time, Provider (badge), Title, Task, Tokens, Cost
- [ ] Group by date (Today, Yesterday, This Week, Older)
- [ ] Color provider badges (Claude=orange, Gemini=blue, Codex=green)
- [ ] Show active sessions at top with indicator

### 0.4.2 Session Detail

- [ ] Create `SessionDetailPanel` side drawer
- [ ] Show full session metadata
- [ ] Display handoff context (compact_markdown)
- [ ] Show tool call summary
- [ ] Display linked tasks

### 0.4.3 Session Actions

- [ ] `p` key: pickup session (copies handoff context to clipboard)
- [ ] `t` key: view transcript (opens in pager or external)
- [ ] `s` key: show summary markdown

## 0.5 Agent View

### 0.5.1 Running Agents

- [ ] Create `AgentListView` showing running agents
- [ ] Display agent tree hierarchy as indented text (parent/child)
- [ ] Show status: Running, Pending, Completed, Failed
- [ ] Display tool call count and elapsed time
- [ ] Show linked task and worktree

### 0.5.2 Agent Detail

- [ ] Create `AgentDetailPanel` with current prompt
- [ ] Show progress indicators
- [ ] Display provider and model
- [ ] Show parent session chain

### 0.5.3 Agent Actions

- [ ] `c` key: cancel agent (calls cancel_agent MCP tool)
- [ ] `Enter`: expand to show children
- [ ] `r` key: view result (if completed)

## 0.6 Memory View

- [ ] Create `MemoryListView` with searchable list
- [ ] Add search input with semantic search
- [ ] Display memory cards (type badge, content preview, importance)
- [ ] Filter by type (fact, preference, pattern, context)
- [ ] Filter by project
- [ ] `g` key: open memory graph in browser (existing viz.py)
- [ ] `n` key: create new memory
- [ ] `d` key: delete memory (with confirmation)

## 0.7 Metrics View

- [ ] Create `MetricsView` with summary stats
- [ ] Show tool call counts (top 10)
- [ ] Display session counts by provider
- [ ] Show token usage summary
- [ ] Display cost summary (today, week, month)
- [ ] Show MCP server health status

## 0.8 Daemon Connection

### 0.8.1 REST Client

- [ ] Create `DaemonClient` class with httpx
- [ ] Implement `/admin/status` health check
- [ ] Add MCP tool call wrapper (`call_tool` method)
- [ ] Handle connection errors gracefully
- [ ] Retry logic with exponential backoff

### 0.8.2 WebSocket Client

- [ ] Create `EventSubscriber` with websockets library
- [ ] Subscribe to relevant events on connect
- [ ] Parse event types and dispatch to handlers
- [ ] Handle reconnection on disconnect
- [ ] Emit local events to update views

### 0.8.3 Real-time Updates

- [ ] Update task list on task events
- [ ] Update session list on session events
- [ ] Update agent list on agent events
- [ ] Show toast notifications for important events

## 0.9 Polish

- [ ] Add loading states for async operations
- [ ] Implement error toast notifications
- [ ] Add command palette (Ctrl+K)
- [ ] Create help screen (? key)
- [ ] Add vim-style movement (h/j/k/l where appropriate)
- [ ] Test on 80x24 minimum terminal size
