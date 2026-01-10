# Phase 2: Real-time Updates

> **Framework:** WebSocket + React Query
> **Goal:** Live updates without polling
> **Depends on:** Phase 1 (Web Foundation)

## 2.1 WebSocket Infrastructure

### 2.1.1 WebSocket Client

- [ ] Create `lib/ws/client.ts` WebSocket client class
- [ ] Implement auto-reconnect with exponential backoff
- [ ] Add connection state tracking (connecting, connected, disconnected)
- [ ] Parse incoming JSON messages with type guards
- [ ] Queue messages during reconnection

### 2.1.2 Event Types

- [ ] Define TypeScript types for all WebSocket events
- [ ] Create `HookEvent` interface for hook events
- [ ] Create `AgentEvent` interface for agent lifecycle
- [ ] Create `AutonomousEvent` interface for autonomous loops
- [ ] Create `SessionMessageEvent` interface for streaming

### 2.1.3 Subscription Manager

- [ ] Create `useWebSocket` hook for connection management
- [ ] Implement `subscribe(events[])` method
- [ ] Implement `unsubscribe(events[])` method
- [ ] Track active subscriptions to resubscribe on reconnect

## 2.2 Daemon Event Emission

### 2.2.1 Task Events

- [ ] Emit `task.created` from `create_task` MCP tool
- [ ] Emit `task.updated` from `update_task` MCP tool
- [ ] Emit `task.closed` from `close_task` MCP tool
- [ ] Emit `task.expanded` from `expand_task` MCP tool
- [ ] Add task_id and project_id to all events

### 2.2.2 Worktree Events

- [ ] Emit `worktree.created` from `create_worktree` MCP tool
- [ ] Emit `worktree.updated` from `claim_worktree`, `release_worktree`
- [ ] Emit `worktree.merged` from merge operations
- [ ] Emit `worktree.deleted` from cleanup operations

### 2.2.3 MCP Events

- [ ] Emit `mcp.server_connected` on successful connection
- [ ] Emit `mcp.server_disconnected` on connection loss
- [ ] Emit `mcp.tool_called` for metrics (optional, high volume)
- [ ] Include server_name and tool counts

## 2.3 React Query Integration

### 2.3.1 Cache Invalidation

- [ ] Create `useEventHandler` hook for event processing
- [ ] Invalidate `tasks` query on task events
- [ ] Invalidate `sessions` query on session events
- [ ] Invalidate `agents` query on agent events
- [ ] Invalidate `mcp-servers` query on MCP events

### 2.3.2 Optimistic Updates

- [ ] Implement optimistic update for task status changes
- [ ] Implement optimistic update for task creation
- [ ] Roll back on error with toast notification
- [ ] Show pending state in UI

### 2.3.3 Live Data Hooks

- [ ] Create `useTasksLive` hook that combines query + events
- [ ] Create `useSessionsLive` hook
- [ ] Create `useAgentsLive` hook
- [ ] Create `useMCPServersLive` hook

## 2.4 UI Feedback

### 2.4.1 Toast Notifications

- [ ] Show toast on task created
- [ ] Show toast on task closed
- [ ] Show toast on agent completed/failed
- [ ] Show toast on connection lost/restored
- [ ] Make toasts dismissible and auto-expire

### 2.4.2 Loading States

- [ ] Add skeleton loaders for all data views
- [ ] Show connection status in header
- [ ] Add reconnecting indicator
- [ ] Show stale data indicator when disconnected

### 2.4.3 Activity Indicator

- [ ] Create `ActivityPulse` component for active agents
- [ ] Show real-time tool call count
- [ ] Animate on new events
- [ ] Display in dashboard and agent views

## 2.5 Connection Management

### 2.5.1 Health Monitoring

- [ ] Ping daemon every 30 seconds
- [ ] Show connection quality indicator
- [ ] Log connection events for debugging
- [ ] Handle daemon restart gracefully

### 2.5.2 Offline Support

- [ ] Cache last known state in localStorage
- [ ] Show cached data when disconnected
- [ ] Queue mutations for retry on reconnect
- [ ] Clear stale cache on successful reconnect
