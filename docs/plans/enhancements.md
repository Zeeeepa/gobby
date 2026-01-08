# Post-MVP Features: AI Project Inspired Enhancements

## Overview

This document outlines high-value features inspired by trending AI projects. These features would enhance Gobby's capabilities for parallel agent coordination, intelligent merge handling, searchable history, and smart context management.

**Inspirations:**

- [Auto-Claude](https://github.com/AndyMik90/Auto-Claude) - Multi-agent orchestration with worktree isolation (Phases 1-5)
- [Continuous-Claude v2](https://github.com/parcadei/Continuous-Claude-v2) - Ledger-based state, artifact indexing (Phase 6)
- [SkillForge](https://github.com/tripleyak/SkillForge) - Intelligent skill routing and quality scoring (Phase 7)
- [KnowNote](https://github.com/MrSibe/KnowNote) - Local-first semantic search with sqlite-vec (Phase 8)
- Original Design - Task-driven autonomous execution with multi-surface termination controls (Phase 9)

> **Note**: Worktree management (`gobby-worktrees`) has been moved to [SUBAGENTS.md](./SUBAGENTS.md) as it is tightly coupled with the subagent spawning system.

## Build Order

```text
Phase 1: Intelligent Merge Resolution (new gobby-merge internal server)
    ↓
    │  Depends on: SUBAGENTS.md Phase 4 (gobby-worktrees)
    ↓
Phase 2: QA Validation Loop Enhancement (extends gobby-tasks validation)
    ↓
Phase 3: GitHub Integration (new gobby-github internal server)
    ↓
Phase 4: Linear Integration (new gobby-linear internal server)
    ↓
Phase 5: Structured Pipeline Workflows (BMAD integration)
    ↓
Phase 6: Artifact Index (searchable session history with FTS5)
    ↓
Phase 7: Enhanced Skill Routing (intelligent skill matching)
    ↓
Phase 8: Semantic Memory Search (sqlite-vec local vectors)
    ↓
Phase 9: Autonomous Work Loop (task-driven execution with termination controls)
```

Each phase is independently valuable. Phases 1-2 enhance local development workflows. Phases 3-4 add external integrations. Phase 5 ties everything together with structured pipelines. Phases 6-8 add intelligent search and context capabilities inspired by trending AI projects. Phase 9 enables fully autonomous task execution with robust termination controls.

---

## Phase 1: Intelligent Merge Resolution

> **Prerequisite**: Requires `gobby-worktrees` from [SUBAGENTS.md](./SUBAGENTS.md) Phase 4.

### Phase 1: Overview

When merging worktree branches back to main, use AI to resolve conflicts intelligently. Key insight from Auto-Claude: send only conflict regions to AI (~98% prompt reduction).

### Phase 1: Core Design Principles

1. **Minimal context** - Only send conflict hunks, not entire files
2. **Parallel resolution** - Resolve multiple files simultaneously
3. **Validation before apply** - Verify resolution compiles/parses before applying
4. **Fallback escalation** - Git auto → conflict-only AI → full-file AI → human

### Conflict Resolution Strategy

```text
┌─────────────────────────────────────────────────────────────┐
│                    Merge Attempt                            │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Tier 1: Git Auto-Merge                         │
│  - Non-conflicting changes merged automatically             │
│  - No AI needed for these files                             │
└─────────────────────────┬───────────────────────────────────┘
                          │ conflicts detected
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Tier 2: Conflict-Only AI                       │
│  - Extract only conflict markers and surrounding context    │
│  - ~98% prompt reduction vs full file                       │
│  - AI resolves each conflict region                         │
│  - Parallel processing for multiple files                   │
└─────────────────────────┬───────────────────────────────────┘
                          │ resolution failed
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Tier 3: Full-File AI                           │
│  - Send entire conflicted file                              │
│  - More context for complex semantic conflicts              │
│  - Fallback when hunks aren't sufficient                    │
└─────────────────────────┬───────────────────────────────────┘
                          │ still failed
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Tier 4: Human Review                           │
│  - Mark file for manual resolution                          │
│  - Provide AI analysis of conflict nature                   │
│  - Suggest resolution approaches                            │
└─────────────────────────────────────────────────────────────┘
```

### Phase 1: Data Model

```sql
CREATE TABLE merge_resolutions (
    id TEXT PRIMARY KEY,                    -- mr-{6 chars}
    worktree_id TEXT NOT NULL,
    source_branch TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    status TEXT DEFAULT 'pending',          -- pending, resolving, resolved, failed
    files_total INTEGER DEFAULT 0,
    files_auto_merged INTEGER DEFAULT 0,
    files_ai_resolved INTEGER DEFAULT 0,
    files_manual INTEGER DEFAULT 0,
    resolution_tier TEXT,                   -- tier1, tier2, tier3, tier4
    started_at TEXT,
    completed_at TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (worktree_id) REFERENCES worktrees(id)
);

CREATE TABLE merge_conflicts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    resolution_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    conflict_hunks TEXT,                    -- JSON: array of conflict regions
    resolved_content TEXT,                  -- Final resolved content
    resolution_method TEXT,                 -- auto, ai_hunk, ai_full, manual
    ai_reasoning TEXT,                      -- Explanation of resolution
    created_at TEXT NOT NULL,
    resolved_at TEXT,
    FOREIGN KEY (resolution_id) REFERENCES merge_resolutions(id) ON DELETE CASCADE
);
```

### MCP Tools (gobby-merge)

```python
@mcp.tool()
def start_merge(
    worktree_id: str,
    target_branch: str = "main",
    strategy: str = "auto",                 # auto, ai_only, manual
) -> dict:
    """
    Initiate merge of worktree branch into target.

    Returns:
    - merge_resolution_id for tracking
    - List of files with conflict status
    - Recommended resolution tier per file
    """

@mcp.tool()
def get_merge_status(resolution_id: str) -> dict:
    """Get current merge resolution status and progress."""

@mcp.tool()
def get_conflict_hunks(
    resolution_id: str,
    file_path: str,
) -> dict:
    """
    Extract conflict hunks from a file.

    Returns minimal context around each <<<<<<< marker.
    Optimized for token efficiency.
    """

@mcp.tool()
def resolve_conflict_hunk(
    resolution_id: str,
    file_path: str,
    hunk_index: int,
    resolution: str,
    reasoning: str | None = None,
) -> dict:
    """Resolve a specific conflict hunk."""

@mcp.tool()
def resolve_file_ai(
    resolution_id: str,
    file_path: str,
    tier: str = "hunk",                     # hunk (tier2) or full (tier3)
) -> dict:
    """
    Use AI to resolve all conflicts in a file.

    tier="hunk": Send only conflict regions (default, most efficient)
    tier="full": Send entire file (for semantic conflicts)
    """

@mcp.tool()
def resolve_all_conflicts(
    resolution_id: str,
    parallel: bool = True,
    max_concurrent: int = 5,
) -> dict:
    """
    Resolve all conflicts using tiered strategy.

    Attempts tier 2 (hunk) first, escalates to tier 3 (full) on failure.
    Parallel processing when enabled.
    """

@mcp.tool()
def validate_resolution(
    resolution_id: str,
    file_path: str | None = None,           # Specific file or all
) -> dict:
    """
    Validate resolved content.

    - Syntax check (parse/compile)
    - No remaining conflict markers
    - File is complete (no truncation)
    """

@mcp.tool()
def apply_merge(resolution_id: str) -> dict:
    """
    Apply resolved merge to repository.

    Creates merge commit with resolution metadata.
    Updates worktree status to 'merged'.
    """

@mcp.tool()
def abort_merge(resolution_id: str) -> dict:
    """Abort merge and restore previous state."""

@mcp.tool()
def mark_manual(
    resolution_id: str,
    file_path: str,
    reason: str,
) -> dict:
    """Mark a file for manual human resolution."""
```

### Phase 1: CLI Commands

```bash
# Merge operations
gobby merge start WORKTREE_ID [--target BRANCH] [--strategy auto|ai|manual]
gobby merge status RESOLUTION_ID
gobby merge conflicts RESOLUTION_ID [--file PATH]
gobby merge resolve RESOLUTION_ID [--parallel] [--max-concurrent N]
gobby merge validate RESOLUTION_ID [--file PATH]
gobby merge apply RESOLUTION_ID
gobby merge abort RESOLUTION_ID

# Analysis
gobby merge analyze WORKTREE_ID [--target BRANCH]  # Preview conflicts without starting
gobby merge history [--project PROJECT] [--limit N]
```

### Phase 1: Configuration

```yaml
merge:
  enabled: true
  default_strategy: "auto"                  # auto, ai_only, manual
  parallel_resolution: true
  max_concurrent_files: 5
  context_lines: 5                          # Lines around conflict for AI
  validation:
    syntax_check: true
    marker_check: true
  provider: "claude"                        # LLM provider for resolution
  model: "claude-sonnet-4-5"
  prompts:
    hunk_resolution: |
      You are resolving a git merge conflict.

      The conflict is between:
      - OURS (<<<<<<< HEAD): Changes from {target_branch}
      - THEIRS (>>>>>>> {source_branch}): Changes being merged

      Conflict region:
      {conflict_hunk}

      Resolve this conflict by combining both changes appropriately.
      Output ONLY the resolved code, no explanations.
```

### Phase 1: Implementation Checklist

#### Phase 1.1: Conflict Extraction

- [ ] Create `src/merge/extractor.py` with conflict hunk extraction
- [ ] Implement `extract_conflict_hunks()` - parse <<<<<<< markers
- [ ] Implement context windowing (configurable lines around conflict)
- [ ] Calculate token savings vs full file
- [ ] Add unit tests with various conflict patterns

#### Phase 1.2: Resolution Engine

- [ ] Create `src/merge/resolver.py` with `MergeResolver` class
- [ ] Implement tiered resolution strategy
- [ ] Implement parallel file resolution
- [ ] Implement validation (syntax, markers, completeness)
- [ ] Add fallback escalation logic

#### Phase 1.3: Storage & Tracking

- [ ] Create database migrations
- [ ] Create `src/storage/merges.py` with `LocalMergeManager`
- [ ] Track resolution progress and history
- [ ] Store AI reasoning for audit trail

#### Phase 1.4: MCP Tools

- [ ] Create `src/mcp_proxy/tools/merge.py`
- [ ] Register as `gobby-merge` internal server
- [ ] Implement all tools listed above

#### Phase 1.5: CLI Commands

- [ ] Add `gobby merge` command group
- [ ] Implement all commands listed above
- [ ] Add progress indicators for long operations

#### Phase 1.6: Integration

- [ ] Hook into worktree merge flow (from SUBAGENTS gobby-worktrees)
- [ ] Update task status on successful merge
- [ ] Add merge metadata to session handoff

---

## Phase 2: Enhanced QA Validation Loop

### Phase 2: Overview

Extend existing `gobby-tasks` validation with Auto-Claude's self-healing QA loop pattern. After task completion, run iterative validation with automatic fix attempts.

**Current State:** `validate_task` tool exists but is single-shot.

**Goal:** Iterative validation loop with configurable retry limit and automatic fix subtask creation.

### QA Loop Architecture

```text
┌─────────────────────────────────────────────────────────────┐
│                  Task Marked Complete                       │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Gather Validation Context                      │
│  - Git diff (staged + unstaged)                             │
│  - Test results (if tests exist)                            │
│  - Affected files content                                   │
│  - Acceptance criteria from task                            │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│              Run Validation Agent                           │
│  - External validator (separate context)                    │
│  - Checks acceptance criteria                               │
│  - Returns pass/fail with specific issues                   │
└─────────────────────────┬───────────────────────────────────┘
                          │
              ┌───────────┴───────────┐
              │                       │
              ▼                       ▼
       ┌──────────┐           ┌──────────────┐
       │  PASS    │           │    FAIL      │
       └────┬─────┘           └──────┬───────┘
            │                        │
            ▼                        ▼
    Close task with            Attempt auto-fix
    validation_status          (up to N retries)
    = "valid"                        │
                              ┌──────┴──────┐
                              │             │
                              ▼             ▼
                        Fix succeeded   Max retries
                        (loop back)     exceeded
                                              │
                                              ▼
                                    Create fix subtask
                                    Mark task "failed"
```

### New MCP Tools (gobby-tasks)

```python
@mcp.tool()
def validate_and_fix(
    task_id: str,
    max_retries: int = 3,
    auto_fix: bool = True,
) -> dict:
    """
    Run validation loop with automatic fix attempts.

    1. Validate task completion
    2. If failed and auto_fix=True:
       - Attempt to fix issues
       - Re-validate (up to max_retries)
    3. If still failing:
       - Create fix subtask with failure details
       - Mark task status = 'failed'

    Returns validation history and final status.
    """

@mcp.tool()
def get_validation_history(task_id: str) -> dict:
    """Get all validation attempts for a task with results."""

@mcp.tool()
def run_fix_attempt(
    task_id: str,
    issues: list[str],
) -> dict:
    """
    Attempt to fix specific validation issues.

    Spawns fix agent with:
    - Original task context
    - Validation failure details
    - Affected files

    Returns changes made and success status.
    """
```

### Configuration Updates

```yaml
task_validation:
  # ... existing config ...

  # QA Loop settings
  qa_loop:
    enabled: true
    max_retries: 3                          # Max fix attempts before giving up
    auto_fix: true                          # Attempt automatic fixes
    fix_timeout_seconds: 120                # Timeout per fix attempt
    external_validator: true                # Use separate agent for validation
    create_fix_subtask_on_fail: true        # Create subtask documenting failure

  # Fix agent settings
  fix_agent:
    provider: "claude"
    model: "claude-sonnet-4-5"
    prompt: |
      You are fixing validation failures for a task.

      ## Original Task
      {task_title}
      {task_description}

      ## Validation Failures
      {validation_issues}

      ## Files to Fix
      {affected_files}

      Fix the issues and ensure all validation criteria pass.
```

### Phase 2: Implementation Checklist

#### Phase 2.1: Validation History

- [ ] Add `validation_attempts` table to track all attempts
- [ ] Store validation result, issues, timestamp per attempt
- [ ] Implement `get_validation_history()` query

#### Phase 2.2: Fix Agent

- [ ] Create `src/tasks/fix_agent.py` with fix attempt logic
- [ ] Implement `run_fix_attempt()` - spawn agent with context
- [ ] Capture changes made during fix attempt
- [ ] Re-run validation after fix

#### Phase 2.3: QA Loop

- [ ] Implement `validate_and_fix()` loop logic
- [ ] Add retry counter and max limit
- [ ] Implement fix subtask creation on final failure
- [ ] Update task status to 'failed' when exhausted

#### Phase 2.4: Integration

- [ ] Hook into `close_task` flow (optional auto-validate)
- [ ] Add QA loop option to task expansion (validate subtasks)
- [ ] Add CLI commands for manual QA loop trigger

---

## Phase 3: GitHub Integration

### Phase 3: Overview

Bidirectional sync between `gobby-tasks` and GitHub Issues. Import issues as tasks, create PRs from completed tasks, sync status changes.

### MCP Tools (gobby-github)

```python
@mcp.tool()
def connect_github(
    repo: str,                              # owner/repo format
    token: str | None = None,               # Uses GITHUB_TOKEN env if not provided
) -> dict:
    """Connect project to GitHub repository."""

@mcp.tool()
def import_issues(
    labels: list[str] | None = None,
    state: str = "open",                    # open, closed, all
    limit: int = 50,
) -> dict:
    """
    Import GitHub issues as gobby-tasks.

    Creates tasks with:
    - Title and description from issue
    - Labels mapped to task labels
    - GitHub issue number stored in metadata
    """

@mcp.tool()
def sync_task_to_issue(task_id: str) -> dict:
    """Push task status/updates to linked GitHub issue."""

@mcp.tool()
def create_pr_from_task(
    task_id: str,
    worktree_id: str | None = None,         # Use current worktree if not specified
    draft: bool = False,
) -> dict:
    """
    Create GitHub PR from completed task.

    - Uses task title for PR title
    - Generates PR description from task + changes
    - Links PR to issue (if task imported from issue)
    """

@mcp.tool()
def get_pr_status(task_id: str) -> dict:
    """Get status of PR linked to task (checks, reviews, etc.)."""

@mcp.tool()
def sync_from_github() -> dict:
    """Pull latest issue/PR updates into gobby-tasks."""
```

### Phase 3: CLI Commands

```bash
gobby github connect OWNER/REPO [--token TOKEN]
gobby github import [--labels LABEL,...] [--state open|closed|all] [--limit N]
gobby github sync [--direction in|out|both]
gobby github pr create TASK_ID [--worktree WORKTREE_ID] [--draft]
gobby github pr status TASK_ID
gobby github disconnect
```

### Phase 3: Configuration

```yaml
github:
  enabled: false
  repo: null                                # owner/repo
  token_env: "GITHUB_TOKEN"                 # Environment variable for token
  auto_sync: false                          # Auto-sync on task changes
  import_labels: []                         # Only import issues with these labels
  create_pr_on_close: false                 # Auto-create PR when task closed
  link_issues: true                         # Link PRs to issues
```

### Phase 3: Implementation Checklist

#### Phase 3.1: GitHub Client

- [ ] Create `src/integrations/github.py` with GitHub API client
- [ ] Implement issue listing/fetching
- [ ] Implement PR creation
- [ ] Implement status sync
- [ ] Handle rate limiting and pagination

#### Phase 3.2: Task Mapping

- [ ] Add `github_issue_number` and `github_pr_number` to tasks table
- [ ] Implement issue → task mapping
- [ ] Implement task → issue sync
- [ ] Handle label mapping

#### Phase 3.3: MCP Tools & CLI

- [ ] Create `src/mcp_proxy/tools/github.py`
- [ ] Register as `gobby-github` internal server
- [ ] Add CLI commands

---

## Phase 4: Linear Integration

### Phase 4: Overview

Sync `gobby-tasks` with Linear for teams using Linear for project management.

### MCP Tools (gobby-linear)

```python
@mcp.tool()
def connect_linear(
    team_id: str,
    api_key: str | None = None,
) -> dict:
    """Connect project to Linear team."""

@mcp.tool()
def import_issues(
    state: str | None = None,               # Filter by state
    labels: list[str] | None = None,
    limit: int = 50,
) -> dict:
    """Import Linear issues as gobby-tasks."""

@mcp.tool()
def sync_task_to_linear(task_id: str) -> dict:
    """Push task status to linked Linear issue."""

@mcp.tool()
def create_linear_issue(task_id: str) -> dict:
    """Create Linear issue from gobby-task."""

@mcp.tool()
def sync_from_linear() -> dict:
    """Pull latest Linear updates."""
```

### Phase 4: Configuration

```yaml
linear:
  enabled: false
  team_id: null
  api_key_env: "LINEAR_API_KEY"
  auto_sync: false
  state_mapping:                            # Map gobby status to Linear states
    open: "Todo"
    in_progress: "In Progress"
    closed: "Done"
    failed: "Canceled"
```

### Phase 4: Implementation Checklist

#### Phase 4.1: Linear Client

- [ ] Create `src/integrations/linear.py` with Linear GraphQL client
- [ ] Implement issue listing/fetching
- [ ] Implement issue creation/update
- [ ] Handle pagination

#### Phase 4.2: Task Mapping

- [ ] Add `linear_issue_id` to tasks table
- [ ] Implement bidirectional sync
- [ ] Map states and labels

#### Phase 4.3: MCP Tools & CLI

- [ ] Create `src/mcp_proxy/tools/linear.py`
- [ ] Register as `gobby-linear` internal server
- [ ] Add CLI commands

---

## Phase 5: Structured Pipeline Workflows

### Phase 5: Overview

Formalize the Spec → Plan → Implement → QA → Merge pipeline as explicit workflow phases. Each phase has distinct agent roles and tool access.

**Integration:** Leverage existing BMAD workflows for structured execution.

### Pipeline Phases

| Phase | Agent Role | Key Actions | Tools Available |
| :--- | :--- | :--- | :--- |
| **Spec** | Analyst | Gather requirements, create PRD | Read, Glob, Grep, WebSearch |
| **Plan** | Architect | Design implementation, expand tasks | expand_task, create_task |
| **Implement** | Developer | Write code, create worktrees | All tools, worktree access |
| **QA** | Validator | Run tests, validate tasks | validate_task, Bash (test runners) |
| **Merge** | Integrator | Resolve conflicts, merge to main | merge tools |

### Pipeline State

```python
@dataclass
class PipelineState:
    id: str                                 # pp-{6 chars}
    project_id: str
    name: str                               # Human-readable pipeline name
    current_phase: str                      # spec, plan, implement, qa, merge
    phase_history: list[PhaseTransition]
    root_task_id: str | None                # Top-level task for this pipeline
    worktree_ids: list[str]                 # Active worktrees
    spec_document: str | None               # Path to spec file
    created_at: datetime
    updated_at: datetime
```

### MCP Tools (gobby-pipeline)

```python
@mcp.tool()
def create_pipeline(
    name: str,
    goal: str,                              # High-level goal description
    spec_path: str | None = None,           # Existing spec file
) -> dict:
    """Start a new development pipeline."""

@mcp.tool()
def get_pipeline_status(pipeline_id: str) -> dict:
    """Get current pipeline phase and progress."""

@mcp.tool()
def advance_phase(
    pipeline_id: str,
    to_phase: str | None = None,            # Auto-advance if not specified
) -> dict:
    """Advance pipeline to next phase (with validation)."""

@mcp.tool()
def get_phase_checklist(
    pipeline_id: str,
    phase: str | None = None,
) -> dict:
    """Get checklist of requirements for current/specified phase."""
```

### Phase 5: Implementation Checklist

#### Phase 5.1: Pipeline State

- [ ] Create `pipelines` table
- [ ] Create `pipeline_phases` table for history
- [ ] Implement state machine for phase transitions

#### Phase 5.2: Phase Validation

- [ ] Implement phase entry/exit criteria
- [ ] Validate spec exists before plan phase
- [ ] Validate tasks created before implement phase
- [ ] Validate tests pass before merge phase

#### Phase 5.3: MCP Tools & CLI

- [ ] Create `src/mcp_proxy/tools/pipeline.py`
- [ ] Register as `gobby-pipeline` internal server
- [ ] Add CLI commands

#### Phase 5.4: BMAD Integration

- [ ] Map pipeline phases to BMAD workflows
- [ ] Enable BMAD agent handoff between phases
- [ ] Integrate with existing BMAD skills

---

## Phase 6: Artifact Index (Searchable Session History)

### Phase 6: Overview

Implement a searchable index of session artifacts inspired by [Continuous-Claude v2](https://github.com/parcadei/Continuous-Claude-v2). Their "clear, don't compact" philosophy uses ledger-based state management with an **Artifact Index** (SQLite + FTS5) for fast retrieval of past session content.

**Inspiration:** Continuous-Claude's approach to lossless session history vs. lossy summarization.

**Goal:** Enable agents to search across all past session artifacts—code changes, tool outputs, decisions—using full-text search.

### Phase 6: Core Design Principles

1. **Lossless preservation** - Store all artifacts, not just summaries
2. **Fast retrieval** - FTS5 index for sub-second search across thousands of sessions
3. **Structured metadata** - Track artifact type, session, timestamp, file paths
4. **Contextual injection** - Recall relevant artifacts during session handoff

### Phase 6: Data Model

```sql
-- Core artifact storage
CREATE TABLE session_artifacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    artifact_type TEXT NOT NULL,           -- code_change, tool_output, decision, error, commit
    title TEXT,                             -- Brief description
    content TEXT NOT NULL,                  -- Full artifact content
    file_path TEXT,                         -- Associated file (if applicable)
    metadata TEXT,                          -- JSON: additional structured data
    created_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

-- Full-text search index
CREATE VIRTUAL TABLE session_artifacts_fts USING fts5(
    title,
    content,
    file_path,
    content='session_artifacts',
    content_rowid='id'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER session_artifacts_ai AFTER INSERT ON session_artifacts BEGIN
    INSERT INTO session_artifacts_fts(rowid, title, content, file_path)
    VALUES (new.id, new.title, new.content, new.file_path);
END;

CREATE TRIGGER session_artifacts_ad AFTER DELETE ON session_artifacts BEGIN
    INSERT INTO session_artifacts_fts(session_artifacts_fts, rowid, title, content, file_path)
    VALUES ('delete', old.id, old.title, old.content, old.file_path);
END;

CREATE TRIGGER session_artifacts_au AFTER UPDATE ON session_artifacts BEGIN
    INSERT INTO session_artifacts_fts(session_artifacts_fts, rowid, title, content, file_path)
    VALUES ('delete', old.id, old.title, old.content, old.file_path);
    INSERT INTO session_artifacts_fts(rowid, title, content, file_path)
    VALUES (new.id, new.title, new.content, new.file_path);
END;

-- Index for common queries
CREATE INDEX idx_artifacts_session ON session_artifacts(session_id);
CREATE INDEX idx_artifacts_type ON session_artifacts(artifact_type);
CREATE INDEX idx_artifacts_file ON session_artifacts(file_path);
```

### Artifact Types

| Type | Description | Captured From |
| :--- | :--- | :--- |
| `code_change` | File modifications | Edit/Write tool results |
| `tool_output` | Tool execution results | All tool results |
| `decision` | Architectural/design decisions | LLM reasoning (extracted) |
| `error` | Errors encountered | Tool failures, validation errors |
| `commit` | Git commits made | Bash git commit output |
| `test_result` | Test execution results | Bash pytest/jest output |
| `research` | Web search/fetch results | WebSearch/WebFetch results |

### MCP Tools (gobby-artifacts)

```python
@mcp.tool()
def search_artifacts(
    query: str,
    artifact_types: list[str] | None = None,
    session_id: str | None = None,           # Limit to specific session
    file_path: str | None = None,            # Filter by file path pattern
    limit: int = 20,
) -> dict:
    """
    Full-text search across session artifacts.

    Returns matching artifacts with relevance scoring and highlights.
    """

@mcp.tool()
def get_artifact(artifact_id: int) -> dict:
    """Get full artifact content by ID."""

@mcp.tool()
def list_artifacts(
    session_id: str | None = None,
    artifact_type: str | None = None,
    file_path: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """List artifacts with filtering."""

@mcp.tool()
def get_session_timeline(session_id: str) -> dict:
    """
    Get chronological timeline of all artifacts for a session.

    Useful for understanding what happened in a past session.
    """

@mcp.tool()
def find_related_artifacts(
    file_path: str | None = None,
    task_id: str | None = None,
) -> dict:
    """Find artifacts related to a specific file or task."""
```

### Hook Integration

Capture artifacts automatically from hook events:

```python
# In hook_manager.py
async def _capture_artifact(self, event: HookEvent):
    """Extract and store artifacts from hook events."""

    if event.event_type == HookEventType.TOOL_RESULT:
        tool_name = event.data.get("tool_name")
        result = event.data.get("result")

        if tool_name in ["Edit", "Write"]:
            artifact_type = "code_change"
            file_path = event.data.get("file_path")
        elif tool_name == "Bash":
            artifact_type = self._classify_bash_output(result)
        else:
            artifact_type = "tool_output"

        await self.artifact_manager.create(
            session_id=event.session_id,
            artifact_type=artifact_type,
            title=f"{tool_name} result",
            content=result,
            file_path=file_path,
        )
```

### Phase 6: Configuration

```yaml
artifact_index:
  enabled: true
  capture_types:                              # Which artifact types to capture
    - code_change
    - commit
    - error
    - decision
  max_content_length: 50000                   # Truncate large artifacts
  retention_days: 90                          # Delete old artifacts
  fts_enabled: true                           # Enable full-text search
```

### Phase 6: Implementation Checklist

#### Phase 6.1: Storage Layer

- [ ] Create database migration for `session_artifacts` table
- [ ] Create FTS5 virtual table and triggers
- [ ] Create `src/storage/artifacts.py` with `LocalArtifactManager`
- [ ] Implement CRUD operations
- [ ] Implement FTS search with ranking

#### Phase 6.2: Artifact Capture

- [ ] Create `src/artifacts/capture.py` with `ArtifactCaptureManager`
- [ ] Integrate with hook system for automatic capture
- [ ] Implement artifact type classification
- [ ] Add content truncation for large artifacts

#### Phase 6.3: MCP Tools

- [ ] Create `src/mcp_proxy/tools/artifacts.py`
- [ ] Register as `gobby-artifacts` internal server
- [ ] Implement all tools listed above

#### Phase 6.4: CLI Commands

- [ ] Add `gobby artifacts search QUERY` command
- [ ] Add `gobby artifacts list [--session SESSION] [--type TYPE]`
- [ ] Add `gobby artifacts show ARTIFACT_ID`
- [ ] Add `gobby artifacts timeline SESSION_ID`

#### Phase 6.5: Handoff Integration

- [ ] Add artifact search to handoff context generation
- [ ] Auto-include relevant artifacts based on current task
- [ ] Add `{artifact_search}` template variable

---

## Phase 7: Enhanced Skill Routing

### Phase 7: Overview

Implement intelligent skill routing inspired by [SkillForge](https://github.com/tripleyak/SkillForge). Instead of simple pattern matching, use a multi-factor routing system that decides: USE_EXISTING, IMPROVE_EXISTING, CREATE_NEW, or COMPOSE.

**Inspiration:** SkillForge's 4-phase pipeline with 11 analytical lenses and quality scoring.

**Goal:** Transform `match_skills` from simple regex matching to intelligent routing that considers skill quality, specificity, and composition potential.

### Routing Decisions

| Decision | Description | When to Use |
| :--- | :--- | :--- |
| `USE_EXISTING` | Apply existing skill as-is | High-quality skill with exact match |
| `IMPROVE_EXISTING` | Update skill with new context | Good skill but missing recent patterns |
| `CREATE_NEW` | Generate new skill | No relevant skills or all low quality |
| `COMPOSE` | Combine multiple skills | Task spans multiple skill domains |

### Quality Scoring

```python
@dataclass
class SkillQuality:
    specificity: float        # 0-1: How targeted is this skill?
    completeness: float       # 0-1: Does it cover all aspects?
    currency: float           # 0-1: How recent is the skill?
    success_rate: float       # 0-1: Historical success when applied
    usage_count: int          # Times skill has been used
    composite_score: float    # Weighted combination
```

### Analytical Lenses

Evaluate skills through multiple perspectives:

1. **Domain Fit** - Does the skill's domain match the request?
2. **Scope Alignment** - Is the skill too broad or too narrow?
3. **Recency** - Was the skill created/updated recently?
4. **Success History** - Has this skill worked well before?
5. **Trigger Precision** - Does the trigger pattern match accurately?
6. **Instruction Quality** - Are instructions clear and actionable?
7. **Context Requirements** - Does the skill require specific context?
8. **Composition Potential** - Can this skill combine with others?
9. **Update Candidate** - Would this skill benefit from updates?
10. **Conflict Detection** - Does this skill conflict with others?
11. **Evolution Score** - How has this skill evolved over time?

### Enhanced Data Model

```sql
-- Add quality metrics to skills table
ALTER TABLE skills ADD COLUMN specificity REAL DEFAULT 0.5;
ALTER TABLE skills ADD COLUMN completeness REAL DEFAULT 0.5;
ALTER TABLE skills ADD COLUMN success_rate REAL DEFAULT 0.5;
ALTER TABLE skills ADD COLUMN usage_count INTEGER DEFAULT 0;
ALTER TABLE skills ADD COLUMN last_used_at TEXT;
ALTER TABLE skills ADD COLUMN last_updated_at TEXT;
ALTER TABLE skills ADD COLUMN domain TEXT;                    -- e.g., "testing", "git", "deployment"
ALTER TABLE skills ADD COLUMN parent_skill_id TEXT;           -- For skill evolution tracking

-- Skill application history
CREATE TABLE skill_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    skill_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    success BOOLEAN,
    feedback TEXT,                            -- Optional user feedback
    applied_at TEXT NOT NULL,
    FOREIGN KEY (skill_id) REFERENCES skills(id),
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);
```

### MCP Tools (gobby-skills enhanced)

```python
@mcp.tool()
def route_skill(
    prompt: str,
    context: str | None = None,
) -> dict:
    """
    Intelligent skill routing for a given prompt.

    Returns:
    - decision: USE_EXISTING | IMPROVE_EXISTING | CREATE_NEW | COMPOSE
    - matched_skills: List of relevant skills with quality scores
    - routing_reasoning: Explanation of routing decision
    - recommended_action: Specific next step
    """

@mcp.tool()
def analyze_skill_quality(skill_id: str) -> dict:
    """
    Analyze a skill through all 11 lenses.

    Returns quality breakdown and improvement suggestions.
    """

@mcp.tool()
def compose_skills(
    skill_ids: list[str],
    composition_prompt: str,
) -> dict:
    """
    Combine multiple skills into a composite skill.

    Creates new skill with instructions merged from inputs.
    """

@mcp.tool()
def improve_skill(
    skill_id: str,
    context: str,
    preserve_original: bool = True,          # Create new version vs update in place
) -> dict:
    """
    Improve a skill based on new context or feedback.

    If preserve_original=True, creates new skill with parent_skill_id reference.
    """

@mcp.tool()
def record_skill_application(
    skill_id: str,
    success: bool,
    feedback: str | None = None,
) -> dict:
    """Record whether skill application succeeded and update metrics."""
```

### Phase 7: Configuration

```yaml
skill_routing:
  enabled: true
  quality_weights:                            # Weights for composite score
    specificity: 0.25
    completeness: 0.20
    currency: 0.15
    success_rate: 0.30
    usage_count: 0.10
  min_quality_threshold: 0.4                  # Below this, suggest CREATE_NEW
  composition_similarity_threshold: 0.6       # Min similarity for COMPOSE suggestion
  auto_improve_threshold: 0.7                 # Above this, suggest IMPROVE vs CREATE
  domains:                                    # Domain classification hints
    - testing
    - git
    - deployment
    - documentation
    - debugging
    - refactoring
```

### Phase 7: Implementation Checklist

#### Phase 7.1: Quality Scoring

- [ ] Add quality columns to skills table (migration)
- [ ] Create `src/skills/quality.py` with `SkillQualityAnalyzer`
- [ ] Implement all 11 analytical lenses
- [ ] Implement composite score calculation

#### Phase 7.2: Routing Logic

- [ ] Create `src/skills/router.py` with `SkillRouter`
- [ ] Implement `route_skill()` with multi-factor decision
- [ ] Add skill similarity calculation (embedding-based)
- [ ] Implement composition potential detection

#### Phase 7.3: Application Tracking

- [ ] Create `skill_applications` table (migration)
- [ ] Implement `record_skill_application()`
- [ ] Update `success_rate` on each application
- [ ] Decay old success data over time

#### Phase 7.4: MCP Tools

- [ ] Update `src/mcp_proxy/tools/skills.py`
- [ ] Add `route_skill`, `analyze_skill_quality`, `compose_skills`, `improve_skill`
- [ ] Update `match_skills` to use router internally

#### Phase 7.5: CLI Commands

- [ ] Add `gobby skill route "prompt"` command
- [ ] Add `gobby skill analyze SKILL_ID`
- [ ] Add `gobby skill compose SKILL_ID1 SKILL_ID2 ...`

---

## Phase 8: Memory V2 - Semantic Search & Relationships

> **See [docs/plans/memory-v2.md](memory-v2.md) for full specification.**

This phase overhauls gobby-memory with Memora-inspired enhancements:

- **TF-IDF semantic search** - Zero-dependency local search (no OpenAI API required)
- **Cross-references** - Auto-link related memories based on similarity
- **Knowledge graph visualization** - Interactive HTML graph with vis.js
- **Enhanced tag filtering** - Boolean logic (AND/OR/NOT)

### Phases

| Phase | Feature | Effort |
|-------|---------|--------|
| 8.1 | TF-IDF Search Backend | 3-4 hours |
| 8.2 | Cross-References | 2-3 hours |
| 8.3 | Enhanced Tag Filtering | 1 hour |
| 8.4 | Knowledge Graph Visualization | 2 hours |
| 8.5 | Migration & Configuration | 1-2 hours |

**Total estimated effort: 10-12 hours**

### Why This Changed

The original sqlite-vec approach had issues:
- Native extension loading causes platform compatibility problems
- sentence-transformers adds ~500MB dependency
- TF-IDF achieves similar results for memory recall with zero dependencies

---

## Phase 9: Autonomous Work Loop ✅ COMPLETE

### Phase 9: Overview

Enable fully autonomous task execution where the agent works through the task queue until exhausted, stopped, or stuck. The loop survives session boundaries through handoff context and uses tasks as persistent state.

**Status: COMPLETE** - Implemented via workflow system rather than a dedicated `gobby-loop` server.

**Implemented Components:**
- ✅ `autonomous-loop.yaml` lifecycle workflow for automatic session chaining
- ✅ `autonomous-task.yaml` step-based workflow with task-driven execution, exit conditions, and premature stop handling
- ✅ `StopRegistry` class (`src/gobby/autonomous/stop_registry.py`) - thread-safe stop signal management
- ✅ `ProgressTracker` class (`src/gobby/autonomous/progress_tracker.py`) - progress monitoring
- ✅ `StuckDetector` class (`src/gobby/autonomous/stuck_detector.py`) - loop and stagnation detection
- ✅ HTTP endpoint: `POST /sessions/{session_id}/stop` for external stop signals
- ✅ Workflow actions: `check_stop_signal`, `track_progress`, `check_stuck`, `handle_stuck`

**Design Note:** The original plan below called for a dedicated `gobby-loop` MCP server and `gobby loop` CLI commands. This was superseded by integrating autonomous functionality into the existing workflow and session systems, which provides better composability and fewer moving parts. The detailed design below is preserved for historical context but is NOT the implemented approach.

### Phase 9: Core Design Principles

1. **Tasks as persistent state** - Workflow variables reset on session end; tasks persist across sessions
2. **Multi-layered termination** - Stop signals from HTTP, MCP, WebSocket, CLI, slash commands, and stuck detection
3. **Graceful degradation** - Pause/resume, skip stuck tasks, escalate to user when needed
4. **Session chaining** - Automatic handoff when context fills, continue in new session
5. **Observable progress** - Track commits, file changes, validation attempts for stuck detection

### Loop State Machine

```text
┌─────────────────────────────────────────────────────────────────┐
│                        DAEMON LAYER                             │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │                    STOP SIGNAL REGISTRY                     ││
│  │  - HTTP endpoint: POST /api/v1/loop/stop                    ││
│  │  - MCP tool: stop_autonomous_loop()                         ││
│  │  - WebSocket: {"type": "stop_loop"}                         ││
│  │  - CLI: gobby loop stop                                     ││
│  │  - Slash command: /loop stop                                ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     LIFECYCLE WORKFLOW                          │
│                   (Cross-Session Orchestration)                 │
│                                                                 │
│  on_session_start:                                              │
│    → Check if autonomous mode enabled                           │
│    → Inject continuation context                                │
│    → Inject autonomous instructions                             │
│    → Activate step-based workflow                               │
│                                                                 │
│  on_session_end:                                                │
│    → Check stop signal                                          │
│    → Check task queue (list_ready_tasks)                        │
│    → If tasks remain AND no stop → chain session                │
│    → If no tasks OR stop → terminate                            │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    STEP-BASED WORKFLOW                          │
│                   (Within-Session Structure)                    │
│                                                                 │
│   ┌──────────┐    ┌──────────┐    ┌───────────┐    ┌─────────┐ │
│   │  SELECT  │───▶│   PLAN   │───▶│  EXECUTE  │───▶│VALIDATE │ │
│   │   TASK   │    │(optional)│    │           │    │         │ │
│   └──────────┘    └──────────┘    └───────────┘    └─────────┘ │
│        ▲                               │                │       │
│        │                               │ (invalid)      │       │
│        │                               ◀────────────────┘       │
│        │                                                        │
│        │         ┌──────────┐                                   │
│        └─────────│   CLOSE  │◀──────────────────────────────────┘
│                  │   TASK   │         (valid)                   │
│                  └──────────┘                                   │
│                       │                                         │
│                       ▼                                         │
│              [No more tasks?] ───yes───▶ [COMPLETE]             │
│                       │no                                       │
│                       └──────▶ [Loop to SELECT]                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                       TASK LAYER                                │
│                   (Persistent State Machine)                    │
│                                                                 │
│  Task States: open → in_progress → closed                       │
│                        │                                        │
│                        ▼ (validation fails 3x)                  │
│                      stuck                                      │
│                                                                 │
│  Loop State derived from:                                       │
│    - list_ready_tasks() count                                   │
│    - Current in_progress task                                   │
│    - validation_fail_count                                      │
│    - progress_tracker metrics                                   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Termination Conditions

| Trigger | Source | Check Point | Graceful? |
| :--- | :--- | :--- | :--- |
| No ready tasks | Task system | SELECT step | Yes |
| Stop signal | External | Every step transition | Yes |
| Stuck on task | Task system | VALIDATE step (3 fails) | Partial |
| Context limit | Session | /compact → session end | Yes (chains) |
| Escape key | User | Immediate | Abort |
| /stop command | User | Before next action | Yes |

### MCP Tools (gobby-loop)

```python
@mcp.tool()
def start_autonomous_loop(
    from_spec: str | None = None,
    prompt: str | None = None,
    require_plan_approval: bool = False,
    max_validation_retries: int = 3,
) -> dict:
    """
    Start the autonomous work loop.

    If from_spec: Create parent task from spec file, expand into subtasks
    If prompt: Create parent task from prompt, expand into subtasks
    Otherwise: Work through existing ready tasks

    Returns:
    - loop_id: Identifier for this loop instance
    - initial_task: First task to be worked on
    - task_count: Number of ready tasks
    """

@mcp.tool()
def stop_autonomous_loop(
    session_id: str | None = None,
    reason: str = "user_requested",
    force: bool = False,
) -> dict:
    """
    Stop the autonomous loop gracefully.

    If session_id: Stop specific session
    Otherwise: Stop all autonomous sessions

    force=True: Immediate abort (no cleanup)
    force=False: Complete current task step, then stop
    """

@mcp.tool()
def get_loop_status(
    session_id: str | None = None,
) -> dict:
    """
    Get current autonomous loop status.

    Returns:
    - active: Whether loop is running
    - current_step: select_task, plan, execute, validate, close_task, stuck, paused
    - current_task: Task being worked on
    - tasks_completed: Count this session
    - tasks_remaining: Ready tasks in queue
    - progress: Progress tracker metrics
    - stop_requested: Whether stop signal pending
    """

@mcp.tool()
def pause_loop(session_id: str) -> dict:
    """
    Pause the autonomous loop without stopping.

    Agent returns to interactive mode.
    Use resume_loop() to continue.
    """

@mcp.tool()
def resume_loop(session_id: str) -> dict:
    """Resume a paused autonomous loop."""

@mcp.tool()
def skip_current_task(
    session_id: str,
    reason: str = "user_requested",
) -> dict:
    """
    Skip the current task and move to next.

    Marks current task as blocked with reason.
    Selects next ready task.
    """
```

### Phase 9: CLI Commands

```bash
# Start autonomous loop
gobby loop start                              # Work through existing tasks
gobby loop start --prompt "Build feature X"   # Create + expand task, then work
gobby loop start --from-spec ./task-spec.md   # Create from spec file

# Control running loop
gobby loop stop [--session SESSION] [--force]
gobby loop pause [--session SESSION]
gobby loop resume [--session SESSION]
gobby loop skip [--session SESSION] [--reason "..."]

# Monitor
gobby loop status [--session SESSION]
gobby loop watch [--session SESSION]          # Real-time progress stream
```

### Phase 9: Configuration

```yaml
autonomous_loop:
  enabled: true

  # Execution settings
  require_plan_approval: false              # Require approval before execute step
  max_validation_retries: 3                 # Retries before marking stuck

  # Stuck detection
  stuck_detection:
    enabled: true
    task_selection_threshold: 3             # Same task selected N times = stuck
    stagnation_threshold_minutes: 30        # No progress for N minutes = stuck
    validation_fail_threshold: 3            # N validation failures = stuck

  # Session chaining
  session_chaining:
    enabled: true
    max_chain_depth: 10                     # Max consecutive sessions
    handoff_template: "{{ compact_markdown or summary_markdown }}"

  # Progress tracking
  progress_tracking:
    enabled: true
    track_commits: true
    track_file_changes: true
    emit_websocket_events: true

  # Termination
  graceful_stop_timeout_seconds: 30         # Wait for current step to complete
```

### Phase 9: Implementation Checklist (ACTUAL STATUS)

#### Phase 9.1: Stop Signal Infrastructure ✅ COMPLETE

- [x] `src/gobby/autonomous/stop_registry.py` with `StopRegistry` class
- [x] `session_stop_signals` table (not `loop_stop_signals` - per-session design)
- [x] Thread-safe stop signal management
- [x] Workflow actions: `check_stop_signal`, `clear_stop_signal`

#### Phase 9.2: Progress Tracking ✅ COMPLETE

- [x] `src/gobby/autonomous/progress_tracker.py` with `ProgressTracker` class
- [x] Progress recording from tool results
- [x] Stagnation detection algorithm
- [x] Workflow actions: `start_progress_tracking`, `stop_progress_tracking`, `record_progress`

#### Phase 9.3: Stuck Detection ✅ COMPLETE

- [x] `src/gobby/autonomous/stuck_detector.py` with `StuckDetector` class
- [x] Task selection loop detection
- [x] Workflow actions: `check_stuck`, `handle_stuck`

#### Phase 9.4-9.8: MCP/HTTP/WebSocket/CLI/Slash Commands ❌ SUPERSEDED

The original plan called for a dedicated `gobby-loop` MCP server and CLI commands.
This was superseded by integrating with existing systems:
- **Stop signals**: Use `POST /sessions/{session_id}/stop` HTTP endpoint
- **Workflow control**: Use `gobby workflows activate/deactivate autonomous-task`
- **Variables**: Use `gobby-workflows.set_variable` MCP tool

#### Phase 9.9: Workflow Files ✅ COMPLETE

- [x] `autonomous-task.yaml` step-based workflow with exit conditions
- [x] `autonomous-loop.yaml` lifecycle workflow for session chaining
- [x] Installed to `~/.gobby/workflows/` via `gobby install`

#### Phase 9.10: Integration Testing 🔶 PARTIAL

- [x] Tests in `tests/autonomous/test_autonomous.py`
- [x] Tests in `tests/workflows/test_autonomous_task.py`
- [ ] Full end-to-end integration testing

---

## Decisions

| # | Question | Decision | Rationale |
| :--- | :--- | :--- | :--- |
| 1 | **Worktree management location** | Moved to SUBAGENTS.md | Tightly coupled with subagent spawning |
| 2 | **Merge conflict context** | Configurable line window | Balance token efficiency vs context quality |
| 3 | **QA loop limit** | 3 retries default | Prevent infinite loops while allowing recovery |
| 4 | **GitHub auth** | Environment variable | Standard pattern, works with gh CLI |
| 5 | **Linear auth** | API key | Linear's standard auth method |
| 6 | **Pipeline phases** | Fixed 5-phase model | Clear structure, matches Auto-Claude pattern |
| 7 | **External validator** | Separate agent context | Avoids bias from implementation agent |
| 8 | **Loop state persistence** | Tasks (not workflow variables) | Workflow vars reset on session end; tasks survive |
| 9 | **Stop signal registry** | Thread-safe in-memory + SQLite | Fast checks, persistence across daemon restarts |
| 10 | **Stuck detection layers** | 3 layers (validation, selection, stagnation) | Comprehensive coverage of stuck scenarios |
| 11 | **Session chaining trigger** | on_session_end lifecycle hook | Natural hook point, runs after handoff extraction |
| 12 | **Autonomous mode activation** | session.data.autonomous flag | Clean separation, explicit opt-in per session |

---

## Priority Assessment

| Feature | Value | Effort | Priority | Inspiration |
| :--- | :--- | :--- | :--- | :--- |
| Merge Resolution | High | High | P1 | Auto-Claude |
| QA Loop Enhancement | Medium | Low | P2 | Auto-Claude |
| GitHub Integration | High | Medium | P2 | Auto-Claude |
| Linear Integration | Medium | Medium | P3 | Auto-Claude |
| Pipeline Workflows | Medium | High | P3 | Auto-Claude |
| **Artifact Index** | **High** | **Medium** | **P1** | Continuous-Claude v2 |
| **Enhanced Skill Routing** | **High** | **Medium** | **P2** | SkillForge |
| **Memory V2 (Search + Relationships)** | **High** | **Medium** | **P2** | Memora |
| ~~Autonomous Work Loop~~ | ~~High~~ | ~~High~~ | ✅ **DONE** | Original Design |

**Recommendations:**

1. **Immediate wins** - Artifact Index (Phase 6) provides high value with moderate effort and enables better session continuity
2. **After SUBAGENTS Phase 4** - Merge Resolution (Phase 1) requires worktrees to be implemented first
3. **Intelligence layer** - Skill Routing (Phase 7) + Memory V2 (Phase 8) make Gobby smarter over time
4. **External integrations** - GitHub/Linear after core intelligence is solid

**Dependencies:**
- Phase 1 (Merge Resolution) requires SUBAGENTS.md Phase 4 (`gobby-worktrees`)
