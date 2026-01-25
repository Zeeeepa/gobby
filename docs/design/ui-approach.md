# Gobby UI Approach

## Executive Summary

Gobby needs a UI strategy that serves power users in terminals while enabling remote access from mobile devices. We'll build **TUI-first** to validate patterns, then port learnings to a **PWA web UI** that works on phones.

---

## UI Tiers

### Tier 1: TUI Dashboard (MVP Priority)

**Why TUI first:**
- Users are already in terminals (Claude Code, Gemini CLI)
- Low friction - check status without leaving workflow
- Validates which views matter most
- Fast to iterate

**Framework**: [Textual](https://textual.textualize.io/) (Python)
- Native Python (consistent with Gobby backend)
- CSS-like styling maps to design tokens
- Hot reload during development
- Can export to web later via textual-web

**Command structure:**
```bash
gobby ui                    # Launch full TUI
gobby ui tasks              # Tasks view directly
gobby ui sessions           # Sessions view
gobby ui agents             # Agent monitoring
```

### Tier 2: PWA Web Dashboard

**Why PWA:**
- Works on phone (your remote access requirement)
- Offline support for status checking
- Push notifications for agent completion
- Install to home screen
- Single codebase for desktop/mobile

**Framework**: Next.js 14+ with:
- shadcn/ui components
- Tailwind CSS (using our config)
- TanStack Query for data
- Native WebSocket to daemon

**Hosting**: Local daemon serves web UI on port 60336
- `gobby ui --web` opens browser
- Or access from phone on same network
- Optional: Cloudflare tunnel for remote access

### Tier 3: Desktop App (Future)

Tauri wrapper around web UI if native features needed later.

---

## Critical User Flows

### Flow 1: Task Selection (Most Important)

**Current pain**: Copy/paste task IDs between tmux sessions, type `/gobby:workflows auto-task session_task=gt-123456`

**TUI solution**:
```
┌─ GOBBY TASKS ──────────────────────────────────────────────┐
│  [Ready]  gt-abc123  Add user auth        feature  ●●○    │
│  [Ready]  gt-def456  Fix login bug        bug      ●●●    │
│> [Ready]  gt-ghi789  Update docs          chore    ●○○    │ ← cursor here
│  ─────────────────────────────────────────────────────────│
│  [Blocked] gt-xyz... Refactor API         task     ●●○    │
│            └─ waiting on gt-abc123                        │
└───────────────────────────────────────────────────────────┘
 [Enter] Start  [Space] Details  [D] Dependencies  [N] New
```

**Actions**:
- `Enter` on task → sets `session_task` variable, copies ID to clipboard
- Automatic workflow activation
- No more manual typing

### Flow 2: Agent Monitoring from Phone

**Use case**: Walking dog, want to check if agent finished

**Mobile PWA**:
```
┌─────────────────────────────────┐
│  GOBBY          🟢 Connected    │
├─────────────────────────────────┤
│  AGENTS (2 running)             │
│  ┌─────────────────────────────┐│
│  │ 🟡 Implementing auth...     ││
│  │    Claude • 12 tools • 4m   ││
│  │    [Cancel]                 ││
│  └─────────────────────────────┘│
│  ┌─────────────────────────────┐│
│  │ 🟡 Writing tests...         ││
│  │    Gemini • 8 tools • 2m    ││
│  │    [Cancel]                 ││
│  └─────────────────────────────┘│
│                                 │
│  RECENT (tap to expand)         │
│  ✅ gt-abc123 closed 15m ago    │
│  ✅ gt-def456 closed 1h ago     │
└─────────────────────────────────┘
```

**Features**:
- Push notification when agent completes
- One-tap cancel
- Minimal info, optimized for quick glance
- Works offline (shows last known state)

### Flow 3: Session Handoff

**Use case**: Resume work on different machine

**TUI**:
```
┌─ SESSIONS ─────────────────────────────────────────────────┐
│  Today                                                     │
│  ─────────────────────────────────────────────────────────│
│  10:34  Claude Code  "Implemented auth feature"           │
│         gt-abc123 • 12.4k tokens • $0.08                  │
│         [P] Pickup  [S] Summary  [T] Transcript           │
│                                                           │
│  09:15  Gemini CLI   "Fixed test suite"                   │
│         gt-xyz789 • 8.2k tokens • $0.03                   │
│                                                           │
└───────────────────────────────────────────────────────────┘
```

**Actions**:
- `P` → Copies handoff context to clipboard
- `S` → Shows summary markdown
- `T` → Opens transcript in pager

---

## Screen Specifications

### 1. Task Kanban (Priority 1)

**Columns**:
- Ready (green header)
- In Progress (blue header)
- Blocked (red header)
- Done (collapsed, gray)

**Task Card**:
```
┌────────────────────────┐
│ gt-abc123              │ ← monospace ID, clickable
│ Add user auth          │ ← title, truncated
│ feature ●●○            │ ← type badge + priority dots
│ 3 subtasks • 2h ago    │ ← meta line
└────────────────────────┘
```

**Interactions**:
- Drag between columns (web only)
- Arrow keys to navigate (TUI)
- Enter to expand details
- D to show dependency tree

### 2. Session Timeline (Priority 2)

**Layout**: Vertical timeline, newest first

**Session Row**:
```
10:34 AM  ● Claude Code   "Implemented auth feature"
          │ gt-abc123     12.4k tokens  $0.08
          │ └─ Agent [depth:1] → completed
```

**Color coding**:
- Claude: Orange dot
- Gemini: Blue dot
- Codex: Green dot

### 3. Workflow Designer (Priority 3)

**For later**: Visual step editor, but MVP can be YAML-based

### 4. Agent Tree (Priority 4)

**Layout**: Tree view showing spawn hierarchy

```
┌─ Primary Session ───────────────────────────────────────┐
│ "Implement feature X"                                   │
│ Claude • [████████░░] 8/10 tools                       │
│                                                        │
│    ├─ Agent 1 ────────────────────────────────────────│
│    │ "Write tests" • Gemini • Complete ✓              │
│    │                                                   │
│    └─ Agent 2 ────────────────────────────────────────│
│      "Generate docs" • Claude • [█████░░░░░] Running  │
│                                                        │
│      └─ Agent 2.1 ───────────────────────────────────│
│        "Format markdown" • Haiku • Pending            │
└────────────────────────────────────────────────────────┘
```

### 5. Memory Graph (Priority 5)

Already have `viz.py` generating HTML. Integrate into TUI via:
- `M` key opens memory browser
- `/` to search
- `G` to open graph in browser

### 6. Metrics Dashboard (Priority 6)

**Panels**:
- Session count (sparkline)
- Token usage (bar chart)
- Cost (cumulative line)
- Tool success rates (horizontal bars)
- P99 latencies (table)

---

## Data Flow

```
                    ┌─────────────┐
                    │   TUI App   │
                    │  (Textual)  │
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
         ▼                 ▼                 ▼
    ┌─────────┐       ┌─────────┐       ┌─────────┐
    │ :60887  │       │ :60888  │       │ :60336  │
    │ REST    │       │ WS      │       │ Web UI  │
    │ API     │       │ Events  │       │ (PWA)   │
    └────┬────┘       └────┬────┘       └────┬────┘
         │                 │                 │
         └────────┬────────┴─────────────────┘
                  ▼
           ┌───────────┐
           │  Daemon   │
           │ (FastAPI) │
           └───────────┘
```

**Real-time events**:
- `task:created`, `task:updated`, `task:closed`
- `session:started`, `session:ended`
- `agent:spawned`, `agent:completed`, `agent:failed`
- `tool:called` (for live tool counter)

---

## Remote Access Options

### Option A: Local Network (Simple)
- Daemon binds to `0.0.0.0:60336`
- Access from phone on same WiFi
- Pro: No setup
- Con: Only works on same network

### Option B: Cloudflare Tunnel (Recommended)
- `gobby tunnel start` creates secure tunnel
- Access from anywhere via `https://gobby-<hash>.trycloudflare.com`
- Pro: Works anywhere, secure
- Con: Requires internet

### Option C: Tailscale/Zerotier
- VPN to home network
- Pro: Secure, always works
- Con: Requires Tailscale setup

**Recommendation**: Support all three, default to local network, document others.

---

## Implementation Phases

### Phase 1: TUI Foundation (Week 1)
- [ ] Textual app skeleton with navigation
- [ ] Tasks list view (table, not kanban)
- [ ] Task detail panel
- [ ] Basic keyboard shortcuts
- [ ] Connect to REST API

### Phase 2: TUI Complete (Week 2)
- [ ] Session timeline view
- [ ] Agent tree view
- [ ] Memory search (text-based)
- [ ] Metrics summary
- [ ] WebSocket integration for live updates

### Phase 3: Web PWA (Week 3)
- [ ] Next.js skeleton
- [ ] Task kanban with shadcn
- [ ] Mobile-responsive layout
- [ ] Service worker for offline
- [ ] Push notifications

### Phase 4: Mobile Polish (Week 4)
- [ ] Touch-optimized interactions
- [ ] Reduced information density
- [ ] Quick actions (cancel agent, etc.)
- [ ] Tunnel setup flow

---

## Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| TUI Framework | Textual | Python-native, good widgets, hot reload |
| Web Framework | Next.js 14 | SSR, good mobile story, Vercel patterns |
| Component Library | shadcn/ui | Accessible, matches design system |
| State Management | TanStack Query | Built-in caching, real-time sync |
| Real-time | Native WebSocket | Already have port 60888 |
| Mobile | PWA | No app store, works offline, push notifications |
| Remote Access | Cloudflare Tunnel | Secure, free, no port forwarding |

---

## Open Questions

1. **Should TUI and Web share any code?**
   - Textual-web could render TUI in browser, but limited
   - Or keep separate and share API contracts only

2. **How to handle offline on mobile?**
   - Cache last known state
   - Queue actions (cancel agent) for sync
   - Show stale indicator

3. **Authentication for remote access?**
   - Daemon-generated token?
   - Passkey/biometric?
   - Just trust the tunnel?

4. **Should metrics be real-time or polled?**
   - Real-time adds WS complexity
   - Polling every 5s might be enough

---

## Success Metrics

1. **Task selection time**: < 3 seconds from TUI open to task started
2. **Mobile check time**: < 5 seconds to see agent status from phone
3. **Session pickup**: < 10 seconds to get handoff context
4. **Keyboard coverage**: 100% of actions available via keyboard
