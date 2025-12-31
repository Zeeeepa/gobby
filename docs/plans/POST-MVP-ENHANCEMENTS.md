# Post-MVP Features: Auto-Claude Inspired Enhancements

## Overview

This document outlines high-value features inspired by [Auto-Claude](https://github.com/AndyMik90/Auto-Claude), an autonomous multi-agent AI coding framework. These features would enhance Gobby's capabilities for parallel agent coordination, intelligent merge handling, and external integrations.

**Inspiration:** <https://github.com/AndyMik90/Auto-Claude>

## Build Order

```text
Phase 1: Worktree Agent Coordination (extends existing worktree-manager skill)
    ↓
Phase 2: Intelligent Merge Resolution (new gobby-merge internal server)
    ↓
Phase 3: QA Validation Loop Enhancement (extends gobby-tasks validation)
    ↓
Phase 4: GitHub Integration (new gobby-github internal server)
    ↓
Phase 5: Linear Integration (new gobby-linear internal server)
    ↓
Phase 6: Structured Pipeline Workflows (BMAD integration)
```

Each phase is independently valuable. Phases 1-3 enhance local development workflows. Phases 4-5 add external integrations. Phase 6 ties everything together with structured pipelines.

---

## Phase 1: Worktree Agent Coordination

### Overview

Enable multiple Claude Code agents to work in parallel, each in an isolated git worktree. Gobby coordinates which agent owns which worktree and tracks progress via `gobby-tasks`.

**Current State:** The `worktree-manager` skill exists but lacks daemon-level coordination.

**Goal:** Daemon-managed worktree registry with agent assignment, status tracking, and coordinated merging.

### Core Design Principles

1. **Isolation by default** - Each agent works in its own worktree, protecting main branch
2. **Task-driven assignment** - Worktrees are created for specific tasks from `gobby-tasks`
3. **Centralized coordination** - Daemon tracks all active worktrees across projects
4. **Graceful cleanup** - Stale worktrees detected and cleaned up automatically

### Data Model

```sql
CREATE TABLE worktrees (
    id TEXT PRIMARY KEY,                    -- wt-{6 chars}
    project_id TEXT NOT NULL,
    task_id TEXT,                           -- Optional: linked gobby-task
    branch_name TEXT NOT NULL,
    worktree_path TEXT NOT NULL,            -- Absolute path
    base_branch TEXT DEFAULT 'main',
    agent_session_id TEXT,                  -- Current owning session
    status TEXT DEFAULT 'active',           -- active, stale, merged, abandoned
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    merged_at TEXT,
    FOREIGN KEY (project_id) REFERENCES projects(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id),
    FOREIGN KEY (agent_session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_worktrees_project ON worktrees(project_id);
CREATE INDEX idx_worktrees_status ON worktrees(status);
CREATE INDEX idx_worktrees_task ON worktrees(task_id);
```

### MCP Tools (gobby-worktrees)

```python
@mcp.tool()
def create_worktree(
    task_id: str | None = None,
    branch_name: str | None = None,         # Auto-generated from task if not provided
    base_branch: str = "main",
) -> dict:
    """
    Create a new worktree for isolated development.

    If task_id provided:
    - Branch name derived from task title (kebab-case)
    - Worktree linked to task for tracking
    - Task marked as in_progress

    Returns worktree path and branch name.
    """

@mcp.tool()
def list_worktrees(
    status: str | None = None,              # active, stale, merged, abandoned
    project_id: str | None = None,
) -> dict:
    """List all worktrees with their status and owning agents."""

@mcp.tool()
def get_worktree(worktree_id: str) -> dict:
    """Get worktree details including linked task and agent."""

@mcp.tool()
def claim_worktree(
    worktree_id: str,
    session_id: str | None = None,          # Current session if not provided
) -> dict:
    """Claim ownership of a worktree for the current agent session."""

@mcp.tool()
def release_worktree(worktree_id: str) -> dict:
    """Release ownership without deleting. Worktree becomes available."""

@mcp.tool()
def delete_worktree(
    worktree_id: str,
    force: bool = False,                    # Delete even if uncommitted changes
) -> dict:
    """Delete a worktree and its branch."""

@mcp.tool()
def spawn_agent_in_worktree(
    worktree_id: str,
    prompt: str | None = None,              # Initial prompt for the agent
    terminal: str = "ghostty",              # ghostty, iterm, terminal
) -> dict:
    """
    Launch a new Claude Code agent in the specified worktree.

    Opens a new terminal window with Claude Code started in the worktree directory.
    Agent session is linked to the worktree for tracking.
    """

@mcp.tool()
def sync_worktree_from_main(worktree_id: str) -> dict:
    """Rebase or merge latest main into worktree branch."""

@mcp.tool()
def detect_stale_worktrees(
    threshold_hours: int = 24,
) -> dict:
    """Find worktrees with no activity beyond threshold."""

@mcp.tool()
def cleanup_stale_worktrees(
    threshold_hours: int = 24,
    dry_run: bool = True,
) -> dict:
    """Delete stale worktrees (dry_run=True to preview)."""
```

### CLI Commands

```bash
# Worktree management
gobby worktree create [--task TASK_ID] [--branch NAME] [--base BRANCH]
gobby worktree list [--status STATUS] [--project PROJECT]
gobby worktree show WORKTREE_ID
gobby worktree delete WORKTREE_ID [--force]

# Agent coordination
gobby worktree spawn WORKTREE_ID [--prompt "..."] [--terminal ghostty|iterm]
gobby worktree claim WORKTREE_ID
gobby worktree release WORKTREE_ID

# Maintenance
gobby worktree sync WORKTREE_ID           # Sync from main
gobby worktree stale [--hours N]          # List stale worktrees
gobby worktree cleanup [--hours N] [--dry-run]
```

### Configuration

```yaml
worktrees:
  enabled: true
  base_path: ".worktrees"                   # Relative to project root
  default_terminal: "ghostty"               # ghostty, iterm, terminal
  stale_threshold_hours: 24
  auto_cleanup: false                       # Auto-delete stale worktrees
  max_concurrent: 12                        # Max parallel worktrees
  branch_prefix: "agent/"                   # Prefix for auto-generated branches
```

### Implementation Checklist

#### Phase 1.1: Storage Layer

- [ ] Create database migration for worktrees table
- [ ] Create `src/storage/worktrees.py` with `LocalWorktreeManager` class
- [ ] Implement CRUD operations (create, get, update, delete, list)
- [ ] Implement status transitions (active → stale → merged/abandoned)
- [ ] Add unit tests for LocalWorktreeManager

#### Phase 1.2: Git Operations

- [ ] Create `src/worktrees/git.py` with `WorktreeGitManager` class
- [ ] Implement `create_worktree()` - git worktree add
- [ ] Implement `delete_worktree()` - git worktree remove + branch delete
- [ ] Implement `sync_from_main()` - rebase/merge from base branch
- [ ] Implement `get_worktree_status()` - uncommitted changes, ahead/behind
- [ ] Add unit tests for git operations

#### Phase 1.3: Agent Spawning

- [ ] Create `src/worktrees/spawn.py` with agent spawning logic
- [ ] Implement Ghostty terminal spawning
- [ ] Implement iTerm terminal spawning
- [ ] Implement generic Terminal.app spawning
- [ ] Pass initial prompt via environment or file
- [ ] Register spawned session with daemon

#### Phase 1.4: MCP Tools

- [ ] Create `src/mcp_proxy/tools/worktrees.py` with `WorktreeToolRegistry`
- [ ] Register as `gobby-worktrees` internal server
- [ ] Implement all MCP tools listed above
- [ ] Add tool documentation and schemas

#### Phase 1.5: CLI Commands

- [ ] Add `gobby worktree` command group
- [ ] Implement all CLI commands listed above
- [ ] Add help text and examples

#### Phase 1.6: Integration

- [ ] Update `worktree-manager` skill to use daemon coordination
- [ ] Add worktree context to session handoff
- [ ] Link worktree status to task status changes
- [ ] Add WebSocket events for worktree changes

---

## Phase 2: Intelligent Merge Resolution

### Overview

When merging worktree branches back to main, use AI to resolve conflicts intelligently. Key insight from Auto-Claude: send only conflict regions to AI (~98% prompt reduction).

### Core Design Principles

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

### Data Model

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

### CLI Commands

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

### Configuration

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

### Implementation Checklist

#### Phase 2.1: Conflict Extraction

- [ ] Create `src/merge/extractor.py` with conflict hunk extraction
- [ ] Implement `extract_conflict_hunks()` - parse <<<<<<< markers
- [ ] Implement context windowing (configurable lines around conflict)
- [ ] Calculate token savings vs full file
- [ ] Add unit tests with various conflict patterns

#### Phase 2.2: Resolution Engine

- [ ] Create `src/merge/resolver.py` with `MergeResolver` class
- [ ] Implement tiered resolution strategy
- [ ] Implement parallel file resolution
- [ ] Implement validation (syntax, markers, completeness)
- [ ] Add fallback escalation logic

#### Phase 2.3: Storage & Tracking

- [ ] Create database migrations
- [ ] Create `src/storage/merges.py` with `LocalMergeManager`
- [ ] Track resolution progress and history
- [ ] Store AI reasoning for audit trail

#### Phase 2.4: MCP Tools

- [ ] Create `src/mcp_proxy/tools/merge.py`
- [ ] Register as `gobby-merge` internal server
- [ ] Implement all tools listed above

#### Phase 2.5: CLI Commands

- [ ] Add `gobby merge` command group
- [ ] Implement all commands listed above
- [ ] Add progress indicators for long operations

#### Phase 2.6: Integration

- [ ] Hook into worktree merge flow
- [ ] Update task status on successful merge
- [ ] Add merge metadata to session handoff

---

## Phase 3: Enhanced QA Validation Loop

### Overview

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

### Implementation Checklist

#### Phase 3.1: Validation History

- [ ] Add `validation_attempts` table to track all attempts
- [ ] Store validation result, issues, timestamp per attempt
- [ ] Implement `get_validation_history()` query

#### Phase 3.2: Fix Agent

- [ ] Create `src/tasks/fix_agent.py` with fix attempt logic
- [ ] Implement `run_fix_attempt()` - spawn agent with context
- [ ] Capture changes made during fix attempt
- [ ] Re-run validation after fix

#### Phase 3.3: QA Loop

- [ ] Implement `validate_and_fix()` loop logic
- [ ] Add retry counter and max limit
- [ ] Implement fix subtask creation on final failure
- [ ] Update task status to 'failed' when exhausted

#### Phase 3.4: Integration

- [ ] Hook into `close_task` flow (optional auto-validate)
- [ ] Add QA loop option to task expansion (validate subtasks)
- [ ] Add CLI commands for manual QA loop trigger

---

## Phase 4: GitHub Integration

### Overview

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

### CLI Commands

```bash
gobby github connect OWNER/REPO [--token TOKEN]
gobby github import [--labels LABEL,...] [--state open|closed|all] [--limit N]
gobby github sync [--direction in|out|both]
gobby github pr create TASK_ID [--worktree WORKTREE_ID] [--draft]
gobby github pr status TASK_ID
gobby github disconnect
```

### Configuration

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

### Implementation Checklist

#### Phase 4.1: GitHub Client

- [ ] Create `src/integrations/github.py` with GitHub API client
- [ ] Implement issue listing/fetching
- [ ] Implement PR creation
- [ ] Implement status sync
- [ ] Handle rate limiting and pagination

#### Phase 4.2: Task Mapping

- [ ] Add `github_issue_number` and `github_pr_number` to tasks table
- [ ] Implement issue → task mapping
- [ ] Implement task → issue sync
- [ ] Handle label mapping

#### Phase 4.3: MCP Tools & CLI

- [ ] Create `src/mcp_proxy/tools/github.py`
- [ ] Register as `gobby-github` internal server
- [ ] Add CLI commands

---

## Phase 5: Linear Integration

### Overview

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

### Configuration

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

### Implementation Checklist

#### Phase 5.1: Linear Client

- [ ] Create `src/integrations/linear.py` with Linear GraphQL client
- [ ] Implement issue listing/fetching
- [ ] Implement issue creation/update
- [ ] Handle pagination

#### Phase 5.2: Task Mapping

- [ ] Add `linear_issue_id` to tasks table
- [ ] Implement bidirectional sync
- [ ] Map states and labels

#### Phase 5.3: MCP Tools & CLI

- [ ] Create `src/mcp_proxy/tools/linear.py`
- [ ] Register as `gobby-linear` internal server
- [ ] Add CLI commands

---

## Phase 6: Structured Pipeline Workflows

### Overview

Formalize the Spec → Plan → Implement → QA → Merge pipeline as explicit workflow phases. Each phase has distinct agent roles and tool access.

**Integration:** Leverage existing BMAD workflows for structured execution.

### Pipeline Phases

| Phase | Agent Role | Key Actions | Tools Available |
|-------|------------|-------------|-----------------|
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

### Implementation Checklist

#### Phase 6.1: Pipeline State

- [ ] Create `pipelines` table
- [ ] Create `pipeline_phases` table for history
- [ ] Implement state machine for phase transitions

#### Phase 6.2: Phase Validation

- [ ] Implement phase entry/exit criteria
- [ ] Validate spec exists before plan phase
- [ ] Validate tasks created before implement phase
- [ ] Validate tests pass before merge phase

#### Phase 6.3: MCP Tools & CLI

- [ ] Create `src/mcp_proxy/tools/pipeline.py`
- [ ] Register as `gobby-pipeline` internal server
- [ ] Add CLI commands

#### Phase 6.4: BMAD Integration

- [ ] Map pipeline phases to BMAD workflows
- [ ] Enable BMAD agent handoff between phases
- [ ] Integrate with existing BMAD skills

---

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | **Worktree storage** | SQLite table + filesystem | Track metadata in DB, actual worktrees on disk |
| 2 | **Agent spawning** | Terminal-based (Ghostty/iTerm) | Claude Code runs in terminal, leverage existing patterns |
| 3 | **Merge conflict context** | Configurable line window | Balance token efficiency vs context quality |
| 4 | **QA loop limit** | 3 retries default | Prevent infinite loops while allowing recovery |
| 5 | **GitHub auth** | Environment variable | Standard pattern, works with gh CLI |
| 6 | **Linear auth** | API key | Linear's standard auth method |
| 7 | **Pipeline phases** | Fixed 5-phase model | Clear structure, matches Auto-Claude pattern |
| 8 | **External validator** | Separate agent context | Avoids bias from implementation agent |

---

## Priority Assessment

| Feature | Value | Effort | Priority |
|---------|-------|--------|----------|
| Worktree Coordination | High | Medium | P1 |
| Merge Resolution | High | High | P1 |
| QA Loop Enhancement | Medium | Low | P2 |
| GitHub Integration | High | Medium | P2 |
| Linear Integration | Medium | Medium | P3 |
| Pipeline Workflows | Medium | High | P3 |

**Recommendation:** Start with Worktree Coordination (Phase 1) as it extends existing functionality and enables parallel development. Then add Merge Resolution (Phase 2) to complete the parallel agent workflow.
