# Autonomous Session Handoff

## Overview

Enable continuous autonomous coding sessions without relying on Claude Code's built-in autocompact summaries. When autocompact fires, Gobby generates structured context that supplements (not duplicates) Claude's compacted context, ensuring the agent can resume work without losing critical state.

**Problem:** Claude Code's autocompact generates generic summaries that lose implementation details, active task state, and progress context. For autonomous coding (unattended, long-running sessions), this causes the agent to lose track of what it was doing.

**Solution:** Hook into PreCompact to extract structured context, store it externally, and inject it on SessionStart(source='compact'). Rather than competing with Claude's narrative summary, provide structured facts that compaction tends to lose.

## Core Design Principles

1. **Supplement, don't duplicate** - Claude's compaction provides narrative; Gobby provides structured facts
2. **No /clear dependency** - Works for continuous sessions without manual intervention
3. **External persistence** - Critical state lives in gobby-tasks and gobby-memory, surviving any compaction
4. **Automatic inference** - Extract context from transcript even if agent didn't explicitly use gobby-tasks
5. **Minimal injection** - Only inject what Claude's compaction loses, keeping context window efficient

## Data Flow

```text
┌─────────────────────────────────────────────────────────────────────────┐
│                     Autonomous Session Flow                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Session Start                                                           │
│       │                                                                  │
│       ▼                                                                  │
│  Agent works... (context accumulates)                                    │
│       │                                                                  │
│       ▼                                                                  │
│  Context threshold reached (~180k tokens)                                │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ PreCompact Hook Fires (trigger='auto')                          │    │
│  │                                                                  │    │
│  │  1. TranscriptAnalyzer.extract_handoff_context(turns)           │    │
│  │     - Active gobby-task (if agent used it)                      │    │
│  │     - TodoWrite state (Claude's internal tracking)              │    │
│  │     - Files modified (Edit/Write tool calls)                    │    │
│  │     - Initial goal (first user message)                         │    │
│  │     - Recent activity (last N tool calls)                       │    │
│  │                                                                  │    │
│  │  2. Store to gobby-memory with tag 'handoff'                    │    │
│  │     - Or write to session record                                │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│       │                                                                  │
│       ▼                                                                  │
│  Claude's autocompact runs (generates its summary)                       │
│       │                                                                  │
│       ▼                                                                  │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │ SessionStart Hook Fires (source='compact')                      │    │
│  │                                                                  │    │
│  │  1. Retrieve stored handoff context                             │    │
│  │  2. Inject structured context (not narrative):                  │    │
│  │     - Active task + status                                      │    │
│  │     - In-progress todo items                                    │    │
│  │     - Files being modified                                      │    │
│  │     - Original goal                                             │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│       │                                                                  │
│       ▼                                                                  │
│  Agent continues with:                                                   │
│    - Claude's compacted narrative (already in context)                   │
│    - Gobby's structured facts (injected)                                │
│       │                                                                  │
│       ▼                                                                  │
│  Work continues... (repeat at next compaction)                           │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. TranscriptAnalyzer

New class to extract structured context from transcript without depending on /clear boundaries. Designed for Claude Code primarily, but extensible to other CLIs via the `TranscriptParser` protocol.

```python
# src/gobby/sessions/analyzer.py

@dataclass
class HandoffContext:
    """Structured context for autonomous handoff."""
    active_gobby_task: dict | None      # From call_tool(gobby-tasks) if used
    todo_state: list[dict]              # From TodoWrite tool calls
    files_modified: list[str]           # From Edit/Write tool calls
    git_commits: list[dict]             # Commits made this session
    git_status: str                     # Current uncommitted changes
    initial_goal: str                   # First user message
    recent_activity: list[str]          # Last N tool calls
    key_decisions: list[str] | None     # Optional: extracted decisions

class TranscriptAnalyzer:
    """
    Transcript analysis for handoff context.

    Primary: Claude Code
    Extensible: Other CLIs via TranscriptParser protocol
    """

    def __init__(self, parser: TranscriptParser | None = None):
        # Default to Claude parser - primary use case
        from gobby.sessions.transcripts.claude import ClaudeTranscriptParser
        self.parser = parser or ClaudeTranscriptParser()

    def extract_handoff_context(
        self,
        turns: list[dict],
        max_turns: int = 100
    ) -> HandoffContext:
        """
        Extract context for autonomous handoff.

        Analyzes recent turns (not dependent on /clear) to find:
        - Active task state from gobby-tasks calls
        - TodoWrite state from Claude's internal tracking
        - Files modified from Edit/Write/Bash calls
        - Git commits and uncommitted changes
        - The original user goal
        - Recent tool activity

        Works on ParsedMessage objects (normalized across CLIs).
        """
```

### 2. Workflow Updates (session-handoff.yaml)

Add triggers for PreCompact and SessionStart(source='compact'):

```yaml
# src/gobby/install/shared/workflows/session-handoff.yaml

triggers:
  # Existing: manual /clear flow
  on_session_end:
    - action: generate_handoff
      when: "event.data.get('reason') == 'clear'"
      # ... existing template ...

  # NEW: autonomous compaction flow
  on_pre_compact:
    - action: extract_handoff_context
      when: "event.data.get('trigger') == 'auto'"
      store_as: compact_handoff
      include:
        - active_task
        - todo_state
        - files_modified
        - git_commits
        - git_status
        - initial_goal
        - recent_activity

  on_session_start:
    # Existing: manual /clear injection
    - action: inject_context
      when: "event.data.get('source') == 'clear'"
      source: previous_session_summary
      template: |
        ## Previous Session Context
        {{ summary }}

    # NEW: autonomous compact injection
    - action: inject_context
      when: "event.data.get('source') == 'compact'"
      source: compact_handoff
      template: |
        ## Continuation Context

        {% if active_task %}
        ### Active Task
        **{{ active_task.title }}** ({{ active_task.id }})
        Status: {{ active_task.status }}
        {% if active_task.description %}{{ active_task.description }}{% endif %}
        {% endif %}

        {% if todo_state %}
        ### In-Progress Work
        {% for todo in todo_state %}
        - [{{ 'x' if todo.status == 'completed' else '>' if todo.status == 'in_progress' else ' ' }}] {{ todo.content }}
        {% endfor %}
        {% endif %}

        {% if git_commits %}
        ### Commits This Session
        {% for commit in git_commits %}
        - `{{ commit.hash }}` {{ commit.message }}
        {% endfor %}
        {% endif %}

        {% if git_status %}
        ### Uncommitted Changes
        ```
        {{ git_status }}
        ```
        {% endif %}

        {% if files_modified %}
        ### Files Being Modified
        {% for file in files_modified %}
        - {{ file }}
        {% endfor %}
        {% endif %}

        {% if initial_goal %}
        ### Original Goal
        {{ initial_goal }}
        {% endif %}
```

### 3. Hook Manager Update

Wire PreCompact to execute workflows (currently only logs):

```python
# src/gobby/hooks/hook_manager.py

def _handle_event_pre_compact(self, event: HookEvent) -> HookResponse:
    """Handle PRE_COMPACT event."""
    session_id = event.metadata.get("_platform_session_id")
    trigger = event.data.get("trigger", "unknown")  # 'auto' or 'manual'

    self.logger.debug(f"Pre-compact ({trigger}): session {session_id}")

    # Execute lifecycle workflows for on_pre_compact
    # This enables extract_handoff_context action
    wf_response = self._workflow_handler.handle_all_lifecycles(event)

    return wf_response
```

### 4. New Workflow Action: extract_handoff_context

```python
# src/gobby/workflows/actions.py

async def _execute_extract_handoff_context(
    self,
    action: dict,
    event: HookEvent,
    context: dict,
) -> dict:
    """
    Extract structured handoff context from transcript.

    Uses TranscriptAnalyzer to parse recent turns and extract:
    - Active task from gobby-tasks calls
    - TodoWrite state
    - Files modified
    - Initial goal
    - Recent activity
    """
    transcript_path = event.data.get("transcript_path")
    if not transcript_path:
        return {"status": "no_transcript"}

    # Read transcript
    turns = self._read_transcript(transcript_path)

    # Analyze
    analyzer = TranscriptAnalyzer()
    handoff_context = analyzer.extract_handoff_context(turns)

    # Store for injection on SessionStart
    store_key = action.get("store_as", "compact_handoff")
    self._store_handoff_context(event.session_id, store_key, handoff_context)

    return {
        "status": "success",
        "context": handoff_context.to_dict(),
    }
```

## Injection Strategy

### What Claude's Compaction Loses

| Information | Claude Compaction | Gobby Injection |
|-------------|-------------------|-----------------|
| General narrative | Preserved (generic) | Not duplicated |
| Specific task ID | Often lost | Injected |
| Task status (in_progress) | Lost | Injected |
| TodoWrite items | Summarized | Exact list |
| Git commits this session | Often lost | Exact list with hashes |
| Uncommitted changes | Lost | Full git status |
| File paths being edited | Often lost | Exact list |
| Original user request | Summarized | Verbatim |
| Recent tool sequence | Lost | Last 5 calls |

### What NOT to Inject

- Full narrative summary (Claude already has this)
- Conversation history (Claude's compaction covers this)
- Code snippets (too large, Claude saw them)
- Debugging steps (narrative territory)

## Implementation Checklist

### Phase 1: TranscriptAnalyzer

- [ ] Create `src/gobby/sessions/analyzer.py`
- [ ] Define `HandoffContext` dataclass
- [ ] Implement `TranscriptAnalyzer.extract_handoff_context()`
- [ ] Implement `_extract_gobby_task()` - find gobby-tasks tool calls
- [ ] Implement `_extract_todowrite()` - find TodoWrite state (reuse from summary.py)
- [ ] Implement `_extract_files_modified()` - find Edit/Write tool calls
- [ ] Implement `_extract_git_commits()` - find commits made this session:
  - Parse Bash tool calls for `git commit` commands
  - Run `git log --since=<session_start>` for commits made during session
  - Extract hash (short), message, and optionally files changed
- [ ] Implement `_get_git_status()` - run `git status --short` for uncommitted changes
- [ ] Implement `_extract_initial_goal()` - first user message
- [ ] Implement `_extract_recent_activity()` - last N tool calls
- [ ] Add unit tests for TranscriptAnalyzer

### Phase 2: Workflow Action

- [ ] Add `extract_handoff_context` action type to ActionExecutor
- [ ] Implement handoff context storage (session-scoped)
- [ ] Implement handoff context retrieval for injection
- [ ] Add unit tests for action execution

### Phase 3: Workflow Definition

- [ ] Add `on_pre_compact` trigger to session-handoff.yaml
- [ ] Add `source='compact'` handler to `on_session_start`
- [ ] Create injection template for structured context
- [ ] Test workflow trigger conditions

### Phase 4: Hook Manager Integration

- [ ] Update `_handle_event_pre_compact()` to execute workflows
- [ ] Ensure event.data includes `trigger` field ('auto' or 'manual')
- [ ] Test PreCompact → SessionStart flow end-to-end

### Phase 5: Testing & Documentation

- [ ] Integration test: simulate autocompact flow
- [ ] Test with real Claude Code session (manual trigger)
- [ ] Document autonomous handoff in README
- [ ] Add configuration options if needed
- [ ] Update CLAUDE.md with autonomous coding guidance

## Configuration

```yaml
# ~/.gobby/config.yaml (future)

autonomous_handoff:
  enabled: true

  # Context extraction settings
  max_turns_to_analyze: 100
  include_recent_activity: 5  # Last N tool calls

  # What to extract
  extract:
    gobby_tasks: true
    todowrite: true
    files_modified: true
    git_commits: true          # Commits made this session
    git_status: true           # Current uncommitted changes
    initial_goal: true
    recent_activity: true

  # Git settings
  git:
    max_commits: 20            # Max commits to include
    include_diff_stats: false  # Include --stat for each commit

  # Injection format
  injection_format: structured  # 'structured' or 'narrative'
```

## Edge Cases

### No Active Task

If agent never used gobby-tasks, we still have:
- TodoWrite state (Claude's internal tracking)
- Files modified
- Initial goal
- Recent activity

This is enough to resume work.

### Multiple Compactions Per Session

Each PreCompact overwrites the previous handoff context. This is fine - we want the most recent state.

### Manual /compact Command

Works the same as autocompact. The `trigger` field will be 'manual' but we extract context either way.

### Session Without Clear Goal

If transcript starts mid-work (e.g., resumed session), initial_goal extraction may be less useful. Fall back to recent activity.

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | **Trigger condition** | `trigger == 'auto'` or always | Start with auto-only, can expand to both |
| 2 | **Storage location** | Session-scoped (in-memory or DB) | Only needed until SessionStart fires |
| 3 | **Injection format** | Structured markdown sections | Clear, parseable, doesn't overlap with narrative |
| 4 | **/clear dependency** | None | Analyze last N turns regardless of /clear |
| 5 | **LLM for extraction** | No (rule-based) | Tool calls are structured, no LLM needed |
| 6 | **Gobby-tasks required** | No (graceful fallback) | Use if available, fall back to TodoWrite |

## Future Enhancements

- **LLM-powered decision extraction** - Use LLM to identify key decisions from transcript
- **Confidence scoring** - Rate how confident we are in extracted context
- **Cross-session learning** - Remember patterns across multiple compactions
- **Custom extraction prompts** - User-defined prompts for context extraction
- **Compaction prediction** - Estimate when compaction will occur, prepare ahead
