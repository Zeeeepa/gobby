---
name: agents
description: How to spawn, message, and command subagents.
version: "1.0.0"
category: Orchestration
alwaysApply: false
injectionFormat: full
---

# Agents Skill: Working with Subagents

This skill teaches spawned agents how to use the Gobby agents system, including spawning other agents, passing messages, and sending commands.

## Server Clarity

All agent tools live on **`gobby-agents`**, NOT `gobby-sessions`.
- `gobby-sessions` is for session lifecycle (CRUD, handoffs).
- `gobby-agents` is for spawning, messaging, and commands.

## Messaging Tools (on `gobby-agents`)

- `send_message(from_session, to_session, content)` — Send a peer-to-peer message between any two sessions in the same project.
- `deliver_pending_messages(session_id)` — Inbox check. Use this often to retrieve any pending messages.

## Command Tools (on `gobby-agents`)

These tools are specifically for orchestrating workers:
- `send_command(session_id, command_type, payload)` — Issue a command to a subagent.
- `activate_command(session_id, command_id)` — Accept a command you have received (marks it in-progress).
- `complete_command(session_id, command_id, result)` — Fulfill a command with a result string.

## Dos and Don'ts

- **DO** use the integer Session ID (`#5`) or short prefixes for session IDs.
- **DO** check your inbox before taking long actions.
- **DON'T** use `/quit` or bash exit tools to kill yourself. Use the `kill_agent` or `terminate` tools instead (via `gobby-agents` or `mcp_proxy`).
- **DON'T** poll constantly — wait for the user or use the event-driven hooks where possible.
