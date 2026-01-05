# Post-MVP Features: AI Project Inspired Enhancements

## Overview

This document outlines high-value features inspired by trending AI projects. These features would enhance Gobby's capabilities for parallel agent coordination, intelligent merge handling, searchable history, and smart context management.

**Inspirations:**

- [Auto-Claude](https://github.com/AndyMik90/Auto-Claude) - Multi-agent orchestration with worktree isolation (Phases 1-6)
- [Continuous-Claude v2](https://github.com/parcadei/Continuous-Claude-v2) - Ledger-based state, artifact indexing (Phase 7)
- [SkillForge](https://github.com/tripleyak/SkillForge) - Intelligent skill routing and quality scoring (Phase 8)
- [KnowNote](https://github.com/MrSibe/KnowNote) - Local-first semantic search with sqlite-vec (Phase 9)
- Original Design - Task-driven autonomous execution with multi-surface termination controls (Phase 10)

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
    ↓
Phase 7: Artifact Index (searchable session history with FTS5)
    ↓
Phase 8: Enhanced Skill Routing (intelligent skill matching)
    ↓
Phase 9: Semantic Memory Search (sqlite-vec local vectors)
    ↓
Phase 10: Autonomous Work Loop (task-driven execution with termination controls)
```

Each phase is independently valuable. Phases 1-3 enhance local development workflows. Phases 4-5 add external integrations. Phase 6 ties everything together with structured pipelines. Phases 7-9 add intelligent search and context capabilities inspired by trending AI projects. Phase 10 enables fully autonomous task execution with robust termination controls.

---

## Phase 1: Worktree Agent Coordination

### Phase 1: Overview

Enable multiple Claude Code agents to work in parallel, each in an isolated git worktree. Gobby coordinates which agent owns which worktree and tracks progress via `gobby-tasks`.

**Current State:** The `worktree-manager` skill exists but lacks daemon-level coordination.

**Goal:** Daemon-managed worktree registry with agent assignment, status tracking, and coordinated merging.

### Core Design Principles

1. **Isolation by default** - Each agent works in its own worktree, protecting main branch
2. **Task-driven assignment** - Worktrees are created for specific tasks from `gobby-tasks`
3. **Centralized coordination** - Daemon tracks all active worktrees across projects
4. **Graceful cleanup** - Stale worktrees detected and cleaned up automatically

### Phase 1: Data Model

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

### Phase 1: CLI Commands

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

### Phase 1: Configuration

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

### Phase 1: Implementation Checklist

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

#### Phase 1.7: Workflow Exclusions for Worktree Agents

- [ ] Set `is_worktree: true` variable in worktree agent sessions
- [ ] Exclude worktree agents from `require_task_complete` enforcement
  - Main session owns the parent task; worktree agents work on assigned subtasks
  - Check `variables.get('is_worktree')` in `on_after_agent` trigger
- [ ] Allow worktree agents to stop when their assigned task is complete
- [ ] Main session tracks overall epic progress across all worktree agents

---

## Phase 2: Intelligent Merge Resolution

### Phase 2: Overview

When merging worktree branches back to main, use AI to resolve conflicts intelligently. Key insight from Auto-Claude: send only conflict regions to AI (~98% prompt reduction).

### Phase 2: Core Design Principles

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

### Phase 2: Data Model

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

### Phase 2: CLI Commands

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

### Phase 2: Configuration

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

### Phase 2: Implementation Checklist

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

### Phase 3: Overview

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

### Phase 3: Implementation Checklist

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

### Phase 4: Overview

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

### Phase 4: CLI Commands

```bash
gobby github connect OWNER/REPO [--token TOKEN]
gobby github import [--labels LABEL,...] [--state open|closed|all] [--limit N]
gobby github sync [--direction in|out|both]
gobby github pr create TASK_ID [--worktree WORKTREE_ID] [--draft]
gobby github pr status TASK_ID
gobby github disconnect
```

### Phase 4: Configuration

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

### Phase 4: Implementation Checklist

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

### Phase 5: Overview

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

### Phase 5: Configuration

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

### Phase 5: Implementation Checklist

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

### Phase 6: Overview

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

### Phase 6: Implementation Checklist

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

## Phase 7: Artifact Index (Searchable Session History)

### Phase 7: Overview

Implement a searchable index of session artifacts inspired by [Continuous-Claude v2](https://github.com/parcadei/Continuous-Claude-v2). Their "clear, don't compact" philosophy uses ledger-based state management with an **Artifact Index** (SQLite + FTS5) for fast retrieval of past session content.

**Inspiration:** Continuous-Claude's approach to lossless session history vs. lossy summarization.

**Goal:** Enable agents to search across all past session artifacts—code changes, tool outputs, decisions—using full-text search.

### Phase 7: Core Design Principles

1. **Lossless preservation** - Store all artifacts, not just summaries
2. **Fast retrieval** - FTS5 index for sub-second search across thousands of sessions
3. **Structured metadata** - Track artifact type, session, timestamp, file paths
4. **Contextual injection** - Recall relevant artifacts during session handoff

### Phase 7: Data Model

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

### Phase 7: Configuration

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

### Phase 7: Implementation Checklist

#### Phase 7.1: Storage Layer

- [ ] Create database migration for `session_artifacts` table
- [ ] Create FTS5 virtual table and triggers
- [ ] Create `src/storage/artifacts.py` with `LocalArtifactManager`
- [ ] Implement CRUD operations
- [ ] Implement FTS search with ranking

#### Phase 7.2: Artifact Capture

- [ ] Create `src/artifacts/capture.py` with `ArtifactCaptureManager`
- [ ] Integrate with hook system for automatic capture
- [ ] Implement artifact type classification
- [ ] Add content truncation for large artifacts

#### Phase 7.3: MCP Tools

- [ ] Create `src/mcp_proxy/tools/artifacts.py`
- [ ] Register as `gobby-artifacts` internal server
- [ ] Implement all tools listed above

#### Phase 7.4: CLI Commands

- [ ] Add `gobby artifacts search QUERY` command
- [ ] Add `gobby artifacts list [--session SESSION] [--type TYPE]`
- [ ] Add `gobby artifacts show ARTIFACT_ID`
- [ ] Add `gobby artifacts timeline SESSION_ID`

#### Phase 7.5: Handoff Integration

- [ ] Add artifact search to handoff context generation
- [ ] Auto-include relevant artifacts based on current task
- [ ] Add `{artifact_search}` template variable

---

## Phase 8: Enhanced Skill Routing

### Phase 8: Overview

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

### Phase 8: Configuration

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

### Phase 8: Implementation Checklist

#### Phase 8.1: Quality Scoring

- [ ] Add quality columns to skills table (migration)
- [ ] Create `src/skills/quality.py` with `SkillQualityAnalyzer`
- [ ] Implement all 11 analytical lenses
- [ ] Implement composite score calculation

#### Phase 8.2: Routing Logic

- [ ] Create `src/skills/router.py` with `SkillRouter`
- [ ] Implement `route_skill()` with multi-factor decision
- [ ] Add skill similarity calculation (embedding-based)
- [ ] Implement composition potential detection

#### Phase 8.3: Application Tracking

- [ ] Create `skill_applications` table (migration)
- [ ] Implement `record_skill_application()`
- [ ] Update `success_rate` on each application
- [ ] Decay old success data over time

#### Phase 8.4: MCP Tools

- [ ] Update `src/mcp_proxy/tools/skills.py`
- [ ] Add `route_skill`, `analyze_skill_quality`, `compose_skills`, `improve_skill`
- [ ] Update `match_skills` to use router internally

#### Phase 8.5: CLI Commands

- [ ] Add `gobby skill route "prompt"` command
- [ ] Add `gobby skill analyze SKILL_ID`
- [ ] Add `gobby skill compose SKILL_ID1 SKILL_ID2 ...`

---

## Phase 9: Semantic Memory Search with sqlite-vec

### Phase 9: Overview

Implement vector-based semantic search for `gobby-memory` using [sqlite-vec](https://github.com/asg017/sqlite-vec), inspired by [KnowNote](https://github.com/MrSibe/KnowNote). This enables "recall by meaning" rather than just keyword matching.

**Inspiration:** KnowNote's local-first RAG pipeline with SQLite + sqlite-vec.

**Goal:** Enable semantic memory recall without requiring external vector databases or APIs.

### Why sqlite-vec?

- **Local-first** - No external services, works offline
- **Single file** - Embeddings stored in same SQLite database
- **Fast** - Optimized SIMD vector operations
- **Portable** - Pure SQLite extension, cross-platform

### Architecture

```text
Memory Recall Query
        │
        ▼
┌───────────────────────────────────────────────────┐
│                 Hybrid Search                      │
│  ┌─────────────────┐  ┌─────────────────────────┐ │
│  │  Text Search    │  │  Vector Search          │ │
│  │  (FTS5)         │  │  (sqlite-vec)           │ │
│  │  Fast, exact    │  │  Semantic, fuzzy        │ │
│  └────────┬────────┘  └───────────┬─────────────┘ │
│           │                       │               │
│           └───────────┬───────────┘               │
│                       ▼                           │
│              Reciprocal Rank Fusion               │
│              (combine results)                    │
└───────────────────────┬───────────────────────────┘
                        │
                        ▼
                 Ranked Results
```

### Phase 9: Data Model

```sql
-- Load sqlite-vec extension (on connection)
-- .load vec0

-- Memory embeddings (separate table for clean schema)
CREATE TABLE memory_embeddings (
    memory_id TEXT PRIMARY KEY,
    embedding BLOB NOT NULL,                  -- vec_f32(384) for all-MiniLM-L6-v2
    model TEXT NOT NULL,                      -- embedding model used
    created_at TEXT NOT NULL,
    FOREIGN KEY (memory_id) REFERENCES memories(id) ON DELETE CASCADE
);

-- Vector search index
CREATE VIRTUAL TABLE memory_vec USING vec0(
    embedding float[384]
);

-- Trigger to sync vec table with embeddings
CREATE TRIGGER memory_embeddings_ai AFTER INSERT ON memory_embeddings BEGIN
    INSERT INTO memory_vec(rowid, embedding)
    SELECT me.rowid, me.embedding
    FROM memory_embeddings me WHERE me.memory_id = new.memory_id;
END;
```

### Local Embedding Generation

Use a small, fast local model to avoid API costs:

```python
# Using sentence-transformers
from sentence_transformers import SentenceTransformer

class LocalEmbedder:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def embed(self, text: str) -> list[float]:
        return self.model.encode(text).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        return self.model.encode(texts).tolist()
```

### Enhanced Recall

```python
@mcp.tool()
def recall(
    query: str,
    search_mode: str = "hybrid",              # text, vector, hybrid
    memory_type: str | None = None,
    min_importance: float = 0.0,
    limit: int = 10,
    include_scores: bool = False,
) -> dict:
    """
    Recall memories with semantic search support.

    search_mode:
    - "text": FTS5 keyword search (fast, exact matches)
    - "vector": Semantic similarity search (meaning-based)
    - "hybrid": Combine both with reciprocal rank fusion
    """

@mcp.tool()
def find_similar_memories(
    memory_id: str,
    limit: int = 5,
) -> dict:
    """Find memories semantically similar to a given memory."""

@mcp.tool()
def cluster_memories(
    memory_type: str | None = None,
    n_clusters: int = 5,
) -> dict:
    """
    Cluster memories by semantic similarity.

    Useful for discovering themes and patterns in stored memories.
    """
```

### Phase 9: Configuration

```yaml
memory:
  # ... existing config ...

  semantic_search:
    enabled: true
    embedding_model: "all-MiniLM-L6-v2"       # Local model
    embedding_dimensions: 384
    search_mode: "hybrid"                      # Default search mode
    hybrid_alpha: 0.5                          # Weight for vector vs text (0=text, 1=vector)
    auto_embed: true                           # Embed new memories automatically
    batch_size: 32                             # Batch size for embedding generation
```

### Phase 9: Implementation Checklist

#### Phase 9.1: sqlite-vec Integration

- [ ] Add sqlite-vec as dependency (pip install sqlite-vec)
- [ ] Create extension loading in database connection
- [ ] Create migration for `memory_embeddings` and `memory_vec` tables
- [ ] Test extension loading across platforms

#### Phase 9.2: Local Embedding

- [ ] Add sentence-transformers as optional dependency
- [ ] Create `src/memory/embeddings.py` with `LocalEmbedder`
- [ ] Implement lazy model loading (load on first use)
- [ ] Add embedding generation to memory creation flow
- [ ] Add batch embedding for existing memories

#### Phase 9.3: Vector Search

- [ ] Implement `vector_search(query_embedding, limit)` using vec0
- [ ] Implement `hybrid_search(query, limit, alpha)` with RRF
- [ ] Add similarity threshold filtering
- [ ] Implement `find_similar_memories()`

#### Phase 9.4: MCP Tool Updates

- [ ] Update `recall()` to support `search_mode` parameter
- [ ] Add `find_similar_memories()` tool
- [ ] Add `cluster_memories()` tool (optional, depends on sklearn)

#### Phase 9.5: CLI Commands

- [ ] Add `--mode` flag to `gobby memory recall` command
- [ ] Add `gobby memory embed` command to generate embeddings for existing memories
- [ ] Add `gobby memory similar MEMORY_ID` command

#### Phase 9.6: Migration & Backfill

- [ ] Create migration script for existing memories
- [ ] Add `gobby memory migrate-embeddings` command
- [ ] Handle memories without embeddings gracefully in search

---

## Phase 10: Autonomous Work Loop

### Phase 10: Overview

Enable fully autonomous task execution where the agent works through the task queue until exhausted, stopped, or stuck. The loop survives session boundaries through handoff context and uses tasks as persistent state.

**Current State:** Session-lifecycle workflow handles handoff context. Task system provides persistent work tracking. Step-based workflows enforce execution structure.

**Goal:** Combine these systems into a cohesive autonomous loop with robust termination controls accessible via HTTP, MCP, WebSocket, CLI, and slash commands.

### Phase 10: Core Design Principles

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

### Phase 10: Data Model

```sql
-- Stop signal registry (in-memory or SQLite for persistence across restarts)
CREATE TABLE loop_stop_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT,                          -- NULL = global stop
    reason TEXT NOT NULL,                     -- user_requested, http_endpoint, mcp_tool, websocket, no_tasks, stuck, error
    requested_at TEXT NOT NULL,
    handled_at TEXT,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_stop_signals_session ON loop_stop_signals(session_id);
CREATE INDEX idx_stop_signals_pending ON loop_stop_signals(handled_at) WHERE handled_at IS NULL;

-- Progress tracking for stuck detection
CREATE TABLE loop_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    started_at TEXT NOT NULL,
    last_progress_at TEXT NOT NULL,
    commits_count INTEGER DEFAULT 0,
    files_modified_count INTEGER DEFAULT 0,
    validation_attempts INTEGER DEFAULT 0,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

-- Task selection history for loop detection
CREATE TABLE task_selection_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    selected_at TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(id),
    FOREIGN KEY (task_id) REFERENCES tasks(id)
);

CREATE INDEX idx_selection_history_session ON task_selection_history(session_id);
```

### Stop Signal Registry

```python
# src/gobby/autonomous/stop_registry.py
from enum import Enum
from dataclasses import dataclass
from datetime import datetime
import threading

class StopReason(Enum):
    USER_REQUESTED = "user_requested"      # /stop or escape
    HTTP_ENDPOINT = "http_endpoint"        # POST /api/v1/loop/stop
    MCP_TOOL = "mcp_tool"                  # stop_autonomous_loop()
    WEBSOCKET = "websocket"                # {"type": "stop_loop"}
    NO_TASKS = "no_tasks"                  # Natural completion
    STUCK = "stuck"                        # Task failed repeatedly
    ERROR = "error"                        # Unrecoverable error

@dataclass
class StopSignal:
    session_id: str | None
    reason: StopReason
    requested_at: datetime
    handled_at: datetime | None = None

class StopRegistry:
    """Thread-safe stop signal management."""

    def __init__(self):
        self._stops: dict[str, StopSignal] = {}
        self._global_stop: StopSignal | None = None
        self._lock = threading.Lock()

    def request_stop(
        self,
        reason: StopReason,
        session_id: str | None = None,
    ) -> StopSignal:
        """Request stop for a session or globally."""
        signal = StopSignal(
            session_id=session_id,
            reason=reason,
            requested_at=datetime.now(),
        )
        with self._lock:
            if session_id:
                self._stops[session_id] = signal
            else:
                self._global_stop = signal
        return signal

    def should_stop(self, session_id: str) -> StopSignal | None:
        """Check if session should stop."""
        with self._lock:
            # Global stop takes precedence
            if self._global_stop and self._global_stop.handled_at is None:
                return self._global_stop
            return self._stops.get(session_id)

    def mark_handled(self, session_id: str | None = None) -> None:
        """Mark stop signal as handled."""
        with self._lock:
            if session_id and session_id in self._stops:
                self._stops[session_id].handled_at = datetime.now()
            elif self._global_stop:
                self._global_stop.handled_at = datetime.now()

    def clear(self, session_id: str | None = None) -> None:
        """Clear stop signal after handling."""
        with self._lock:
            if session_id:
                self._stops.pop(session_id, None)
            else:
                self._global_stop = None
```

### Progress Tracker

```python
# src/gobby/autonomous/progress_tracker.py
from dataclasses import dataclass, field
from datetime import datetime

@dataclass
class ProgressTracker:
    """Track progress metrics for stuck detection."""

    session_id: str
    task_id: str
    started_at: datetime = field(default_factory=datetime.now)
    last_progress_at: datetime = field(default_factory=datetime.now)
    commits: list[str] = field(default_factory=list)
    files_modified: set[str] = field(default_factory=set)
    validation_attempts: int = 0

    def record_commit(self, sha: str) -> None:
        self.commits.append(sha)
        self.last_progress_at = datetime.now()

    def record_file_change(self, path: str) -> None:
        self.files_modified.add(path)
        self.last_progress_at = datetime.now()

    def record_validation_attempt(self) -> None:
        self.validation_attempts += 1

    def is_stagnant(self, threshold_minutes: int = 30) -> bool:
        """Check if no progress for threshold time."""
        elapsed = datetime.now() - self.last_progress_at
        return elapsed.total_seconds() > threshold_minutes * 60

    def progress_summary(self) -> dict:
        return {
            "duration_minutes": (datetime.now() - self.started_at).total_seconds() / 60,
            "commits": len(self.commits),
            "files_modified": len(self.files_modified),
            "validation_attempts": self.validation_attempts,
            "minutes_since_progress": (datetime.now() - self.last_progress_at).total_seconds() / 60,
        }
```

### Stuck Detection

Three layers of stuck detection:

**Layer 1: Validation Failure Count** (existing in task system)
- `validation_fail_count` increments on each failed validation
- After 3 failures, creates fix subtask or marks stuck

**Layer 2: Task Selection Loop Detection**
- Track which tasks are selected via `task_selection_history`
- If same task selected 3+ times without completion, trigger stuck state

**Layer 3: Stagnation Detection**
- Track commits and file changes via `ProgressTracker`
- If no progress for configurable threshold (default 30 min), trigger stuck state

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

### HTTP Endpoints

```python
# POST /api/v1/loop/start
@app.post("/api/v1/loop/start")
async def start_loop(
    from_spec: str | None = None,
    prompt: str | None = None,
    session_id: str | None = None,
) -> dict:
    """Start autonomous loop (creates new session if not provided)."""

# POST /api/v1/loop/stop
@app.post("/api/v1/loop/stop")
async def stop_loop(
    session_id: str | None = None,
    force: bool = False,
) -> dict:
    """Stop autonomous loop."""

# GET /api/v1/loop/status
@app.get("/api/v1/loop/status")
async def loop_status(session_id: str | None = None) -> dict:
    """Get loop status."""

# POST /api/v1/loop/pause
@app.post("/api/v1/loop/pause")
async def pause_loop(session_id: str) -> dict:
    """Pause loop."""

# POST /api/v1/loop/resume
@app.post("/api/v1/loop/resume")
async def resume_loop(session_id: str) -> dict:
    """Resume loop."""

# POST /api/v1/loop/skip
@app.post("/api/v1/loop/skip")
async def skip_task(session_id: str, reason: str = "user_requested") -> dict:
    """Skip current task."""
```

### WebSocket Messages

```python
# Incoming messages (client → daemon)
{"type": "loop_start", "prompt": "...", "from_spec": "..."}
{"type": "loop_stop", "session_id": "...", "force": false}
{"type": "loop_pause", "session_id": "..."}
{"type": "loop_resume", "session_id": "..."}
{"type": "loop_skip", "session_id": "...", "reason": "..."}

# Outgoing messages (daemon → client)
{"type": "loop_started", "session_id": "...", "task_count": 5}
{"type": "loop_stopped", "session_id": "...", "reason": "..."}
{"type": "loop_progress", "session_id": "...", "step": "execute", "task_id": "..."}
{"type": "loop_task_completed", "session_id": "...", "task_id": "...", "remaining": 4}
{"type": "loop_stuck", "session_id": "...", "task_id": "...", "reason": "..."}
{"type": "loop_complete", "session_id": "...", "tasks_completed": 5}
```

### Phase 10: CLI Commands

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

### Slash Commands

```
/loop start              # Start autonomous mode in current session
/loop start --prompt "..." # Start with initial task
/loop stop               # Stop autonomous mode
/loop status             # Show current loop state
/loop skip               # Skip current task, try another
/loop pause              # Pause loop, take manual control
/loop resume             # Resume paused loop
```

### Workflow: autonomous-execution.yaml

```yaml
name: autonomous-execution
type: stepped
description: |
  Autonomous work loop that processes tasks until exhausted or stopped.
  Uses task system as persistent state, survives session boundaries.

variables:
  autonomous_mode: true
  max_validation_retries: 3
  require_plan_approval: false
  stagnation_threshold_minutes: 30

steps:
  - name: select_task
    description: "Select next task from queue"
    allowed_tools: [mcp__gobby__*]

    on_enter:
      - action: check_stop_signal

      - action: call_mcp_tool
        server_name: gobby-tasks
        tool_name: suggest_next_task
        arguments:
          prefer_subtasks: true
        as: task_suggestion

      - action: detect_task_loop
        as: loop_detection

      - action: inject_context
        when: "task_suggestion.suggestion is not None"
        content: |
          ## Autonomous Mode: Task Selected

          **{{ task_suggestion.suggestion.title }}** (`{{ task_suggestion.suggestion.id }}`)

          Priority: {{ task_suggestion.suggestion.priority }}
          Type: {{ task_suggestion.suggestion.task_type }}

          **Why this task?** {{ task_suggestion.reason }}

          {% if task_suggestion.suggestion.description %}
          ### Description
          {{ task_suggestion.suggestion.description }}
          {% endif %}

          {% if task_suggestion.suggestion.validation_criteria %}
          ### Acceptance Criteria
          {{ task_suggestion.suggestion.validation_criteria }}
          {% endif %}

      - action: call_mcp_tool
        when: "task_suggestion.suggestion is not None"
        server_name: gobby-tasks
        tool_name: update_task
        arguments:
          task_id: "{{ task_suggestion.suggestion.id }}"
          status: "in_progress"

      - action: set_variable
        name: current_task
        value: "{{ task_suggestion.suggestion }}"

    transitions:
      - to: complete
        when: "task_suggestion.suggestion is None"
        message: "No more tasks in queue. Autonomous loop complete."

      - to: stuck
        when: "loop_detection.is_stuck == true"

      - to: plan
        when: "variables.require_plan_approval == true"

      - to: execute
        when: "task_suggestion.suggestion is not None"

  - name: plan
    description: "Plan execution approach (optional)"
    allowed_tools: [Read, Glob, Grep, WebSearch, WebFetch, Task]
    blocked_tools: [Edit, Write, Bash, NotebookEdit]

    on_enter:
      - action: memory_recall_relevant
        query: "{{ current_task.title }}"
        limit: 5
        as: relevant_memories

      - action: match_skills
        prompt: "{{ current_task.title }} {{ current_task.description }}"
        as: matched_skills

      - action: inject_context
        content: |
          ## Planning Phase

          Review the task and form an execution plan.

          {% if relevant_memories %}
          ### Relevant Memories
          {% for mem in relevant_memories %}
          - {{ mem.content }}
          {% endfor %}
          {% endif %}

          {% if matched_skills %}
          ### Applicable Skills
          {% for skill in matched_skills %}
          - **{{ skill.name }}**: {{ skill.trigger_pattern }}
          {% endfor %}
          {% endif %}

          When ready, say "ready to execute" to proceed.

    exit_conditions:
      - type: user_approval
        prompt: "Plan looks good. Ready to execute?"

    transitions:
      - to: execute
        when: "user_says('ready') or user_says('execute') or user_says('proceed')"

  - name: execute
    description: "Execute task implementation"
    allowed_tools: all

    on_enter:
      - action: check_stop_signal

      - action: start_progress_tracking
        task_id: "{{ current_task.id }}"

      - action: inject_context
        content: |
          ## Execution Phase

          Working on: **{{ current_task.title }}**

          When complete, say "validate" to run validation.
          Say "stuck" if you encounter blockers.

    on_exit:
      - action: stop_progress_tracking

    transitions:
      - to: validate
        when: "user_says('validate') or user_says('done') or user_says('complete')"

      - to: stuck
        when: "user_says('stuck') or user_says('blocked')"

  - name: validate
    description: "Validate task completion"
    allowed_tools: [Read, Glob, Grep, Bash, mcp__gobby__*]
    blocked_tools: [Edit, Write]

    on_enter:
      - action: check_stop_signal

      - action: call_mcp_tool
        server_name: gobby-tasks
        tool_name: validate_task
        arguments:
          task_id: "{{ current_task.id }}"
        as: validation_result

      - action: inject_context
        content: |
          ## Validation Result

          **Status**: {{ validation_result.status }}

          {% if validation_result.feedback %}
          **Feedback**: {{ validation_result.feedback }}
          {% endif %}

          {% if validation_result.status == 'invalid' %}
          Returning to execution phase to address feedback.
          {% elif validation_result.status == 'valid' %}
          Task validated! Proceeding to close.
          {% endif %}

    transitions:
      - to: close_task
        when: "validation_result.status == 'valid'"

      - to: execute
        when: "validation_result.status == 'invalid' and current_task.validation_fail_count < variables.max_validation_retries"

      - to: stuck
        when: "validation_result.status == 'invalid' and current_task.validation_fail_count >= variables.max_validation_retries"

  - name: close_task
    description: "Close completed task"
    allowed_tools: [mcp__gobby__*]

    on_enter:
      - action: call_mcp_tool
        server_name: gobby-tasks
        tool_name: close_task
        arguments:
          task_id: "{{ current_task.id }}"
          session_id: "{{ session.id }}"
          skip_validation: true
        as: close_result

      - action: memory_extract
        content: |
          Completed task: {{ current_task.title }}
          Approach: {{ close_result.changes_summary or 'Not recorded' }}

      - action: inject_context
        content: |
          ## Task Closed

          **{{ current_task.title }}** completed successfully.

          {% if close_result.commit_sha %}
          Commit: `{{ close_result.commit_sha }}`
          {% endif %}

          Selecting next task...

    transitions:
      - to: select_task
        when: "always()"

  - name: stuck
    description: "Handle stuck state"
    allowed_tools: [Read, Glob, Grep, mcp__gobby__*]

    on_enter:
      - action: call_mcp_tool
        server_name: gobby-tasks
        tool_name: update_task
        arguments:
          task_id: "{{ current_task.id }}"
          status: "blocked"

      - action: remember
        content: |
          Task "{{ current_task.title }}" got stuck.
          Validation attempts: {{ current_task.validation_fail_count }}
        memory_type: pattern
        importance: 0.8
        tags: ["stuck", "autonomous"]

      - action: inject_context
        content: |
          ## Stuck on Task

          Task `{{ current_task.id }}` has been marked as blocked.

          Options:
          1. **"try different"** - Skip and select another task
          2. **"escalate"** - Pause loop and wait for user guidance
          3. **"force close"** - Close task anyway (skip validation)

          What would you like to do?

    transitions:
      - to: select_task
        when: "user_says('try different') or user_says('skip')"

      - to: paused
        when: "user_says('escalate') or user_says('pause')"

      - to: close_task
        when: "user_says('force close')"

  - name: paused
    description: "Loop paused, awaiting user input"
    allowed_tools: all

    on_enter:
      - action: inject_context
        content: |
          ## Autonomous Loop Paused

          The loop has been paused. You have full control.

          Say **"resume"** to continue autonomous operation.
          Say **"stop"** to end the loop.

    transitions:
      - to: select_task
        when: "user_says('resume') or user_says('continue')"

      - to: complete
        when: "user_says('stop') or user_says('end')"

  - name: complete
    description: "Loop completed"
    allowed_tools: all

    on_enter:
      - action: call_mcp_tool
        server_name: gobby-tasks
        tool_name: list_tasks
        arguments:
          status: "closed"
          limit: 100
        as: completed_tasks

      - action: inject_context
        content: |
          ## Autonomous Loop Complete

          **Tasks Completed This Session**: {{ completed_tasks | length }}

          {% for task in completed_tasks[:10] %}
          - {{ task.title }}
          {% endfor %}

          {% if completed_tasks | length > 10 %}
          ... and {{ completed_tasks | length - 10 }} more
          {% endif %}

          Loop has ended. Normal interactive mode resumed.

triggers:
  on_session_start:
    - action: set_variable
      name: autonomous_mode
      value: true
      when: "session.data.get('autonomous') == true"
```

### Workflow: autonomous-lifecycle.yaml

```yaml
name: autonomous-lifecycle
type: lifecycle
priority: 100

triggers:
  on_session_start:
    - action: set_workflow
      workflow: autonomous-execution
      when: "session.data.get('autonomous') == true"

    - action: inject_context
      when: "session.data.get('autonomous') == true"
      content: |
        ## Autonomous Work Mode Active

        This session will automatically work through the task queue until:
        - All tasks are complete
        - A stop signal is received
        - The loop gets stuck

        **Stop Commands**: `/loop stop`, escape key, or say "stop loop"

        Beginning task selection...

  on_session_end:
    - action: call_mcp_tool
      server_name: gobby-tasks
      tool_name: list_ready_tasks
      arguments:
        limit: 1
      as: remaining_tasks
      when: "event.data.get('autonomous') == true and event.data.get('reason') != 'user_abort'"

    - action: check_stop_signal
      as: stop_check

    - action: start_new_session
      when: >
        remaining_tasks and
        len(remaining_tasks) > 0 and
        stop_check.decision != 'block'
      prompt: |
        AUTONOMOUS WORK SESSION (Continued)

        {{ handoff.compact_markdown or handoff.summary_markdown }}

        Remaining tasks: {{ len(remaining_tasks) }}

        Continuing autonomous work loop...
      session_data:
        autonomous: true
        parent_session_id: "{{ session.id }}"

  on_before_agent:
    - action: check_stop_signal
      when: "workflow.autonomous_mode == true"

  on_after_tool:
    - action: track_progress
      tool_pattern: "git commit|Edit|Write"
      when: "workflow.autonomous_mode == true"
```

### Phase 10: Configuration

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

### Memory Integration

Autonomous loop learns from failures and successes:

```yaml
# In autonomous-lifecycle.yaml
on_session_start:
  - action: memory_recall
    query: "stuck blocked failed autonomous"
    memory_type: pattern
    limit: 5
    as: failure_patterns
    when: "session.data.get('autonomous') == true"

  - action: inject_context
    when: "failure_patterns"
    content: |
      ### Past Failure Patterns (Avoid These)
      {% for pattern in failure_patterns %}
      - {{ pattern.content }}
      {% endfor %}

on_task_closed:
  - action: call_mcp_tool
    server_name: gobby-skills
    tool_name: learn_skill_from_session
    arguments:
      session_id: "{{ session.id }}"
      filter_to_task: "{{ current_task.id }}"
    when: "current_task.validation_fail_count == 0"
```

### Phase 10: Implementation Checklist

#### Phase 10.1: Stop Signal Infrastructure

- [ ] Create `src/gobby/autonomous/stop_registry.py` with `StopRegistry` class
- [ ] Add database migration for `loop_stop_signals` table
- [ ] Implement thread-safe stop signal management
- [ ] Add stop signal checking to workflow engine

#### Phase 10.2: Progress Tracking

- [ ] Create `src/gobby/autonomous/progress_tracker.py` with `ProgressTracker` class
- [ ] Add database migration for `loop_progress` table
- [ ] Implement progress recording from tool results
- [ ] Add stagnation detection algorithm

#### Phase 10.3: Stuck Detection

- [ ] Add database migration for `task_selection_history` table
- [ ] Implement task selection loop detection
- [ ] Create `check_stop_signal` workflow action
- [ ] Create `detect_task_loop` workflow action
- [ ] Create `start_progress_tracking` / `stop_progress_tracking` actions

#### Phase 10.4: MCP Tools

- [ ] Create `src/gobby/mcp_proxy/tools/loop.py` with `LoopToolRegistry`
- [ ] Register as `gobby-loop` internal server
- [ ] Implement `start_autonomous_loop`, `stop_autonomous_loop`, `get_loop_status`
- [ ] Implement `pause_loop`, `resume_loop`, `skip_current_task`

#### Phase 10.5: HTTP Endpoints

- [ ] Add `/api/v1/loop/*` endpoints to `src/gobby/servers/http.py`
- [ ] Implement start, stop, pause, resume, skip, status endpoints
- [ ] Add authentication/authorization for loop control

#### Phase 10.6: WebSocket Integration

- [ ] Add loop control message handlers to WebSocket server
- [ ] Implement loop progress event emission
- [ ] Add real-time status streaming

#### Phase 10.7: CLI Commands

- [ ] Add `gobby loop` command group to CLI
- [ ] Implement start, stop, pause, resume, skip, status, watch commands
- [ ] Add progress output formatting

#### Phase 10.8: Slash Commands

- [ ] Create `/loop` skill with subcommands
- [ ] Register slash command handlers
- [ ] Integrate with session context

#### Phase 10.9: Workflow Files

- [ ] Create `autonomous-execution.yaml` step-based workflow
- [ ] Create `autonomous-lifecycle.yaml` lifecycle workflow
- [ ] Install to `~/.gobby/workflows/` on daemon start

#### Phase 10.10: Integration Testing

- [ ] Test natural completion (no more tasks)
- [ ] Test all stop signal sources (HTTP, MCP, WS, CLI, /slash)
- [ ] Test stuck detection (validation fails, selection loop, stagnation)
- [ ] Test session chaining on context limit
- [ ] Test pause/resume flow
- [ ] Test skip task flow
- [ ] Test memory/skill integration

---

## Decisions

| # | Question | Decision | Rationale |
| :--- | :--- | :--- | :--- |
| 1 | **Worktree storage** | SQLite table + filesystem | Track metadata in DB, actual worktrees on disk |
| 2 | **Agent spawning** | Terminal-based (Ghostty/iTerm) | Claude Code runs in terminal, leverage existing patterns |
| 3 | **Merge conflict context** | Configurable line window | Balance token efficiency vs context quality |
| 4 | **QA loop limit** | 3 retries default | Prevent infinite loops while allowing recovery |
| 5 | **GitHub auth** | Environment variable | Standard pattern, works with gh CLI |
| 6 | **Linear auth** | API key | Linear's standard auth method |
| 7 | **Pipeline phases** | Fixed 5-phase model | Clear structure, matches Auto-Claude pattern |
| 8 | **External validator** | Separate agent context | Avoids bias from implementation agent |
| 9 | **Loop state persistence** | Tasks (not workflow variables) | Workflow vars reset on session end; tasks survive |
| 10 | **Stop signal registry** | Thread-safe in-memory + SQLite | Fast checks, persistence across daemon restarts |
| 11 | **Stuck detection layers** | 3 layers (validation, selection, stagnation) | Comprehensive coverage of stuck scenarios |
| 12 | **Session chaining trigger** | on_session_end lifecycle hook | Natural hook point, runs after handoff extraction |
| 13 | **Autonomous mode activation** | session.data.autonomous flag | Clean separation, explicit opt-in per session |

---

## Priority Assessment

| Feature | Value | Effort | Priority | Inspiration |
| :--- | :--- | :--- | :--- | :--- |
| Worktree Coordination | High | Medium | P1 | Auto-Claude |
| Merge Resolution | High | High | P1 | Auto-Claude |
| QA Loop Enhancement | Medium | Low | P2 | Auto-Claude |
| GitHub Integration | High | Medium | P2 | Auto-Claude |
| Linear Integration | Medium | Medium | P3 | Auto-Claude |
| Pipeline Workflows | Medium | High | P3 | Auto-Claude |
| **Artifact Index** | **High** | **Medium** | **P1** | Continuous-Claude v2 |
| **Enhanced Skill Routing** | **High** | **Medium** | **P2** | SkillForge |
| **Semantic Memory Search** | **Medium** | **Medium** | **P2** | KnowNote |
| **Autonomous Work Loop** | **High** | **High** | **P1** | Original Design |

**Recommendations:**

1. **Immediate wins** - Artifact Index (Phase 7) provides high value with moderate effort and enables better session continuity
2. **Parallel development** - Worktree Coordination (Phase 1) + Merge Resolution (Phase 2) for multi-agent workflows
3. **Intelligence layer** - Skill Routing (Phase 8) + Semantic Memory (Phase 9) make Gobby smarter over time
4. **External integrations** - GitHub/Linear after core intelligence is solid
5. **Autonomous execution** - Autonomous Work Loop (Phase 10) enables hands-off task execution; depends on existing task system + workflows being stable

**Phase 10 Dependencies:**
- Requires stable task system (gobby-tasks) - ✅ Exists
- Requires stable workflow engine - ✅ Exists
- Requires session handoff - ✅ Exists
- Benefits from Artifact Index (Phase 7) for better handoff context
- Benefits from Enhanced Skill Routing (Phase 8) for smarter task execution
- Benefits from QA Loop Enhancement (Phase 3) for better validation
