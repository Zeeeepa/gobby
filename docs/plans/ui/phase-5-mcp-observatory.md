# Phase 5: MCP Observatory

> **Framework:** Web UI + daemon metrics
> **Goal:** Tool analytics, server management, semantic search
> **Depends on:** Phase 4 (Agent Orchestrator)

## 5.1 Server List View

### 5.1.1 Server Table

- [ ] Create `MCPServersPage` with DataTable
- [ ] Add columns: Status, Name, Transport, Tools, Calls (24h)
- [ ] Color status indicators (connected=green, reconnecting=yellow, disabled=gray)
- [ ] Sort by call count (most used first)
- [ ] Show internal servers (gobby-*) separately

### 5.1.2 Server Row

- [ ] Create `ServerRow` component
- [ ] Display transport type icon (HTTP, stdio, WebSocket)
- [ ] Show tool count badge
- [ ] Display connection duration
- [ ] Add quick actions (Refresh, Disconnect)

### 5.1.3 Filters

- [ ] Filter by status (connected, disconnected, disabled)
- [ ] Filter by transport type
- [ ] Search by server name
- [ ] Toggle internal/external servers

## 5.2 Server Actions

### 5.2.1 Add Server Dialog

- [ ] Create `AddServerDialog` modal
- [ ] Name input (required, unique)
- [ ] Transport selector (HTTP, stdio, WebSocket)
- [ ] URL input (for HTTP/WebSocket)
- [ ] Command/args inputs (for stdio)
- [ ] Headers input (for HTTP with auth)
- [ ] Enabled checkbox

### 5.2.2 Server Operations

- [ ] "Refresh Tools" button (re-fetches tool list)
- [ ] "Disconnect" button (temporary disable)
- [ ] "Remove" button with confirmation
- [ ] "Enable/Disable" toggle

### 5.2.3 Import Server

- [ ] Create `ImportServerDialog` modal
- [ ] Import from GitHub URL (parse README)
- [ ] Import from another project
- [ ] Show preview before import
- [ ] Edit before adding

## 5.3 Tool Analytics

### 5.3.1 Analytics Dashboard

- [ ] Create `ToolAnalytics` component
- [ ] Show time period selector (1h, 24h, 7d, 30d)
- [ ] Display total calls, success rate, avg latency
- [ ] Add export button (CSV)

### 5.3.2 Top Tools Chart

- [ ] Create horizontal bar chart (Recharts)
- [ ] Show top 10 tools by call count
- [ ] Display server name in label
- [ ] Color by success rate

### 5.3.3 Failure Analysis

- [ ] Show failing tools table
- [ ] Display failure count and rate
- [ ] Show last error message
- [ ] Link to tool detail

### 5.3.4 Latency Distribution

- [ ] Create latency histogram
- [ ] Show p50, p90, p99 lines
- [ ] Filter by server
- [ ] Highlight outliers

## 5.4 Server Detail

### 5.4.1 Server Detail Sheet

- [ ] Create `ServerDetailSheet` slide-out
- [ ] Show connection metadata
- [ ] Display configuration (URL, command, headers)
- [ ] Show uptime and reconnection count

### 5.4.2 Tool List

- [ ] List all tools for server
- [ ] Show tool name and description
- [ ] Display call count and success rate
- [ ] Click to expand schema

### 5.4.3 Tool Schema View

- [ ] Create `ToolSchemaView` component
- [ ] Display inputSchema as formatted JSON
- [ ] Show parameter descriptions
- [ ] Add "Copy Schema" button
- [ ] Add "Test Tool" button (future)

## 5.5 Tool Call Log

### 5.5.1 Call Log Table

- [ ] Create `ToolCallLog` component
- [ ] Columns: Time, Server, Tool, Session, Duration, Status
- [ ] Filter by server, tool, session
- [ ] Filter by status (success, error)
- [ ] Paginate results

### 5.5.2 Call Detail

- [ ] Create `CallDetailModal` modal
- [ ] Show request arguments (formatted JSON)
- [ ] Show response (formatted JSON, truncated)
- [ ] Display error message if failed
- [ ] Show timing breakdown

### 5.5.3 Export

- [ ] Export call log as JSON
- [ ] Export call log as CSV
- [ ] Filter export by date range

## 5.6 Semantic Search

### 5.6.1 Tool Search

- [ ] Create search input in MCP view header
- [ ] Call `/mcp/tools/search` on input
- [ ] Show results ranked by similarity
- [ ] Display similarity score
- [ ] Highlight matching terms

### 5.6.2 Tool Recommendations

- [ ] Create `ToolRecommendations` component
- [ ] Input task description
- [ ] Call `/mcp/tools/recommend`
- [ ] Show recommended tools with usage hints
- [ ] Group by server

## 5.7 Daemon Metrics

### 5.7.1 MCP Health Panel

- [ ] Add MCP section to dashboard
- [ ] Show server connection status summary
- [ ] Display total tools available
- [ ] Show recent call rate (calls/minute)

### 5.7.2 Error Alerts

- [ ] Show alert for high error rate (>10%)
- [ ] Show alert for disconnected servers
- [ ] Link to affected server
- [ ] Dismiss/snooze alerts
