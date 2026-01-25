# Gobby UI v2: The AgentCMD Transplant

**Status**: Planning
**Strategy**: UI Transplant ("Frontend Lobotomy")
**Source**: [jnarowski/agentcmd](https://github.com/jnarowski/agentcmd)

## Executive Summary
We are adopting the high-quality React/Vite frontend from `agentcmd` to serve as the official Gobby GUI. Instead of integrating with their complex backend or using their workflow engine, we will perform a "surgical transplant": preserving their UI components while replacing their network and state management layers to communicate directly with the local Gobby Daemon.

## Goal
Deliver a premium, "Chat-IDE" experience for Gobby without building it from scratch.

## Architecture: The "Transplant"
We fork the `agentcmd` frontend and replace its "Brain" (API/Hooks) while keeping its "Skin" (Components).

| Component | Status | Replacement |
| :--- | :--- | :--- |
| **UI Components** | ✅ Keep | N/A |
| **Pages/Layout** | ✅ Keep | N/A |
| **Network Layer** | ❌ Discard | `GobbyClient` (Fetch wrapper) |
| **Chat Protocol** | ❌ Discard | `useGobbyChat` (HTTP Stream) |
| **Slash Commands** | 🔄 Rewire | `useGobbyCommands` (MCP + Skills) |
| **Workflow Engine** | ❌ Remove | Gobby Task System |
| **Authentication** | ❌ Remove | Local Daemon Auth |

## Functionality Breakdown

### 1. Unified Command Menu
The `/` menu is the primary interface for agent capabilities. It aggregates three sources into a single filtered list:
1.  **Upstream MCP Tools**: From external servers (e.g., `filesystem`, `github`).
2.  **Internal Gobby Tools**: From Gobby's proxy (e.g., `gobby-tasks`, `context7`).
3.  **Skills**: from `gobby-skills` (e.g., `/skill:react-expert`), allowing users to inject knowledge/instructions.

### 2. Chat Interface
-   **Transport**: HTTP POST for sending, HTTP Streaming (SSE-like) for receiving.
-   **History**: Loads persistent session transcripts (`#123`) from Gobby's database.
-   **Rendering**: Supports Markdown, Code Blocks, and specialized "Artifact" rendering where compatible.

### 3. Session Management
-   Sidebar integration with Gobby's existing session list.
-   Ability to create, switch, and archive sessions.

## Implementation Plan

### Phase 1: Clone & Strip ("The Lobotomy")
1.  Clone `agentcmd`.
2.  Delete `apps/app/src/server` (The Node.js Backend).
3.  Sanitize `apps/app/src/client`:
    -   Remove `ApiClient` (Auth/Rest wrapper).
    -   Remove `useWebSocket` (Proprietary socket protocol).
    -   Remove `sessionStore` (Zustand store coupled to backend types).

### Phase 2: The Gobby Wiring
1.  **SDK**: Create `src/client/gobby/client.ts` to talk to `localhost:DAEMON_PORT`.
2.  **State**: Create `useGobbyChat` hook.
    -   Maps Gobby `TranscriptItem` -> UI `Message` components.
    -   Handles streaming responses.

### Phase 3: Capability Wiring
1.  **Slash Commands**: Wire `CommandMenu` to `mcp_proxy.list_tools` and `skills.list_skills`.
2.  **Terminal**: Disable/Hide the specific `Terminal` tab for V1 (or wire to simple daemon stream).

### Phase 4: Polish & Branding
1.  Remove "AgentCMD" branding.
2.  Update colors/logos to match Gobby identity.
3.  Build static assets (`vite build`) and serve via Gobby's `web-host`.

## Technical Risks
-   **Type Coupling**: UI components might rely on shared Zod schemas from the backend.
    -   *Mitigation*: We will generate a `types.d.ts` that mocks these shapes based on UI usage.
-   **Complex Components**: The `ChatInterface` might have deep logic for "Optimistic Updates" that breaks without the real store.
    -   *Mitigation*: We will simplify to a "Single Source of Truth" model where the UI renders exactly what the Gobby stream sends.
