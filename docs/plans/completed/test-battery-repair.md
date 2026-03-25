# Plan: Fix Gemini Agent Lifecycle Gaps

## Summary

Four interconnected bugs discovered while investigating two Gemini agents that ran for 4.5+ hours in a useless error loop after a daemon restart. These need to be fixed together to make the agent lifecycle robust.

---

## Bug 1: Agent Timeout Doesn't Survive Daemon Restart

**Root cause:** `timeout_seconds` is only stored in-memory in `RunningAgentRegistry`. The `agent_runs` DB table has no `timeout_seconds` column. When the daemon restarts and re-hydrates running agents from DB, timeout is `None`, and `check_expired_agents()` skips them with `if not agent.timeout_seconds: continue`.

**Files to modify:**

1. **`src/gobby/storage/migrations.py`** — Add migration to add `timeout_seconds REAL` column to `agent_runs` table. Also add to `BASELINE_SCHEMA`.

2. **`src/gobby/storage/agents.py`** — Update `create()`, `get()`, `list_running()`, and model hydration to include `timeout_seconds`.

3. **`src/gobby/mcp_proxy/tools/spawn_agent/_implementation.py`** — Already passes `timeout_seconds` to `RunningAgent`; ensure it also persists to DB via `agent_run_manager.create()`.

4. **`src/gobby/agents/lifecycle_monitor.py`** — When re-hydrating agents on startup (`recover_or_cleanup_agents()`), read `timeout_seconds` from DB and populate in-memory registry.

---

## Bug 2: `cleanup_stale_runs()` Is Never Called Periodically

**Root cause:** `LocalAgentRunManager.cleanup_stale_runs()` (storage/agents.py:537) exists but is only callable from the CLI (`gobby agents cleanup`). No periodic task invokes it. This is the safety net that should catch agents the lifecycle monitor misses.

**Files to modify:**

1. **`src/gobby/agents/lifecycle_monitor.py`** — Add a call to `cleanup_stale_runs()` in the `_check_loop`, running it every N iterations (e.g., every 10th loop = every 5 minutes). This marks any `agent_runs` with status `running` that are older than 30 minutes (configurable) as `timeout`.

2. **`src/gobby/workflows/pipeline_heartbeat.py`** — Consider also having the heartbeat invoke stale run cleanup, since it already handles stale task recovery. This gives two independent paths to catch zombies.

---

## Bug 3: Gemini CLI Doesn't Self-Terminate on Daemon Loss

**Root cause:** When Gobby hooks fail with "daemon not running", Gemini CLI shows a warning but keeps looping. It calls BeforeModel → gets blocked → calls AfterAgent → gets blocked → compresses → repeats forever. There's no hook failure threshold that triggers exit.

**Files to modify:**

1. **`src/gobby/install/shared/gemini/hooks.py`** (or equivalent Gemini hook handler) — Add a failure counter. After N consecutive hook failures (e.g., 3-5), the hook should return a hard stop signal or write a sentinel file that Gemini's GEMINI.md instructions tell it to check and exit.

2. **Alternatively / additionally — `src/gobby/agents/lifecycle_monitor.py`** — Enhance `check_provider_stalls()` or add new `check_zombie_agents()` that detects the "daemon not running" error pattern in tmux pane output and force-kills the tmux session. This is the more robust fix since it doesn't depend on Gemini respecting the signal.

3. **`src/gobby/agents/registry.py`** — Ensure `kill()` with `close_terminal=True` does a hard `tmux kill-session` as a final fallback if SIGTERM/SIGKILL don't work within the timeout window.

---

## Bug 4: Gemini Session Transcripts Don't Appear in Activities Panel

**Root cause:** In `src/gobby/hooks/event_handlers/_session.py`, the `SESSION_START` handler requires a `transcript_path` to register with `SessionMessageProcessor`. Claude provides this natively; Gemini does not. The fallback `_find_gemini_transcript()` fails because Gemini's session JSON file may not exist yet at SESSION_START time (race condition).

**Files to modify:**

1. **`src/gobby/hooks/event_handlers/_session.py`** — Two-part fix:
   - **Immediate:** Make `_find_gemini_transcript()` more robust — retry with short delay, or register a "pending" session that gets linked when the file appears.
   - **Deferred registration:** Add a mechanism where the `SessionMessageProcessor` can accept late-binding of transcript paths. When a Gemini session file is discovered later (e.g., on first AfterAgent hook), register it then.

2. **`src/gobby/sessions/processor.py`** — Add `register_session_deferred()` or `update_transcript_path()` method that allows late binding.

3. **`src/gobby/hooks/event_handlers/_session.py`** — In AfterAgent or other subsequent hooks, check if the session is unregistered and attempt to register it with the now-existing transcript path.

---

## Implementation Order

1. **Bug 1 (timeout persistence)** — Highest priority. Without this, no timeout works after restart. DB migration + storage + spawn code.
2. **Bug 2 (periodic stale cleanup)** — Safety net. Quick addition to lifecycle monitor loop.
3. **Bug 3 (zombie termination)** — Force-kill zombie agents. Add tmux kill-session fallback + pane content detection.
4. **Bug 4 (Gemini transcripts)** — Important for observability but not blocking agent execution.

---

## Verification Steps

1. **Bug 1:** Spawn a Gemini agent with timeout=120 → restart daemon → confirm agent is killed after timeout
2. **Bug 2:** Spawn a Gemini agent → kill daemon → wait 30+ minutes → restart daemon → confirm `cleanup_stale_runs` marks it as timed out
3. **Bug 3:** Spawn a Gemini agent → restart daemon → confirm agent self-terminates within ~90 seconds (3 × 30s hook failures) OR lifecycle monitor force-kills its tmux session
4. **Bug 4:** Spawn a Gemini agent → check session activities panel → confirm transcript appears within first minute of agent activity
