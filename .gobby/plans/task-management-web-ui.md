# Task Management Web UI

## Overview

Build a first-class task management interface for the Gobby web UI. The backend has a rich task system (47+ field data model, 8 statuses, hierarchy, dependencies, validation, expansion) but no HTTP REST endpoints and no web UI. The "Tasks" tab currently shows "Coming Soon".

The goal is a system that feels like "Linear + LangGraph DevTools + Jira" in one place: you always know what agents are doing, why, and what changed, with low friction to interact or intervene.

## Constraints

- React 18 + TypeScript, Vite build, no React Router (tab-based nav)
- CSS variables for theming (dark theme), no Tailwind or CSS-in-JS
- Backend: FastAPI HTTP on port 60887, WebSocket on port 60888
- Task operations currently MCP-only; need REST endpoints first
- Must follow existing patterns: `useMemory.ts` hook, `memory.py` route factory, `broadcast.py` mixin
- Key backend files: `storage/tasks/_manager.py`, `storage/tasks/_models.py`, `storage/tasks/_queries.py`, `storage/task_dependencies.py`
- New dependencies allowed: `@atlaskit/pragmatic-drag-and-drop` (~5KB), `react-arborist` (~15KB)

## Phase 1: Backend REST API

**Goal**: Expose task CRUD, lifecycle, and dependency operations as HTTP endpoints for the web UI.

**Tasks:**
- [ ] Create task REST router with CRUD endpoints (category: code)
- [ ] Add list tasks endpoint with filtering and stats (category: code)
- [ ] Add task lifecycle endpoints - close, reopen (category: code)
- [ ] Add task dependency endpoints - get tree, add, remove (category: code)
- [ ] Register tasks router in HTTP server and routes __init__ (category: config)
- [ ] Add broadcast_task_event to WebSocket broadcast mixin (category: code)
- [ ] Wire task event broadcasting into REST route handlers (category: code)

## Phase 2: Frontend Data Layer

**Goal**: Create the data fetching hook and install frontend dependencies.

**Tasks:**
- [ ] Install @atlaskit/pragmatic-drag-and-drop and react-arborist (category: config)
- [ ] Create useTasks hook with fetch, CRUD, polling, and filters (depends: Phase 1) (category: code)
- [ ] Wire TasksPage into App.tsx replacing ComingSoonPage (depends: Phase 1) (category: code)

## Phase 3: Core Layout and Task Detail

**Goal**: Build the page shell with toolbar, view toggle, filter bar, and task detail panel.

**Tasks:**
- [ ] Create TasksPage shell with toolbar, view toggle, and filter bar (depends: Phase 2) (category: code)
- [ ] Create shared TaskBadges - StatusBadge, PriorityBadge, TypeBadge, BlockedIndicator (category: code)
- [ ] Create TaskDetail slide-in panel with metadata, actions, description (depends: Phase 2) (category: code)
- [ ] Add status action buttons to TaskDetail - contextual by current status (category: code)
- [ ] Add dependency and hierarchy sections to TaskDetail (category: code)
- [ ] Add validation info section to TaskDetail (category: code)

## Phase 4: Task Creation

**Goal**: Enable creating tasks from the web UI with smart defaults.

**Tasks:**
- [ ] Create TaskCreateForm modal with required and optional fields (depends: Phase 3) (category: code)
- [ ] Add quick-capture command palette entry for task creation (depends: Phase 3) (category: code)
- [ ] Add context-aware defaults - auto-suggest project, type, priority from current view (category: code)

## Phase 5: Kanban Board

**Goal**: Build the primary execution view with drag-and-drop status changes.

**Tasks:**
- [ ] Create KanbanBoard component with 6-column status mapping (depends: Phase 3) (category: code)
- [ ] Create KanbanColumn component with header, count badge, drop target (category: code)
- [ ] Create KanbanCard with Linear-style density - ref, title, priority border, badges (category: code)
- [ ] Implement drag-and-drop between columns using pragmatic-drag-and-drop (category: code)
- [ ] Add blocked task visual treatment - lock icon, dimmed opacity within status column (category: code)
- [ ] Add card hover quick actions - status change shortcuts (category: code)
- [ ] Add kanban CSS - board layout, column styling, card design, drag states (category: code)

## Phase 6: Task Tree

**Goal**: Build the hierarchy view for organizing complex goals with collapsible nodes.

**Tasks:**
- [ ] Create TaskTree component using react-arborist with custom node rendering (depends: Phase 3) (category: code)
- [ ] Implement tree node with status dot, ref, title, badges, child count (category: code)
- [ ] Add expand all, collapse all, show/hide closed controls (category: code)
- [ ] Add tree-specific search filtering (category: code)
- [ ] Add tree CSS - indentation, node styling, selected state (category: code)

## Phase 7: Live Status and Overview Panel

**Goal**: Show real-time agent activity across all tasks without digging into each one.

**Tasks:**
- [ ] Add WebSocket task_event subscription to useTasks hook for real-time updates (depends: Phase 5) (category: code)
- [ ] Create per-task status strip - agent name, current step, last action timestamp (depends: Phase 5) (category: code)
- [ ] Create global overview sections - Now, Stuck, Recently Completed with counts (depends: Phase 3) (category: code)
- [ ] Add activity pulse indicator on kanban cards showing live agent work (depends: Phase 5) (category: code)

## Phase 8: Transparent Reasoning and Actions

**Goal**: Make agent reasoning understandable without babysitting every token.

**Tasks:**
- [ ] Create reasoning timeline component - collapsed Plan/Investigate/Act/Verify phases (depends: Phase 3) (category: code)
- [ ] Create action feed component - tool calls with human-readable descriptions and results (category: code)
- [ ] Add session transcript viewer to TaskDetail linking to agent sessions (depends: Phase 3) (category: code)
- [ ] Add expandable raw trace view for debugging (category: code)

## Phase 9: Oversight and Escalation

**Goal**: Let users control agent autonomy per task and handle escalations smoothly.

**Tasks:**
- [ ] Add oversight mode selector to TaskDetail - hands-off, ask-before-risky, ask-each-step (depends: Phase 3) (category: code)
- [ ] Create escalation view showing agent options with pros/cons for user decision (depends: Phase 3) (category: code)
- [ ] Add intervention buttons per step - Retry, Edit and Run, Roll Back, Mark Resolved (depends: Phase 8) (category: code)
- [ ] Add de-escalation flow for returning escalated tasks to agents (category: code)

## Phase 10: Planning Views

**Goal**: Add Kanban swimlanes, priority views, and optional Gantt chart for time-bound planning.

**Tasks:**
- [ ] Add Kanban swimlanes - group by assignee, priority, or parent task (depends: Phase 5) (category: code)
- [ ] Create priority view - Now/Next/Later grouping (depends: Phase 5) (category: code)
- [ ] Add within-column card reordering with fractional indexing (depends: Phase 5) (category: code)
- [ ] Create Gantt chart view with timeline, dependency arrows, and milestones (depends: Phase 6) (category: code)
- [ ] Add drag-to-reschedule on Gantt bars (category: code)

## Phase 11: Results and Work Reports

**Goal**: Close the user's mental loop with clear visibility into what changed.

**Tasks:**
- [ ] Create per-task result area - summarized outcome, artifacts, PR links, commit diffs (depends: Phase 3) (category: code)
- [ ] Create daily/weekly digest view - completed, in-progress, needs-input summaries (depends: Phase 7) (category: code)
- [ ] Create per-agent portfolio view - work history, strengths, failure patterns (depends: Phase 7) (category: code)
- [ ] Add cost and token tracking display per task (depends: Phase 7) (category: code)

## Phase 12: Memory and Context

**Goal**: Make memory an explicit part of the task UX for trust and debugging.

**Tasks:**
- [ ] Add task-linked memory section to TaskDetail - memories read/written during work (depends: Phase 3) (category: code)
- [ ] Add memory correction UI - edit or pin memories from task context (category: code)
- [ ] Add re-run capability - clone task with new inputs or schedule recurring (depends: Phase 4) (category: code)
- [ ] Add learning-from-feedback display - show what agent will remember after corrections (category: code)

## Phase 13: Safety, Guardrails, and Trust

**Goal**: Surface risk, permissions, and audit information clearly.

**Tasks:**
- [ ] Add capability scope display to TaskDetail - active connections and permissions (depends: Phase 3) (category: code)
- [ ] Add risk indicator badges for sensitive actions - deploy, payments, data access (category: code)
- [ ] Create audit log view - immutable log of significant actions with approvals (depends: Phase 1) (category: code)
- [ ] Add per-task permission overrides with inline toggle switches (category: code)

## Phase 14: Collaboration

**Goal**: Support multi-user workflows with assignees, comments, and role-based views.

**Tasks:**
- [ ] Add assignee management - assign to human, agent, or joint ownership (depends: Phase 3) (category: code)
- [ ] Create threaded comments on tasks with @mentions (depends: Phase 1) (category: code)
- [ ] Add role-based default views - individual queue vs global overview (depends: Phase 5) (category: code)
- [ ] Add task handoff flow between humans and agents (depends: Phase 9) (category: code)

## Phase 15: Tree Re-parenting and Advanced DnD

**Goal**: Enable drag-and-drop re-parenting in tree view and advanced board interactions.

**Tasks:**
- [ ] Enable drag-and-drop re-parenting in TaskTree via react-arborist DnD (depends: Phase 6) (category: code)
- [ ] Add send-subtree-to-kanban - select a branch and surface leaf tasks as cards (depends: Phase 5, Phase 6) (category: code)
- [ ] Add dependency graph visualization using SVG and dagre layout engine (depends: Phase 6) (category: code)

## Task Mapping

| Plan Item | Task Ref | Status |
|-----------|----------|--------|
| **Epic: Task Management Web UI** | #7513 | open |
| **Phase 1: Backend REST API** | #7514 | open |
| Create task REST router with CRUD endpoints | #7529 | open |
| Add list tasks endpoint with filtering and stats | #7530 | open |
| Add task lifecycle endpoints - close, reopen | #7531 | open |
| Add task dependency endpoints - get tree, add, remove | #7532 | open |
| Register tasks router in HTTP server and routes __init__ | #7533 | open |
| Add broadcast_task_event to WebSocket broadcast mixin | #7534 | open |
| Wire task event broadcasting into REST route handlers | #7535 | open |
| **Phase 2: Frontend Data Layer** | #7515 | open |
| Install @atlaskit/pragmatic-drag-and-drop and react-arborist | #7536 | open |
| Create useTasks hook with fetch, CRUD, polling, and filters | #7537 | open |
| Wire TasksPage into App.tsx replacing ComingSoonPage | #7538 | open |
| **Phase 3: Core Layout and Task Detail** | #7516 | open |
| Create TasksPage shell with toolbar, view toggle, and filter bar | #7539 | open |
| Create shared TaskBadges | #7540 | open |
| Create TaskDetail slide-in panel | #7541 | open |
| Add status action buttons to TaskDetail | #7542 | open |
| Add dependency and hierarchy sections to TaskDetail | #7543 | open |
| Add validation info section to TaskDetail | #7544 | open |
| **Phase 4: Task Creation** | #7517 | open |
| Create TaskCreateForm modal | #7545 | open |
| Add quick-capture command palette entry | #7546 | open |
| Add context-aware defaults | #7547 | open |
| **Phase 5: Kanban Board** | #7518 | open |
| Create KanbanBoard component with 6-column status mapping | #7548 | open |
| Create KanbanColumn component | #7549 | open |
| Create KanbanCard with Linear-style density | #7550 | open |
| Implement drag-and-drop between columns | #7551 | open |
| Add blocked task visual treatment | #7552 | open |
| Add card hover quick actions | #7553 | open |
| Add kanban CSS | #7554 | open |
| **Phase 6: Task Tree** | #7519 | open |
| Create TaskTree component using react-arborist | #7555 | open |
| Implement tree node with status dot, ref, title, badges | #7556 | open |
| Add expand all, collapse all, show/hide closed controls | #7557 | open |
| Add tree-specific search filtering | #7558 | open |
| Add tree CSS | #7559 | open |
| **Phase 7: Live Status and Overview Panel** | #7520 | open |
| Add WebSocket task_event subscription to useTasks hook | #7560 | open |
| Create per-task status strip | #7561 | open |
| Create global overview sections - Now, Stuck, Recently Completed | #7562 | open |
| Add activity pulse indicator on kanban cards | #7563 | open |
| **Phase 8: Transparent Reasoning and Actions** | #7521 | open |
| Create reasoning timeline component | #7564 | open |
| Create action feed component | #7565 | open |
| Add session transcript viewer to TaskDetail | #7566 | open |
| Add expandable raw trace view for debugging | #7567 | open |
| **Phase 9: Oversight and Escalation** | #7522 | open |
| Add oversight mode selector to TaskDetail | #7568 | open |
| Create escalation view | #7569 | open |
| Add intervention buttons per step | #7570 | open |
| Add de-escalation flow | #7571 | open |
| **Phase 10: Planning Views** | #7523 | open |
| Add Kanban swimlanes | #7572 | open |
| Create priority view - Now/Next/Later | #7573 | open |
| Add within-column card reordering with fractional indexing | #7574 | open |
| Create Gantt chart view | #7575 | open |
| Add drag-to-reschedule on Gantt bars | #7576 | open |
| **Phase 11: Results and Work Reports** | #7524 | open |
| Create per-task result area | #7577 | open |
| Create daily/weekly digest view | #7578 | open |
| Create per-agent portfolio view | #7579 | open |
| Add cost and token tracking display per task | #7580 | open |
| **Phase 12: Memory and Context** | #7525 | open |
| Add task-linked memory section to TaskDetail | #7581 | open |
| Add memory correction UI | #7582 | open |
| Add re-run capability | #7583 | open |
| Add learning-from-feedback display | #7584 | open |
| **Phase 13: Safety, Guardrails, and Trust** | #7526 | open |
| Add capability scope display to TaskDetail | #7585 | open |
| Add risk indicator badges | #7586 | open |
| Create audit log view | #7587 | open |
| Add per-task permission overrides | #7588 | open |
| **Phase 14: Collaboration** | #7527 | open |
| Add assignee management | #7589 | open |
| Create threaded comments on tasks | #7590 | open |
| Add role-based default views | #7591 | open |
| Add task handoff flow | #7592 | open |
| **Phase 15: Tree Re-parenting and Advanced DnD** | #7528 | open |
| Enable drag-and-drop re-parenting in TaskTree | #7593 | open |
| Add send-subtree-to-kanban | #7594 | open |
| Add dependency graph visualization | #7595 | open |
