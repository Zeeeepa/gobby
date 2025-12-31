# Task System V2: Commit Linking & Enhanced Validation

## Overview

This document outlines enhancements to gobby's task system focusing on two major areas:

1. **Commit Linking** - Associate git commits with tasks for traceability and improved validation
2. **Enhanced QA Validation** - Robust validation loop with recurring issue detection, escalation, and multi-agent support

These features address edge cases in the current validation system (e.g., validating already-committed work) and incorporate patterns from [Auto-Claude](https://github.com/AndyMik90/Auto-Claude) for production-grade QA loops.

## Motivation

### Current Limitations

1. **Validation only checks uncommitted changes** - If work was committed in a previous sprint, `get_git_diff()` returns nothing and validation fails
2. **No traceability** - Can't see which commits implement which task
3. **Simple pass/fail** - No detection of recurring issues or escalation path
4. **Single-agent validation** - Same context validates its own work
5. **Flat feedback** - Free-text feedback, not structured issues

### Goals

- Link commits to tasks for audit trail and validation context
- Detect recurring validation failures and escalate appropriately
- Support external validator agent for objectivity
- Track full validation history per task
- Run build/test checks before LLM validation

## Data Model Changes

### Tasks Table Additions

```sql
-- Add to tasks table
ALTER TABLE tasks ADD COLUMN commits TEXT;              -- JSON array of commit SHAs
ALTER TABLE tasks ADD COLUMN validation_history TEXT;   -- JSON array of validation attempts
ALTER TABLE tasks ADD COLUMN escalated_at TEXT;         -- Timestamp when escalated to human
ALTER TABLE tasks ADD COLUMN escalation_reason TEXT;    -- Why it was escalated
```

### New Validation History Table

```sql
CREATE TABLE task_validation_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    task_id TEXT NOT NULL,
    iteration INTEGER NOT NULL,           -- 1, 2, 3...
    status TEXT NOT NULL,                 -- valid, invalid, error, pending
    feedback TEXT,                        -- LLM feedback text
    issues TEXT,                          -- JSON array of structured issues
    context_type TEXT,                    -- git_diff, commit_range, manual
    context_summary TEXT,                 -- What was validated against
    validator_type TEXT,                  -- internal, external_agent
    created_at TEXT NOT NULL,
    FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
);

CREATE INDEX idx_validation_history_task ON task_validation_history(task_id);
```

### Structured Issue Format

```json
{
  "type": "test_failure|lint_error|acceptance_gap|type_error|security",
  "severity": "blocker|major|minor",
  "title": "Brief description",
  "location": "path/to/file:line",
  "details": "Full explanation",
  "suggested_fix": "How to resolve",
  "recurring_count": 0
}
```

## Commit Linking

### Concept

Track which git commits are associated with each task. This enables:

1. **Validation against committed code** - Check `git diff <commits>` instead of just uncommitted changes
2. **Traceability** - Audit trail of what was done for each task
3. **Duplicate detection** - Know if work exists even after merge

### MCP Tools

```python
@mcp.tool()
def link_commit(
    task_id: str,
    commit_sha: str,
    auto_detected: bool = False,
) -> dict:
    """
    Link a git commit to a task.

    Args:
        task_id: Task to link to
        commit_sha: Full or short SHA of the commit
        auto_detected: Whether this was auto-linked (vs manual)

    Returns:
        Updated task with commits list
    """

@mcp.tool()
def unlink_commit(task_id: str, commit_sha: str) -> dict:
    """Remove a commit link from a task."""

@mcp.tool()
def auto_link_commits(
    task_id: str,
    since: str | None = None,  # Commit SHA or "1 day ago"
) -> dict:
    """
    Auto-detect and link commits mentioning this task ID.

    Searches commit messages for patterns like:
    - [gt-abc123]
    - gt-abc123:
    - Implements gt-abc123

    Args:
        task_id: Task to find commits for
        since: Only search commits after this point

    Returns:
        List of newly linked commits
    """

@mcp.tool()
def get_task_diff(
    task_id: str,
    include_uncommitted: bool = True,
) -> dict:
    """
    Get combined diff for all commits linked to a task.

    Used by validation to check actual implementation.

    Args:
        task_id: Task to get diff for
        include_uncommitted: Also include staged/unstaged changes

    Returns:
        Combined diff string and commit list
    """
```

### CLI Commands

```bash
# Link commits
gobby tasks commit link TASK_ID COMMIT_SHA
gobby tasks commit unlink TASK_ID COMMIT_SHA
gobby tasks commit auto TASK_ID [--since COMMIT]

# View linked commits
gobby tasks show TASK_ID --commits
gobby tasks commit list TASK_ID

# Get task diff
gobby tasks diff TASK_ID [--no-uncommitted]
```

### Auto-Linking via Hooks

On session end, scan new commits for task ID mentions:

```python
# In session_end hook
async def auto_link_session_commits(session_id: str):
    """Find commits made this session and link to mentioned tasks."""
    # Get commits since session start
    session = session_manager.get(session_id)
    commits = get_commits_since(session.started_at)

    for commit in commits:
        # Parse task IDs from message
        task_ids = extract_task_ids(commit.message)
        for task_id in task_ids:
            link_commit(task_id, commit.sha, auto_detected=True)
```

### Validation Integration

Update `close_task` to use commit-based diff:

```python
async def close_task(task_id: str, ...):
    # ...existing code...

    # Try commit-based diff first
    if task.commits:
        validation_context = get_task_diff(task_id)
    elif not validation_context:
        # Fall back to uncommitted changes
        git_diff = get_git_diff()
        if git_diff:
            validation_context = f"Git diff:\n\n{git_diff}"
```

## Enhanced QA Validation Loop

Inspired by Auto-Claude's multi-agent QA system.

### Configuration

```yaml
# config.yaml
task_validation:
  enabled: true
  provider: "claude"
  model: "claude-sonnet-4-20250514"

  # Iteration limits
  max_iterations: 10                    # Max validation attempts per task
  max_consecutive_errors: 3             # Escalate after this many agent errors

  # Recurring issue detection
  recurring_issue_threshold: 3          # Same issue appears N times → escalate
  issue_similarity_threshold: 0.8       # Fuzzy match for "same" issue

  # Build verification
  run_build_first: true                 # Run build/tests before LLM validation
  build_command: "npm test"             # Or auto-detect from project

  # External validator
  use_external_validator: false         # Use separate agent for objectivity
  external_validator_model: "claude-sonnet-4-20250514"

  # Escalation
  escalation_enabled: true
  escalation_notify: "webhook"          # webhook, slack, email, none
  escalation_webhook_url: null

  # Prompts
  prompt: |
    Validate if the following changes satisfy the requirements...

  issue_extraction_prompt: |
    Extract structured issues from the validation feedback...
```

### Validation States

```
pending → in_progress → valid | invalid | error
                           ↓
                      [if recurring or max iterations]
                           ↓
                       escalated
```

### Core Loop Implementation

```python
class EnhancedTaskValidator:
    """
    Robust validation loop with recurring issue detection and escalation.
    """

    async def validate_with_retry(
        self,
        task: Task,
        max_iterations: int = 10,
    ) -> ValidationResult:
        """
        Run validation loop until approved or escalation triggered.
        """
        iteration = 0
        consecutive_errors = 0

        while iteration < max_iterations:
            iteration += 1

            # Phase 1: Build verification (if enabled)
            if self.config.run_build_first:
                build_result = await self.run_build_check(task)
                if not build_result.success:
                    await self.record_iteration(task, iteration, "invalid",
                        issues=[build_result.to_issue()])
                    continue  # Let fixer address build issues

            # Phase 2: Run validation
            result = await self.run_validation(task, iteration)

            # Phase 3: Record iteration
            await self.record_iteration(task, iteration, result)

            # Phase 4: Check termination conditions
            if result.status == "valid":
                return result

            if result.status == "error":
                consecutive_errors += 1
                if consecutive_errors >= self.config.max_consecutive_errors:
                    return await self.escalate(task, "consecutive_errors")
            else:
                consecutive_errors = 0

            # Phase 5: Check for recurring issues
            if await self.has_recurring_issues(task):
                return await self.escalate(task, "recurring_issues")

        # Max iterations exceeded
        return await self.escalate(task, "max_iterations")

    async def has_recurring_issues(self, task: Task) -> bool:
        """Check if same issues keep appearing."""
        history = await self.get_iteration_history(task.id)
        if len(history) < self.config.recurring_issue_threshold:
            return False

        # Extract all issues from history
        all_issues = []
        for iteration in history:
            all_issues.extend(iteration.issues or [])

        # Group similar issues
        issue_groups = self.group_similar_issues(all_issues)

        # Check if any group exceeds threshold
        for group in issue_groups:
            if len(group) >= self.config.recurring_issue_threshold:
                return True

        return False

    def group_similar_issues(
        self,
        issues: list[Issue],
    ) -> list[list[Issue]]:
        """Group issues by similarity (title + location)."""
        groups = []
        for issue in issues:
            matched = False
            for group in groups:
                if self.issues_similar(issue, group[0]):
                    group.append(issue)
                    matched = True
                    break
            if not matched:
                groups.append([issue])
        return groups

    def issues_similar(self, a: Issue, b: Issue) -> bool:
        """Check if two issues are similar enough to be the same."""
        # Same location is strong signal
        if a.location and b.location and a.location == b.location:
            return True

        # Fuzzy title match
        from difflib import SequenceMatcher
        ratio = SequenceMatcher(None, a.title, b.title).ratio()
        return ratio >= self.config.issue_similarity_threshold

    async def escalate(
        self,
        task: Task,
        reason: str,
    ) -> ValidationResult:
        """Escalate to human when automated resolution fails."""
        # Update task
        task_manager.update_task(
            task.id,
            status="escalated",
            escalated_at=datetime.now(UTC),
            escalation_reason=reason,
        )

        # Send notification
        if self.config.escalation_notify == "webhook":
            await self.send_webhook_notification(task, reason)

        # Generate summary for human
        summary = await self.generate_escalation_summary(task)

        return ValidationResult(
            status="escalated",
            feedback=summary,
            escalation_reason=reason,
        )
```

### External Validator Agent

For objectivity, use a separate agent that didn't write the code:

```python
async def run_external_validation(
    self,
    task: Task,
    changes_context: str,
) -> ValidationResult:
    """
    Spawn a fresh agent to validate - no prior context.

    This prevents the "validate your own work" problem.
    """
    prompt = f"""
    You are a QA validator reviewing code changes.

    ## Task
    Title: {task.title}
    Acceptance Criteria: {task.validation_criteria}

    ## Changes to Validate
    {changes_context}

    ## Instructions
    1. Review each change against the acceptance criteria
    2. Run any relevant tests or checks
    3. Output your assessment as JSON:

    {{
      "status": "valid" | "invalid",
      "summary": "Brief assessment",
      "issues": [
        {{
          "type": "acceptance_gap|test_failure|code_quality",
          "severity": "blocker|major|minor",
          "title": "...",
          "location": "file:line",
          "details": "...",
          "suggested_fix": "..."
        }}
      ]
    }}
    """

    # Use external validator model (may be different from main)
    provider = self.llm_service.get_provider(self.config.provider)
    response = await provider.generate_text(
        prompt=prompt,
        system_prompt="You are an objective QA validator.",
        model=self.config.external_validator_model,
    )

    return self.parse_validation_response(response)
```

### Build Verification

Run build/tests before LLM validation:

```python
async def run_build_check(self, task: Task) -> BuildResult:
    """
    Run build/test command before LLM validation.

    Prevents wasting LLM calls on obviously broken code.
    """
    # Auto-detect build command if not configured
    command = self.config.build_command
    if not command:
        command = await self.detect_build_command()

    if not command:
        return BuildResult(success=True, skipped=True)

    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,  # 5 min timeout
            cwd=self.project_path,
        )

        return BuildResult(
            success=result.returncode == 0,
            stdout=result.stdout,
            stderr=result.stderr,
            command=command,
        )
    except subprocess.TimeoutExpired:
        return BuildResult(
            success=False,
            error="Build timed out after 5 minutes",
        )
    except Exception as e:
        return BuildResult(
            success=False,
            error=str(e),
        )

async def detect_build_command(self) -> str | None:
    """Auto-detect build/test command from project."""
    project_path = Path(self.project_path)

    # Check for common patterns
    if (project_path / "package.json").exists():
        return "npm test"
    if (project_path / "pyproject.toml").exists():
        return "uv run pytest"
    if (project_path / "Cargo.toml").exists():
        return "cargo test"
    if (project_path / "go.mod").exists():
        return "go test ./..."

    return None
```

### MCP Tools

```python
@mcp.tool()
async def validate_task(
    task_id: str,
    max_iterations: int = 1,
    use_external_validator: bool | None = None,
    run_build_first: bool | None = None,
) -> dict:
    """
    Validate task completion with enhanced QA loop.

    Args:
        task_id: Task to validate
        max_iterations: Max validation attempts (default: 1 for manual, 10 for close_task)
        use_external_validator: Override config setting
        run_build_first: Override config setting

    Returns:
        Validation result with status, issues, and history
    """

@mcp.tool()
def get_validation_history(task_id: str) -> dict:
    """
    Get full validation history for a task.

    Returns all iterations with issues, feedback, and context.
    """

@mcp.tool()
def get_recurring_issues(task_id: str) -> dict:
    """
    Analyze validation history for recurring issues.

    Returns grouped issues that appear multiple times.
    """

@mcp.tool()
def clear_validation_history(task_id: str) -> dict:
    """
    Clear validation history for fresh start.

    Use after major changes that invalidate previous feedback.
    """

@mcp.tool()
def de_escalate_task(task_id: str, reason: str) -> dict:
    """
    Return an escalated task to open status.

    Use after human intervention resolves the issue.
    """
```

### CLI Commands

```bash
# Validation
gobby tasks validate TASK_ID [--max-iterations N] [--external] [--skip-build]
gobby tasks validate TASK_ID --history          # Show validation history
gobby tasks validate TASK_ID --recurring        # Show recurring issues

# Escalation
gobby tasks list --status escalated             # List escalated tasks
gobby tasks de-escalate TASK_ID --reason "Fixed manually"

# History management
gobby tasks validation-history TASK_ID
gobby tasks validation-history TASK_ID --clear
```

## Implementation Checklist

### Phase 1: Commit Linking

- [ ] Add `commits` column to tasks table (migration)
- [ ] Create `src/tasks/commits.py` with commit linking logic
- [ ] Implement `link_commit()` function
- [ ] Implement `unlink_commit()` function
- [ ] Implement `auto_link_commits()` with message parsing
- [ ] Implement `get_task_diff()` for commit-range diffs
- [ ] Add MCP tools: `link_commit`, `unlink_commit`, `auto_link_commits`, `get_task_diff`
- [ ] Add CLI commands: `gobby tasks commit link/unlink/auto/list`
- [ ] Update `close_task` to use commit-based diff when available
- [ ] Add auto-linking to session_end hook
- [ ] Update JSONL sync to include commits
- [ ] Add unit tests for commit linking

### Phase 2: Validation History

- [ ] Create `task_validation_history` table (migration)
- [ ] Add `validation_history` column to tasks (JSON cache)
- [ ] Create `ValidationHistoryManager` class
- [ ] Implement `record_iteration()` method
- [ ] Implement `get_iteration_history()` method
- [ ] Add `get_validation_history` MCP tool
- [ ] Add `gobby tasks validation-history` CLI command
- [ ] Update `validate_task` to record all iterations
- [ ] Add unit tests for history tracking

### Phase 3: Structured Issues

- [ ] Define `Issue` dataclass with type, severity, location, etc.
- [ ] Update validation prompt to output structured issues
- [ ] Implement `parse_issues_from_response()` helper
- [ ] Add issue extraction prompt to config
- [ ] Update `ValidationResult` to include issues list
- [ ] Store issues in validation history
- [ ] Add tests for issue parsing

### Phase 4: Recurring Issue Detection

- [ ] Implement `group_similar_issues()` with fuzzy matching
- [ ] Implement `has_recurring_issues()` check
- [ ] Add `issue_similarity_threshold` config
- [ ] Add `recurring_issue_threshold` config
- [ ] Implement `get_recurring_issue_summary()`
- [ ] Add `get_recurring_issues` MCP tool
- [ ] Add `--recurring` flag to validation CLI
- [ ] Add tests for similarity matching

### Phase 5: Build Verification

- [ ] Add `run_build_first` config option
- [ ] Add `build_command` config option
- [ ] Implement `detect_build_command()` auto-detection
- [ ] Implement `run_build_check()` method
- [ ] Convert build failures to structured issues
- [ ] Add `--skip-build` flag to validate CLI
- [ ] Add tests for build verification

### Phase 6: Enhanced Validation Loop

- [ ] Create `EnhancedTaskValidator` class
- [ ] Implement `validate_with_retry()` main loop
- [ ] Add `max_iterations` config
- [ ] Add `max_consecutive_errors` config
- [ ] Track consecutive errors separately from rejections
- [ ] Pass error context to retry iterations
- [ ] Update `close_task` to use enhanced loop
- [ ] Add `--max-iterations` flag to CLI
- [ ] Add integration tests for retry loop

### Phase 7: External Validator

- [ ] Add `use_external_validator` config option
- [ ] Add `external_validator_model` config option
- [ ] Implement `run_external_validation()` method
- [ ] Create external validator prompt template
- [ ] Add `--external` flag to validate CLI
- [ ] Test external vs internal validator quality
- [ ] Document when to use external validator

### Phase 8: Escalation

- [ ] Add `escalated` as valid task status
- [ ] Add `escalated_at` column to tasks
- [ ] Add `escalation_reason` column to tasks
- [ ] Implement `escalate()` method
- [ ] Add `escalation_enabled` config
- [ ] Add `escalation_notify` config (webhook/slack/none)
- [ ] Implement webhook notification
- [ ] Implement `generate_escalation_summary()`
- [ ] Add `de_escalate_task` MCP tool
- [ ] Add `gobby tasks de-escalate` CLI command
- [ ] Add `gobby tasks list --status escalated`
- [ ] Add tests for escalation flow

### Phase 9: Documentation & Polish

- [ ] Update CLAUDE.md with new validation features
- [ ] Update docs/tasks.md with validation guide
- [ ] Add configuration examples
- [ ] Add troubleshooting guide for common issues
- [ ] Performance test with large validation histories
- [ ] Add metrics/logging for validation loops

## Decisions

| # | Question | Decision | Rationale |
|---|----------|----------|-----------|
| 1 | **Commit storage** | JSON array in tasks table | Simple, no join needed for common case |
| 2 | **Validation history** | Separate table + JSON cache | Full history in table, recent in task for quick access |
| 3 | **Issue similarity** | Title + location fuzzy match | Simple, catches most duplicates without ML |
| 4 | **Escalation status** | New status value | Clear state, queryable, distinct from `failed` |
| 5 | **Build check timing** | Before LLM validation | Fail fast, save LLM costs |
| 6 | **External validator** | Opt-in per task or global | Flexibility, not all tasks need objectivity |
| 7 | **Auto-link pattern** | `[gt-xxxxx]` or `gt-xxxxx:` | Common conventions, easy to type |
| 8 | **Iteration limit** | 10 default | Generous but bounded, prevents runaway |
| 9 | **Recurring threshold** | 3 occurrences | Balance between persistence and giving up |

## Future Enhancements

- **Semantic issue matching** - Use embeddings for better similarity detection
- **Fix suggestion ranking** - Prioritize fixes by likelihood of success
- **Validator learning** - Track which validation patterns succeed
- **Cross-task issue detection** - Find issues appearing across multiple tasks
- **Validation metrics dashboard** - Visualize pass rates, common issues
- **Integration with Linear/GitHub** - Sync escalations to external trackers
