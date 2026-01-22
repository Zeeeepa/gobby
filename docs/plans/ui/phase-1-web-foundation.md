# Phase 1: Web Dashboard Foundation

> **Framework:** Next.js 14+ with shadcn/ui
> **Goal:** Full-featured web UI foundation with component library
> **Depends on:** Phase 0 (TUI validates interaction patterns)

## 1.1 Project Setup

### 1.1.1 Initialize Next.js

- [ ] Create `ui/` directory in gobby repo root
- [ ] Initialize Next.js 14 with App Router: `npx create-next-app@latest ui --typescript --tailwind --eslint --app`
- [ ] Remove default boilerplate pages
- [ ] Configure TypeScript strict mode
- [ ] Add path aliases (`@/components`, `@/lib`, `@/hooks`)

### 1.1.2 Design System Integration

- [ ] Copy Tailwind config from `docs/design/tailwind.config.ts`
- [ ] Install Inter and JetBrains Mono fonts
- [ ] Create CSS custom properties for design tokens
- [ ] Set up dark mode as default (class strategy)

### 1.1.3 Component Library

- [ ] Install shadcn/ui: `npx shadcn-ui@latest init`
- [ ] Add core components: Button, Input, Card, Dialog, DropdownMenu
- [ ] Add data components: Table, Badge, Tabs
- [ ] Add feedback components: Toast, Skeleton, Progress
- [ ] Install Phosphor icons: `npm install @phosphor-icons/react`

### 1.1.4 Development Tooling

- [ ] Configure ESLint with Next.js rules
- [ ] Set up Prettier with Tailwind plugin
- [ ] Add `ui:dev` script to root package.json
- [ ] Create `.env.local` with `NEXT_PUBLIC_DAEMON_URL=http://localhost:8765`

## 1.2 Static File Serving

### 1.2.1 Daemon Integration

- [ ] Add `/ui` static file route to FastAPI in `src/gobby/servers/http.py`
- [ ] Configure StaticFiles to serve from `ui/out/` (exported Next.js)
- [ ] Handle SPA routing: all `/ui/*` routes serve `index.html`
- [ ] Add CORS headers for development mode

### 1.2.2 Build Pipeline

- [ ] Add `next.config.js` with `output: 'export'` for static export
- [ ] Create build script: `cd ui && npm run build`
- [ ] Add `gobby ui --web` CLI command to open browser at `http://localhost:8765/ui`
- [ ] Add build step to `uv run gobby build` command

## 1.3 Core Layout

### 1.3.1 App Shell

- [ ] Create root layout with sidebar and main content area
- [ ] Implement collapsible sidebar navigation
- [ ] Add navigation items: Dashboard, Tasks, Sessions, Worktrees, MCP, Memory
- [ ] Create header with breadcrumbs and global actions
- [ ] Add footer with daemon version and status

### 1.3.2 Navigation

- [ ] Implement `NavItem` component with icon and label
- [ ] Add active state styling
- [ ] Create keyboard shortcut hints (Cmd+1 through Cmd+6)
- [ ] Implement route-based navigation with App Router

### 1.3.3 Placeholder Views

- [ ] Create placeholder page for each route
- [ ] Add "Coming Soon" state with phase information
- [ ] Implement loading skeletons for each view

## 1.4 API Client

### 1.4.1 HTTP Client

- [ ] Create `lib/api/client.ts` with typed fetch wrapper
- [ ] Implement base URL configuration from env
- [ ] Add error handling with typed error responses
- [ ] Create retry logic for transient failures

### 1.4.2 React Query Setup

- [ ] Install TanStack Query: `npm install @tanstack/react-query`
- [ ] Create QueryClientProvider in root layout
- [ ] Configure default stale time and cache time
- [ ] Add React Query DevTools for development

### 1.4.3 API Hooks

- [ ] Create `useAdminStatus` hook for daemon health
- [ ] Create `useTasks` hook with filters
- [ ] Create `useSessions` hook with filters
- [ ] Create `useMCPServers` hook
- [ ] Create `useMemories` hook with search

### 1.4.4 MCP Tool Client

- [ ] Create `callTool` function for MCP tool execution
- [ ] Add TypeScript types for all internal MCP tools
- [ ] Create mutation hooks for tool calls (useCreateTask, etc.)
- [ ] Handle tool call errors with toast notifications

### 1.4.5 Global State

- [ ] Install Zustand: `npm install zustand`
- [ ] Create `useUIStore` for UI preferences (sidebar collapsed, theme)
- [ ] Create `useDaemonStore` for connection state
- [ ] Persist UI preferences to localStorage

## 1.5 Dashboard View (MVP)

### 1.5.1 Active Agents Section

- [ ] Create `AgentSummaryCard` component
- [ ] Display agent count by provider (Claude, Gemini, Codex)
- [ ] Show provider icon and color
- [ ] Link to Agents view

### 1.5.2 Quick Stats Section

- [ ] Create `StatCard` component with icon, label, value
- [ ] Display task counts (open, ready, in progress)
- [ ] Display worktree counts (active, stale)
- [ ] Display MCP server counts (connected, tools)

### 1.5.3 Ready Work Section

- [ ] Create `ReadyTaskList` component
- [ ] Show top 5 ready tasks by priority
- [ ] Display task ID, title, type badge
- [ ] Add "View All" link to Tasks view
- [ ] Click task to navigate to detail

### 1.5.4 Recent Activity Section

- [ ] Create `ActivityFeed` component
- [ ] Display last 10 events (task closed, session started, etc.)
- [ ] Show timestamp and event description
- [ ] Add "View All" link to Sessions view

## 1.6 Tasks View (Basic)

### 1.6.1 Task List

- [ ] Create `TasksPage` with list view
- [ ] Implement DataTable with columns: Status, ID, Title, Type, Priority
- [ ] Add status filter dropdown
- [ ] Add type filter dropdown
- [ ] Add search input for title filtering

### 1.6.2 Task Row

- [ ] Create `TaskRow` component with status badge
- [ ] Add task type badge with color coding
- [ ] Display priority as dots (P1=3 dots, P4=0 dots)
- [ ] Show truncated description on hover

### 1.6.3 Task Detail Sheet

- [ ] Create `TaskDetailSheet` slide-out panel
- [ ] Display all task fields
- [ ] Show dependency list
- [ ] Add action buttons (Edit, Expand, Close)

## 1.7 Sessions View (Basic)

### 1.7.1 Session List

- [ ] Create `SessionsPage` with timeline layout
- [ ] Group sessions by date
- [ ] Display provider badge, title, duration
- [ ] Show token count and cost

### 1.7.2 Session Row

- [ ] Create `SessionRow` component
- [ ] Display provider icon with color
- [ ] Show linked task if any
- [ ] Display status indicator

## 1.8 Settings View

- [ ] Create `SettingsPage` with form sections
- [ ] Add daemon connection settings
- [ ] Add UI preferences (theme, sidebar default)
- [ ] Add keyboard shortcut customization
- [ ] Store settings in localStorage and sync to daemon config
