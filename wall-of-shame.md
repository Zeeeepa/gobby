# Wall of Shame

Failed fix attempts for bugs that should have been caught earlier.

## #9206, #9209 — Web UI Slash Commands Broken

**Symptom:** `/gobby:canvas`, `/skills`, `/mcp` and other slash commands work in CLI but fail silently in the Web UI.

### Attempt 1: Commit `1bffaca6` — "Fix Web UI slash command bugs"

**What it tried:** Unknown adjustments to the web chat path.

**Why it failed:** Did not address the root cause. `_fire_lifecycle()` in `chat.py` only called `workflow_handler.evaluate()` (the RuleEngine for declarative rules). It **never called `EventHandlers.handle_before_agent()`**, which is where skill interception (`_intercept_skill_command`) actually lives.

**Root cause:** The CLI path in `HookManager.handle()` runs two things in sequence:
1. `_evaluate_workflow_rules(event)` → RuleEngine
2. `handler(event)` → `EventHandlers.handle_before_agent()` → skill interception

The Web UI path only did step 1. Step 2 was completely missing.

**Actual fix:** Wire `EventHandlers` to the WebSocket server and dispatch to it from `_fire_lifecycle()` after rule evaluation, mirroring the CLI's two-step pattern.

### Attempt 2: Commit `9be33b0e` — "Wire EventHandlers from _fire_lifecycle"

**What it tried:** Wired `EventHandlers` to the WebSocket server and dispatched `handle_before_agent()` from `_fire_lifecycle()` after rule evaluation. Assumed `/gobby:canvas` was a skill command.

**Why it failed:** `/gobby:canvas` is NOT a skill. `canvas` is an MCP server. The `_intercept_skill_command` path in `handle_before_agent()` calls `_skill_manager.resolve_skill_name("canvas")`, which returns `None`, so it falls through to `_skill_not_found_context` — returning a "Skill 'canvas' not found" error. The fix only helps actual skill-based slash commands (`/gobby`, `/gobby:bridge`, `/gobby:expand`, etc.) but does nothing for `/gobby:canvas`, `/skills`, `/mcp` which are not skills at all.

**Root cause (still open):** The plan incorrectly diagnosed `/gobby:canvas` as a skill interception issue. The actual problem is that these commands need a different dispatch mechanism entirely — they're MCP server interactions, not skill lookups.
