# Orchestration v2: Clone-Based Parallel Agents

This document describes the addition of **Section 16: Clone-Based Parallel Agents** to `docs/plans/orchestration.md`.

The new section addresses the thread-safety issues discovered during E2E testing (documented in `docs/research/investigate-gtr-ccmanager.md`).

---

## Summary of Changes

**New Section 16** to be added after Section 15 (Configuration Reference) in orchestration.md.

**Design Decisions (Confirmed)**:
1. Default isolation mode: `clone` for parallel-orchestrator
2. Remote branch cleanup: Keep 7 days after merge, then auto-delete
3. MCP structure: New `gobby-clones` server (separate from gobby-worktrees)

---

## Section 16: Clone-Based Parallel Agents

### 16.1 Problem Statement

During E2E testing of parallel agent orchestration, fundamental issues emerged with git worktrees:

**Problem 1: Git is NOT Thread-Safe**

All worktrees share a single `.git` directory, leading to:
- Race conditions during concurrent operations (checkout, commit)
- Lock file contention (`index.lock`, `HEAD.lock`)
- Potential repository corruption with aggressive parallel agents

**Problem 2: CLI Worktree Detection**

Gemini CLI's `findProjectRoot()` searches for a `.git` **directory**. Worktrees have a `.git` **file** pointing back to main repo, causing agents to operate on wrong directory.

**Key Finding** (from `docs/research/investigate-gtr-ccmanager.md` line 33):
> "For truly parallel agent work, separate repository clones are safer than worktrees."

### 16.2 Architecture: Clones vs Worktrees

```
┌─────────────────────────────────────────────────────────────────┐
│                     PARALLEL ISOLATION MODES                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────────────┐    ┌─────────────────────────────┐   │
│   │   WORKTREES         │    │         CLONES              │   │
│   │   (Sequential)      │    │         (Parallel)          │   │
│   │                     │    │                             │   │
│   │ - Shared .git       │    │ - Isolated .git per clone   │   │
│   │ - Fast setup        │    │ - Thread-safe operations    │   │
│   │ - Lock contention   │    │ - Explicit sync required    │   │
│   │ - One agent at time │    │ - Multiple agents safe      │   │
│   └─────────────────────┘    └─────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### 16.3 When to Use Each

| Scenario | Recommendation | Reason |
|----------|----------------|--------|
| Sequential orchestrator | Worktree | Fast setup, single agent |
| Parallel orchestrator (2+ agents) | **Clone** | Thread safety |
| Short-lived tasks (<30 min) | Worktree | Minimal overhead |
| Long-running tasks | Either | Based on parallelism |
| CI/CD environments | Clone | Full isolation |
| Overnight batch processing | **Clone** | Multiple agents |

### 16.4 Clone Storage Layout

```
/tmp/gobby-clones/
  <project-name>/
    <task-id-or-branch>/           # Full shallow clone
      .git/                         # Isolated git directory
      .gobby/project.json           # Copy with parent_project_path
      ... project files ...
```

### 16.5 Database Schema

```sql
-- Add to migrations.py
CREATE TABLE clones (
    id TEXT PRIMARY KEY,                    -- clone-<uuid>
    project_id TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    clone_path TEXT NOT NULL,
    base_branch TEXT DEFAULT 'main',
    task_id TEXT,                           -- Optional linked task
    agent_session_id TEXT,                  -- Owning session
    status TEXT DEFAULT 'active',           -- active, synced, merged, abandoned
    remote_url TEXT NOT NULL,               -- Origin URL for sync
    last_sync_at TIMESTAMP,
    cleanup_after TIMESTAMP,                -- 7 days after merge
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (project_id) REFERENCES projects(id)
);

CREATE INDEX idx_clones_project ON clones(project_id);
CREATE INDEX idx_clones_task ON clones(task_id);
CREATE INDEX idx_clones_status ON clones(status);
CREATE INDEX idx_clones_cleanup ON clones(cleanup_after);
```

### 16.6 New MCP Server: gobby-clones

#### create_clone

```python
create_clone(
    branch_name: str,
    base_branch: str = "main",
    task_id: str | None = None,
    depth: int = 1,                 # Shallow clone depth
    project_path: str | None = None
) -> CloneResult
```

**Implementation**:
1. Get remote URL from local repo: `git remote get-url origin`
2. Generate clone path: `/tmp/gobby-clones/<project>/<branch>/`
3. Execute: `git clone --depth=<depth> --branch=<base_branch> <url> <path>`
4. Create new branch: `git checkout -b <branch_name>`
5. Copy `.gobby/project.json` with `parent_project_path` reference
6. Install provider hooks
7. Record in `clones` table

#### spawn_agent_in_clone

```python
spawn_agent_in_clone(
    prompt: str,
    branch_name: str,
    base_branch: str = "main",
    task_id: str | None = None,
    parent_session_id: str | None = None,
    mode: str = "terminal",
    provider: str = "claude",
    model: str | None = None,
    workflow: str | None = None,
    timeout: float = 120.0,
    max_turns: int = 10,
    project_path: str | None = None
) -> SpawnResult
```

**Implementation**:
1. Call `create_clone()` if clone doesn't exist
2. Build enhanced prompt with clone context
3. Use same spawner logic as `spawn_agent_in_worktree()`
4. Claim clone for child session
5. Pre-save workflow state with `session_task`

#### sync_clone

```python
sync_clone(
    clone_id: str,
    direction: Literal["pull", "push"] = "pull"
) -> SyncResult
```

**Implementation**:
- **pull**: `git fetch origin && git rebase origin/<base_branch>`
- **push**: `git push origin <branch_name>`

Unlike worktrees, clones require explicit sync since they don't share refs.

#### merge_clone_to_target

```python
merge_clone_to_target(
    clone_id: str,
    target_branch: str = "dev",
    strategy: str = "merge"
) -> MergeResult
```

**Implementation**:
1. `sync_clone(clone_id, "push")` - Ensure branch is on remote
2. In main repo: `git fetch origin && git checkout <target_branch>`
3. `git merge origin/<branch_name>` or use gobby-merge for conflicts
4. Set `cleanup_after = now + 7 days`
5. Mark clone as "merged"

#### delete_clone

```python
delete_clone(
    clone_id: str,
    force: bool = False,
    delete_remote_branch: bool = False
) -> DeleteResult
```

**Implementation**:
1. Check for uncommitted changes (unless force)
2. `rm -rf <clone_path>`
3. Optionally: `git push origin --delete <branch_name>`
4. Remove from `clones` table

#### Other Tools

```python
list_clones(project_id, status, limit) -> List[Clone]
get_clone(clone_id) -> Clone
get_clone_by_task(task_id) -> Clone
cleanup_stale_clones(hours=24, dry_run=True) -> CleanupResult
cleanup_merged_clones() -> CleanupResult  # Delete where cleanup_after < now
```

### 16.7 Updated Parallel Orchestrator Workflow

```yaml
# src/gobby/workflows/definitions/parallel-orchestrator.yaml (v2)
name: parallel-orchestrator
description: Process multiple subtasks in parallel using isolated clones

config:
  max_parallel_agents: 3
  isolation_mode: clone          # NEW: "clone" (default) or "worktree"
  auto_sync_interval: 300        # Sync clones every 5 min (optional)
  branch_retention_days: 7       # Keep remote branches after merge

steps:
  - name: select_batch
    allowed_tools: [list_ready_tasks, get_task]

  - name: spawn_batch
    allowed_tools:
      # Clone-based (default)
      - create_clone
      - spawn_agent_in_clone
      # Worktree fallback (when isolation_mode: worktree)
      - create_worktree
      - spawn_agent_in_worktree

  - name: wait_any
    allowed_tools: [wait_for_any_task, wait_for_all_tasks]

  - name: sync_and_review
    allowed_tools:
      - sync_clone               # Pull latest before review
      - read, glob, grep
      - get_clone
      - get_worktree             # Fallback

  - name: process_completed
    allowed_tools:
      - merge_clone_to_target    # Clone merge
      - merge_worktree           # Worktree fallback
      - approve_and_cleanup
      - reopen_task
      - delete_clone
      - delete_worktree

  - name: loop
    transitions:
      - condition: "agents_still_running"
        next: wait_any
      - condition: "has_ready_tasks"
        next: select_batch
      - condition: "all_done"
        next: complete
```

### 16.8 gobby-merge Integration

#### Key Difference: Worktrees vs Clones

| Aspect | Worktree Merge | Clone Merge |
|--------|----------------|-------------|
| Branch location | Local (shared .git) | Remote (isolated .git) |
| Pre-merge step | None | `git fetch origin <branch>` |
| Source ref | `branch_name` | `origin/branch_name` |
| Conflict resolution | In-place | Push resolution back to clone |
| Post-merge cleanup | Delete worktree | Delete clone + optionally remote branch |

#### Updated merge_start()

```python
def merge_start(
    source: str,                    # worktree_id OR clone_id
    target_branch: str = "dev",
    strategy: str = "auto",         # auto, conflict_only, full_file, manual
    main_repo_path: str | None = None,  # Path to main repository (required for clones)
    ...
) -> Resolution:
    if source.startswith("clone-"):
        clone = clone_storage.get(source)
        if not clone:
            return Resolution(success=False, error="Clone not found")

        # Validate main_repo_path for clone operations
        if not main_repo_path:
            return Resolution(success=False, error="main_repo_path is required for clone merges")

        # Step 1: Ensure clone changes are pushed to remote
        sync_result = sync_clone(clone.id, direction="push")
        if not sync_result.success:
            return Resolution(success=False, error=f"Failed to push clone: {sync_result.error}")

        # Step 2: Fetch the branch into main repo
        fetch_result = subprocess.run(
            ["git", "fetch", "origin", clone.branch_name],
            cwd=main_repo_path,
            capture_output=True
        )
        if fetch_result.returncode != 0:
            return Resolution(success=False, error="Failed to fetch branch from remote")

        source_branch = f"origin/{clone.branch_name}"
        source_type = "clone"
    else:
        worktree = worktree_storage.get(source)
        if not worktree:
            return Resolution(success=False, error="Worktree not found")

        source_branch = worktree.branch_name  # Already local
        source_type = "worktree"

    # Continue with existing merge logic...
    return _do_merge(source_branch, target_branch, strategy, source_type, main_repo_path)
```

#### Conflict Resolution Flow for Clones

```
┌─────────────────────────────────────────────────────────────────┐
│                   CLONE MERGE CONFLICT FLOW                     │
└─────────────────────────────────────────────────────────────────┘

1. Agent completes work in clone
   └─► close_task() triggers merge flow

2. sync_clone(clone_id, "push")
   └─► Pushes clone's commits to origin/<branch>

3. merge_start(clone_id, target="dev")
   ├─► git fetch origin <branch>
   ├─► git checkout dev
   └─► git merge origin/<branch>
       │
       ├─► NO CONFLICTS → merge_apply() → Mark clone "merged"
       │
       └─► CONFLICTS DETECTED
           │
           ▼
   ┌─────────────────────────────────────────────────────────┐
   │              CONFLICT RESOLUTION TIERS                  │
   ├─────────────────────────────────────────────────────────┤
   │                                                         │
   │  Tier 1: conflict_only_ai                               │
   │  └─► Send only conflict hunks to LLM                    │
   │      • Input: <<<HEAD ... === ... >>>branch markers     │
   │      • LLM chooses resolution strategy                  │
   │      • Fast, cheap (~100 tokens per conflict)           │
   │                                                         │
   │  Tier 2: full_file_ai (escalation)                      │
   │  └─► Send full file content to LLM                      │
   │      • When hunk-only resolution fails                  │
   │      • Complex semantic conflicts                       │
   │      • More expensive (~1000+ tokens per file)          │
   │                                                         │
   │  Tier 3: human_review (escalation)                      │
   │  └─► Task enters "review" status                        │
   │      • Alert via callme if configured                   │
   │      • Human resolves manually                          │
   │      • Agent cannot proceed until resolved              │
   │                                                         │
   └─────────────────────────────────────────────────────────┘

4. After resolution:
   merge_apply(resolution_id)
   └─► git commit (merge commit)
   └─► Set clone.cleanup_after = now + 7 days
   └─► Mark clone status = "merged"
```

#### merge_resolve() for Clones

```python
def merge_resolve(
    conflict_id: str,
    resolved_content: str | None = None,  # Manual resolution
    use_ai: bool = True,
    tier: str = "conflict_only"           # conflict_only, full_file
) -> ConflictResolution:
    conflict = get_conflict(conflict_id)

    if resolved_content:
        # Manual resolution provided
        return _apply_manual_resolution(conflict, resolved_content)

    if not use_ai:
        # Mark for human review
        return ConflictResolution(
            status="pending_human",
            message="Conflict marked for human review"
        )

    if tier == "conflict_only":
        # Tier 1: Send only conflict markers to LLM
        prompt = f"""
        Resolve this git merge conflict. Return ONLY the resolved code, no explanations.

        File: {conflict.file_path}

        Conflict:
        {conflict.hunk}

        Context: Merging feature branch into dev. Preserve both changes if possible.
        """
        resolved = llm.complete(prompt)

        if _validate_resolution(resolved, conflict):
            return _apply_ai_resolution(conflict, resolved)
        else:
            # Escalate to full file
            return merge_resolve(conflict_id, use_ai=True, tier="full_file")

    elif tier == "full_file":
        # Tier 2: Send full file for complex conflicts
        base_content = _get_base_version(conflict.file_path)
        ours_content = _get_ours_version(conflict.file_path)
        theirs_content = _get_theirs_version(conflict.file_path)

        prompt = f"""
        Merge these three versions of {conflict.file_path}.
        Return the fully merged file content.

        BASE (common ancestor):
        ```
        {base_content}
        ```

        OURS (dev branch):
        ```
        {ours_content}
        ```

        THEIRS (feature branch):
        ```
        {theirs_content}
        ```

        Preserve functionality from both branches. Resolve conflicts intelligently.
        """
        resolved = llm.complete(prompt)

        if _validate_resolution(resolved, conflict):
            return _apply_ai_resolution(conflict, resolved)
        else:
            # Escalate to human
            return ConflictResolution(
                status="pending_human",
                message="AI resolution failed validation, requires human review"
            )
```

#### Handling Clone-Specific Merge Scenarios

**Scenario 1: Multiple clones modifying same file**

```
Clone A modifies: src/auth.py (lines 10-20)
Clone B modifies: src/auth.py (lines 50-60)
                                  │
                                  ▼
        ┌─────────────────────────────────────────┐
        │  Merge Order Matters for Clones         │
        │                                         │
        │  1. Clone A merges first → succeeds     │
        │  2. Clone B merges → may conflict       │
        │     └─► sync_clone("pull") recommended  │
        │         before final merge              │
        └─────────────────────────────────────────┘
```

**Recommendation**: Before merging Clone B, sync it with latest dev:
```python
# In parallel orchestrator, before merge:
sync_clone(clone_id, direction="pull")  # Rebase on latest dev
sync_clone(clone_id, direction="push")  # Push rebased changes
merge_start(clone_id, target="dev")     # Now merge cleanly
```

**Scenario 2: Clone branch diverged significantly**

When clone's branch is many commits behind dev:

```python
def merge_clone_with_rebase(clone_id: str, target: str = "dev") -> MergeResult:
    """Rebase clone onto target before merge for cleaner history."""
    clone = get_clone(clone_id)

    # 1. Fetch latest target into clone
    run_in_clone(clone, ["git", "fetch", "origin", target])

    # 2. Rebase clone's work onto target
    rebase_result = run_in_clone(clone, ["git", "rebase", f"origin/{target}"])

    if rebase_result.conflicts:
        # Handle rebase conflicts (similar to merge conflicts)
        return MergeResult(status="rebase_conflicts", conflicts=rebase_result.conflicts)

    # 3. Push rebased branch
    sync_clone(clone_id, "push", force=True)  # Force push after rebase

    # 4. Now merge is fast-forward
    return merge_start(clone_id, target)
```

#### Error Handling

```python
class CloneMergeError(Exception):
    """Errors specific to clone merge operations."""
    pass

def merge_clone_to_target(clone_id: str, target: str = "dev") -> MergeResult:
    try:
        clone = clone_storage.get(clone_id)
        if not clone:
            raise CloneMergeError(f"Clone {clone_id} not found")

        if clone.status == "merged":
            raise CloneMergeError(f"Clone {clone_id} already merged")

        if clone.status == "abandoned":
            raise CloneMergeError(f"Clone {clone_id} is abandoned")

        # Check for uncommitted changes in clone
        if _has_uncommitted_changes(clone.clone_path):
            raise CloneMergeError(
                "Clone has uncommitted changes. Commit or stash before merge."
            )

        # Proceed with merge...
        return _do_clone_merge(clone, target)

    except subprocess.CalledProcessError as e:
        return MergeResult(
            success=False,
            error=f"Git command failed: {e.stderr.decode()}"
        )
    except CloneMergeError as e:
        return MergeResult(success=False, error=str(e))
```

### 16.9 CLI Commands

```bash
# Clone management
gobby clones create <branch-name> [--base main] [--task <id>]
gobby clones list [--status active|merged|abandoned]
gobby clones spawn <branch-name> "<prompt>" [--provider claude]
gobby clones sync <clone-id> [--direction pull|push]
gobby clones merge <clone-id> [--target dev]
gobby clones delete <clone-id> [--force] [--delete-remote]
gobby clones cleanup [--hours 24] [--dry-run]
gobby clones cleanup-merged                    # Delete clones past retention period
```

### 16.10 Context Injection

```python
def _build_clone_context_prompt(
    original_prompt: str,
    clone_path: str,
    branch_name: str,
    task_id: str | None,
    main_repo_path: str | None = None,
) -> str:
    """Build enhanced prompt with clone context."""
    context_lines = [
        "## CRITICAL: Clone Context",
        "You are working in an ISOLATED git clone, NOT the main repository.",
        "",
        f"**Your workspace:** {clone_path}",
        f"**Your branch:** {branch_name}",
    ]

    if task_id:
        context_lines.append(f"**Your task:** {task_id}")

    context_lines.extend([
        "",
        "**IMPORTANT RULES:**",
        f"1. ALL file operations must be within {clone_path}",
        "2. Your commits are LOCAL until synced - don't worry about conflicts yet",
        "3. Run `pwd` to verify your location before any file operations",
        f"4. Commit to YOUR branch ({branch_name}), not main/dev",
        "5. When your assigned task is complete, STOP - orchestrator handles merge",
        "",
        "---",
        "",
    ])

    return "\n".join(context_lines) + original_prompt
```

### 16.11 Performance Comparison

| Metric | Worktree | Shallow Clone (depth=1) |
|--------|----------|-------------------------|
| Disk space | ~50MB (shared .git) | ~100-200MB |
| Setup time | ~2-5 seconds | ~10-30 seconds |
| Concurrent safety | ❌ Lock contention | ✅ Fully isolated |
| Network required | No | Yes (initial clone) |
| Sync complexity | Implicit | Explicit (pull/push) |

**Recommendation**: Use shallow clones (`depth=1`) to minimize disk/network overhead.

### 16.12 Cleanup Strategy

1. **On task completion**:
   - `merge_clone_to_target()` sets `cleanup_after = now + 7 days`
   - Mark clone as "merged"

2. **Periodic cleanup** (ConductorLoop):
   - `cleanup_merged_clones()`: Delete where `cleanup_after < now`
   - `cleanup_stale_clones(hours=24)`: Mark abandoned, optionally delete

3. **Manual cleanup**:
   - `gobby clones cleanup-merged`: Delete merged clones past retention
   - `gobby clones delete <id> --delete-remote`: Full cleanup including remote branch

### 16.13 Authentication & SSH Handling

#### The Problem

Clones require network access to the remote repository. Unlike worktrees (which share the local `.git` directory), clones must authenticate with the remote for:
- Initial `git clone`
- `sync_clone("pull")` - fetch latest changes
- `sync_clone("push")` - push commits
- Remote branch deletion

#### Authentication Strategy

**Principle**: Use the same authentication method as the local repository.

```python
def _get_remote_url(repo_path: str) -> str:
    """Get the remote URL from local repo config."""
    result = subprocess.run(
        ["git", "remote", "get-url", "origin"],
        cwd=repo_path,
        capture_output=True,
        text=True
    )
    return result.stdout.strip()
```

#### URL Format Detection

```python
def _detect_auth_method(url: str) -> AuthMethod:
    """Detect authentication method from remote URL."""
    if url.startswith("git@") or url.startswith("ssh://"):
        return AuthMethod.SSH
    elif url.startswith("https://"):
        if "@" in url:
            # https://user:token@github.com/...
            return AuthMethod.HTTPS_TOKEN_IN_URL
        else:
            # https://github.com/... (relies on credential helper)
            return AuthMethod.HTTPS_CREDENTIAL_HELPER
    elif url.startswith("http://"):
        return AuthMethod.HTTP_INSECURE
    else:
        return AuthMethod.UNKNOWN
```

#### SSH Authentication

**How it works**: SSH keys are system-wide; clones automatically use them.

```
Local repo uses: git@github.com:user/project.git
                            │
                            ▼
Clone inherits same URL → SSH agent provides key automatically
```

**Requirements**:
- SSH key added to ssh-agent (`ssh-add`)
- Key authorized on GitHub/GitLab
- `~/.ssh/config` configured if using non-default key

**No additional configuration needed** - clones just work.

#### HTTPS with Credential Helper

**How it works**: Git credential helpers (macOS Keychain, Windows Credential Manager, `git-credential-store`) cache tokens.

```
Local repo uses: https://github.com/user/project.git
                            │
                            ▼
Clone uses same URL → Credential helper provides token
```

**Common credential helpers**:
```bash
# macOS (uses Keychain)
git config --global credential.helper osxkeychain

# Windows (uses Credential Manager)
git config --global credential.helper manager-core

# Linux (caches in memory for 15 min)
git config --global credential.helper cache

# Store in plaintext file (less secure)
git config --global credential.helper store
```

#### HTTPS with Token in URL

**Format**: `https://oauth2:TOKEN@github.com/user/project.git`

**Handling**: Token is part of URL, clones inherit it automatically.

```python
def create_clone(...):
    remote_url = _get_remote_url(project_path)

    # URL may contain token - clone will inherit it
    # Example: https://oauth2:ghp_xxx@github.com/user/repo.git
    subprocess.run([
        "git", "clone",
        "--depth", str(depth),
        "--branch", base_branch,
        remote_url,  # Token embedded if present
        clone_path
    ])
```

**Security Note**: Token-in-URL is visible in git config. For CI/CD, prefer credential helpers or SSH.

#### GitHub CLI Integration (gh)

For GitHub repos, `gh` can provide authentication:

```python
def _setup_gh_auth_for_clone(clone_path: str) -> bool:
    """Configure clone to use gh for authentication."""
    try:
        # Check if gh is authenticated
        result = subprocess.run(
            ["gh", "auth", "status"],
            capture_output=True
        )
        if result.returncode != 0:
            return False

        # Configure git to use gh as credential helper
        subprocess.run([
            "git", "config", "--local",
            "credential.https://github.com.helper",
            "!/usr/bin/gh auth git-credential"
        ], cwd=clone_path)

        return True
    except FileNotFoundError:
        return False  # gh not installed
```

#### Environment Variable Passthrough

For CI/CD or automated environments, ensure auth environment variables are available:

```python
def _get_clone_env() -> dict:
    """Get environment variables for clone operations."""
    env = os.environ.copy()

    # SSH agent socket
    if "SSH_AUTH_SOCK" in os.environ:
        env["SSH_AUTH_SOCK"] = os.environ["SSH_AUTH_SOCK"]

    # GitHub token (for gh cli or direct API)
    for var in ["GITHUB_TOKEN", "GH_TOKEN", "GITLAB_TOKEN"]:
        if var in os.environ:
            env[var] = os.environ[var]

    # Git askpass for non-interactive auth
    if "GIT_ASKPASS" in os.environ:
        env["GIT_ASKPASS"] = os.environ["GIT_ASKPASS"]

    return env

def create_clone(...):
    env = _get_clone_env()
    subprocess.run(
        ["git", "clone", ...],
        env=env,
        ...
    )
```

#### Troubleshooting Authentication

**Problem**: Clone fails with "Authentication failed"

```python
def diagnose_auth_failure(remote_url: str) -> AuthDiagnosis:
    """Diagnose why authentication failed."""
    auth_method = _detect_auth_method(remote_url)

    if auth_method == AuthMethod.SSH:
        # Check SSH agent
        agent_check = subprocess.run(
            ["ssh-add", "-l"],
            capture_output=True
        )
        if agent_check.returncode != 0:
            return AuthDiagnosis(
                method="SSH",
                error="No SSH keys in agent",
                fix="Run: ssh-add ~/.ssh/id_ed25519"
            )

        # Test SSH connection
        host = _extract_host(remote_url)  # github.com, gitlab.com, etc.
        ssh_test = subprocess.run(
            ["ssh", "-T", f"git@{host}"],
            capture_output=True
        )
        if "successfully authenticated" not in ssh_test.stderr.decode():
            return AuthDiagnosis(
                method="SSH",
                error=f"SSH key not authorized on {host}",
                fix=f"Add SSH key to {host} account settings"
            )

    elif auth_method == AuthMethod.HTTPS_CREDENTIAL_HELPER:
        # Check credential helper config
        helper = subprocess.run(
            ["git", "config", "--get", "credential.helper"],
            capture_output=True,
            text=True
        )
        if not helper.stdout.strip():
            return AuthDiagnosis(
                method="HTTPS",
                error="No credential helper configured",
                fix="Run: git config --global credential.helper osxkeychain"
            )

    return AuthDiagnosis(method=auth_method.value, error="Unknown", fix="Check git logs")
```

#### Private Repository Considerations

For private repos, ensure:

1. **SSH method** (recommended for agents):
   - SSH key has read/write access
   - Key passphrase is cached in ssh-agent (or use keyless)
   - For deploy keys: must be repo-specific

2. **HTTPS with PAT**:
   - Token has `repo` scope (full access) or fine-grained permissions
   - Token not expired
   - Token stored in credential helper or URL

3. **GitHub App** (enterprise):
   - App installed on repo
   - Installation token generated and cached

#### Configuration in gobby

```yaml
# ~/.gobby/config.yaml
clones:
  # Preferred auth method (auto-detected if not set)
  auth_method: auto  # auto, ssh, https, gh

  # For HTTPS: path to token file (alternative to credential helper)
  token_file: ~/.gobby/github_token

  # SSH key to use (if not default)
  ssh_key: ~/.ssh/gobby_deploy_key

  # Passthrough environment variables
  env_passthrough:
    - SSH_AUTH_SOCK
    - GITHUB_TOKEN
    - GH_TOKEN
```

### 16.14 Comparison with CodeRabbit GTR

[git-worktree-runner](https://github.com/coderabbitai/git-worktree-runner) (GTR) is CodeRabbit's solution for parallel development.

| Feature | Gobby Clones | GTR |
|---------|--------------|-----|
| Isolation | Full clones | Worktrees |
| Thread safety | ✅ Isolated .git | ❌ Shared .git |
| AI integration | Native (spawn_agent_in_clone) | Via `git gtr ai` |
| Merge handling | gobby-merge with AI resolution | Manual |
| Task linking | Built-in task_id | None |
| Cleanup | 7-day retention + auto-cleanup | `--merged` flag |

**Key difference**: Gobby uses clones for true parallelism safety, while GTR wraps worktrees with convenience commands.

---

## Implementation Files

### New Files

| File | Purpose |
|------|---------|
| `src/gobby/storage/clones.py` | Clone model + LocalCloneManager |
| `src/gobby/clones/__init__.py` | Module init |
| `src/gobby/clones/git.py` | CloneGitManager (shallow clone ops) |
| `src/gobby/mcp_proxy/tools/clones.py` | MCP tools for gobby-clones server |
| `src/gobby/cli/clones.py` | CLI commands |
| `src/gobby/install/shared/skills/gobby-clones/SKILL.md` | Skill documentation |

### Modified Files

| File | Changes |
|------|---------|
| `docs/plans/orchestration.md` | Add Section 16 |
| `docs/research/investigate-gtr-ccmanager.md` | Mark action items as addressed |
| `src/gobby/storage/migrations.py` | Add `clones` table |
| `src/gobby/worktrees/merge/resolver.py` | Support clone sources |
| `src/gobby/runner.py` | Register gobby-clones server |
| `src/gobby/mcp_proxy/registry.py` | Add clones registry |
| `src/gobby/workflows/definitions/parallel-orchestrator.yaml` | Add clone support |
| `CLAUDE.md` | Add gobby-clones to MCP server table |

### Test Files

| File | Validates |
|------|-----------|
| `tests/storage/test_clones.py` | Clone storage layer |
| `tests/clones/test_git.py` | CloneGitManager operations |
| `tests/mcp_proxy/tools/test_clones.py` | MCP tool behavior |
| `tests/e2e/test_parallel_clones.py` | Full parallel orchestration with clones |

---

## Verification

```bash
# Unit tests
uv run pytest tests/storage/test_clones.py -v
uv run pytest tests/clones/test_git.py -v

# Integration test: Create and spawn in clone
gobby clones create feature/test-clone --base main
gobby clones spawn feature/test-clone "Write a hello world function"

# E2E test: Parallel orchestration with clones
# 1. Create epic with 3 independent subtasks
gobby tasks create "Parallel test epic" --type=epic
gobby tasks expand <epic-id>

# 2. Activate parallel-orchestrator (uses clone by default)
gobby workflows set parallel-orchestrator

# 3. Verify no lock contention with 3 concurrent agents
# 4. All 3 tasks complete and merge successfully
# 5. Remote branches retained for 7 days
```

---

## Phase Integration

This section integrates into the existing orchestration.md implementation phases:

**Phase C Extension**: Add clone tools to Interactive Orchestration Workflows
- Create `gobby-clones` MCP server alongside workflow definitions
- Update `parallel-orchestrator.yaml` with `isolation_mode` config

**Phase F Extension**: Add clone-specific E2E tests
- `tests/e2e/test_parallel_clones.py`: Verify no lock contention
- Compare worktree vs clone performance metrics
