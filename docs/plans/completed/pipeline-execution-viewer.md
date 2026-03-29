# Pipeline Execution Live Feed & Progress Bar

## Context

Pipeline executions currently have no UI visibility. Users must manually poll cron runs or watch terminal output. The WebSocket broadcast infrastructure (`pipeline_event` type) and REST API endpoints already exist — this task adds the UI consumer.

## Design Direction

**GitHub Actions workflow viewer** pattern: left sidebar lists runs with status icons, right panel shows step-by-step detail with expandable log output. Data-dense, functional, monospace timing data. Not a dashboard — a **workflow monitor**.

Key visual choices:
- **Left panel**: Compact run list with status dot, pipeline name, duration, relative time. Active runs pulse. Selected run highlighted with accent border.
- **Right panel**: Step list styled like GitHub Actions job steps — vertical list with status icons, step names, durations. Each step expandable to show output/error. Running step has animated spinner. Failed steps show inline error with red left border.
- **Bottom dock**: Live event feed (terminal-style, monospace, auto-scrolling). Collapsible.
- **Approval gates**: Inline amber banner at the step level with Approve/Reject buttons.
- **Progress**: Thin horizontal bar at the top of the detail panel (not a big chunky bar). Step N of M as text label.
- **Typography**: `var(--font-mono)` for IDs, durations, timestamps. Sans-serif for names/labels.
- **Colors**: Match existing CSS vars — `#3b82f6` running, `#22c55e` completed, `#ef4444` failed, `#f59e0b` waiting, `var(--text-muted)` pending/skipped.

## Files to Create (7)

All in `web/src/components/pipelines/`:

### 1. `RunList.tsx`
Left sidebar listing pipeline executions. Each row:
- Status dot (colored circle, animated pulse for running)
- Pipeline name (truncated, bold)
- Duration or "running..." in mono
- Relative time ("2m ago")
- Click to select, selected state = left accent border + bg highlight
- Active runs sorted to top, visual separator before completed/failed runs
- Status filter tabs at top: All | Active | Completed | Failed

### 2. `StepList.tsx`
GitHub Actions-style vertical step list. Each step is a row:
- Status icon: green checkmark (completed), red X (failed), animated spinner (running), gray circle (pending), skip arrow (skipped), amber clock (waiting_approval)
- Step name
- Duration right-aligned in mono (`12.4s`, `1m 23s`)
- Expandable: click to toggle output/error panel below
- Running step has subtle background pulse animation
- Failed step: red left border, error message shown expanded by default
- Skipped step: dimmed text, skip reason in muted italic
- Connecting vertical line on left side between step icons

### 3. `ApprovalBanner.tsx`
Inline approval UI rendered within the StepList when a step is `waiting_approval`:
- Amber left border + subtle amber background
- Approval message text
- "Approve" (green) and "Reject" (red) buttons, compact
- Loading spinner on button during request
- Calls `approvePipeline`/`rejectPipeline` from hook

### 4. `EventFeed.tsx`
Terminal-style scrollable log panel (docked at bottom, collapsible):
- Monospace font, dark background (`var(--code-bg)`)
- Each line: `HH:MM:SS.mmm  [event_type]  step_name  details`
- Color-coded: green=completed, red=failed, amber=approval, blue=started, gray=skipped
- Auto-scroll to bottom unless user scrolled up (scroll-lock detection)
- "Clear" button and execution filter toggle
- Capped at 200 entries in memory
- Collapse/expand toggle with chevron

### 5. `ExecutionDetail.tsx`
Right panel for the selected execution:
- **Header**: Pipeline name (large), execution ID in mono (small), status badge, total duration
- **Thin progress bar**: Full-width, thin (3px), colored by status, shows step completion %
- **Step N of M** text label below progress bar
- **StepList** component
- **Collapsible sections**: "Inputs" and "Outputs" with JSON pretty-printed in code blocks
- **Metadata footer**: Cron trigger info, session ID, created timestamp
- Empty state when no execution selected: "Select a run to view details"

### 6. `PipelinesPage.tsx`
Top-level page component orchestrating everything:
- **Layout**: CSS Grid — left column (280px) for RunList, right column (flex) for ExecutionDetail, bottom dock for EventFeed
- **Toolbar**: "Pipelines" title, search input for filtering by name
- Uses enhanced `usePipelineExecutions` hook
- Manages selected execution state
- Passes event feed data and filter to EventFeed
- Empty state when no executions exist at all

### 7. `PipelinesPage.css`
All styles for the pipeline page:
- `.pl-page` root grid layout (sidebar + detail + feed dock)
- `.pl-run-list` sidebar styles, `.pl-run-item` compact row styles
- `.pl-detail` right panel styles
- `.pl-step` step row styles with expandable output
- `.pl-step-line` vertical connecting line
- `.pl-progress-bar` thin animated bar (CSS transition on width)
- `.pl-feed` terminal-style log panel
- `.pl-approval` amber banner styles
- `@keyframes pl-pulse` for running status animation
- `@keyframes pl-spin` for step spinner
- Responsive: stack vertically on narrow screens
- Light theme overrides via `[data-theme="light"]`

## Files to Modify (2)

### 8. `web/src/hooks/usePipelineExecutions.ts`
Enhance existing hook:
- **Add event log buffer**: `pipelineEvents` state (capped at 200). Second `useWebSocketEvent("pipeline_event", ...)` callback that appends raw events as `{ event, execution_id, timestamp, ...payload }`.
- **Add `getExecution(id)`**: Fetches `GET /api/pipelines/{execution_id}` for full step detail when selecting a run.
- **New return values**: `pipelineEvents`, `getExecution`

Existing debounce refetch on WS events stays as-is — it handles state sync on reconnect and keeps the run list fresh.

### 9. `web/src/App.tsx`
- **Lazy import** (after line 89):
  ```typescript
  const PipelinesPage = lazy(() =>
    import("./components/pipelines/PipelinesPage").then((m) => ({
      default: m.PipelinesPage,
    })),
  );
  ```
- **Nav item** (after "Cron Jobs" at line 910):
  ```typescript
  { id: "pipelines", label: "Pipelines", icon: <PipelinesIcon /> },
  ```
- **Page branch** (after cron branch ~line 1114):
  ```typescript
  ) : activeTab === "pipelines" ? (
    <PipelinesPage projectId={effectiveProjectId} />
  ```
- **PipelinesIcon** SVG (play-circle or workflow icon)

## Implementation Order

1. `PipelinesPage.css` — all styles first (referenced by everything)
2. `ApprovalBanner.tsx` — no deps
3. `StepList.tsx` — uses ApprovalBanner
4. `EventFeed.tsx` — standalone
5. `usePipelineExecutions.ts` — add event buffer + getExecution
6. `RunList.tsx` — uses hook data
7. `ExecutionDetail.tsx` — uses StepList
8. `PipelinesPage.tsx` — orchestrates everything
9. `App.tsx` — wire in page

## Key References

| What | File |
|---|---|
| WebSocket hook pattern | `web/src/hooks/useWebSocketEvent.ts` |
| Existing pipeline hook | `web/src/hooks/usePipelineExecutions.ts` |
| Types (reuse) | `PipelineExecutionRecord`, `PipelineStepExecution` in hook |
| Page structure pattern | `web/src/components/tasks/TasksPage.tsx` |
| CSS conventions | `web/src/components/tasks/tasks-page.css` |
| CSS variables | `web/src/styles/index.css` (lines 1-52) |
| REST API | `src/gobby/servers/routes/pipelines.py` |
| Event emission | `src/gobby/workflows/pipeline_executor.py` |

## WebSocket Events (no backend changes)

| Event | Fields |
|---|---|
| `pipeline_started` | `pipeline_name`, `inputs`, `step_count` |
| `step_started` | `step_id`, `step_name` |
| `step_completed` | `step_id`, `step_name`, `output` |
| `step_skipped` | `step_id`, `step_name`, `reason` |
| `approval_required` | `step_id`, `step_name`, `message`, `token` |
| `pipeline_completed` | `pipeline_name`, `outputs` |
| `pipeline_failed` | `pipeline_name`, `error` |

## Verification

1. `cd web && npx tsc --noEmit` — type check passes
2. `cd web && npm run build` — build succeeds
3. Start daemon, open web UI, navigate to Pipelines tab — empty state renders
4. Trigger a pipeline via `uv run gobby pipelines run <name>`
5. Verify: run appears in left list, status dot animates, steps populate in detail panel
6. Verify: event feed shows live events scrolling
7. Verify: clicking a step expands to show output
8. Test approval: run pipeline with approval gate, verify banner + buttons work
9. Test completed/failed states render correctly with proper colors
