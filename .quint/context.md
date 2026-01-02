# Bounded Context

## Vocabulary

- **Hook**: Event interceptor for Claude Code/Gemini/Codex CLIs.
- **Session**: A single AI coding assistant conversation with lifecycle events. Task (gobby-task): Persistent work item with dependencies, validation, and git sync.
- **Memory**: Persistent fact/preference/pattern stored across sessions.
- **Skill**: Reusable instruction set learned from sessions.
- **Workflow**: Phase-based or lifecycle-driven agent behavior enforcement.
- **Artifact**: Captured output from tool calls (code changes, commits, decisions). Internal
- **Server**: gobby-* prefixed MCP servers handled locally (tasks, memory, skills, workflows). Progressive
- **Disclosure**: list_tools → get_tool_schema → call_tool pattern for token efficiency.
- **Handoff**: Context extraction and injection between compacted sessions.

## Invariants

Local-first: All data stored in ~/.gobby/ SQLite database, no external services required for core functionality. CLI-agnostic: Must work identically across Claude Code, Gemini CLI, and Codex. Hook non-blocking: Hook handlers must respond within 5 seconds to avoid CLI timeouts. Session isolation: Each session has independent state; cross-session data via explicit storage (tasks, memory, skills). Tool restrictions: Workflow phases can block/allow tools but cannot modify tool behavior. Git-friendly sync: Task/memory/skill sync uses JSONL with last-write-wins conflict resolution. Backward compatible: Config and database migrations must preserve existing data.
