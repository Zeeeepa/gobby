---
name: codex-setup
description: Check Codex CLI readiness and configure the review gate. Use when asked to set up Codex, enable/disable review gate, or check Codex status.
category: integration
tags:
  - gobby
metadata:
  gobby:
    audience: interactive
    depth: 0
---

# Codex Setup

Interactive setup for Codex CLI integration with Gobby.

## Step 1: Check Codex CLI

```bash
command -v codex && codex --version
```

If not installed, tell the user to install it:
```bash
npm install -g @openai/codex
```

## Step 2: Check Authentication

```bash
codex login --status
```

If not authenticated, tell the user to run:
```
! codex login
```

(The `!` prefix runs it in the current session so auth lands in the conversation.)

## Step 3: Configure Review Gate

Ask the user whether they want the Codex stop-time review gate enabled.

**If yes**: Set the daemon config so it persists across sessions:
```
set_variable(name="codex_review_gate_enabled", value=true)
```

Also update daemon config for persistence:
```
call_tool("gobby-config", "set_config", {"key": "codex_review_gate_enabled", "value": true})
```

**If no**: Disable it:
```
set_variable(name="codex_review_gate_enabled", value=false)
call_tool("gobby-config", "set_config", {"key": "codex_review_gate_enabled", "value": false})
```

## Step 4: Summary

Report the status:
- Codex CLI: installed / not installed
- Authentication: logged in / not logged in
- Review gate: enabled / disabled
- Available commands: `codex review`, `codex exec`
