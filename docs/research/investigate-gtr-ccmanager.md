# Research: Git Worktree Runner (GTR) and CCManager Patterns

## Context

During E2E testing of Gobby's parallel agent orchestration, we discovered fundamental issues with AI agents working in git worktrees. This document captures research into community tools addressing similar problems.

## Problems Identified

### Problem 1: Gemini CLI Doesn't Handle Worktrees

**Observation**: Spawned Gemini agent worked in main repo instead of worktree despite correct `cwd`.

**Root Cause**: Gemini CLI's `findProjectRoot()` searches for a `.git` **directory**. Git worktrees have a `.git` **file** (not directory) containing:
```
gitdir: /path/to/main/.git/worktrees/<worktree-name>
```

Gemini follows this path back to the main repo's `.git/worktrees/` folder, incorrectly detecting the main repo as the project root.

**Workaround Implemented**: Strong prompt injection (see `_build_worktree_context_prompt()` in `worktrees.py`).

**Long-term Fix**: File issue with Gemini CLI to handle `.git` files for worktrees.

### Problem 2: Git is NOT Thread-Safe

**Key Finding**: Git's internal data structures are not designed for concurrent multi-process access from a single machine.

All worktrees share a single `.git` directory, leading to:
- Race conditions during concurrent operations (checkout, commit, etc.)
- Lock file contention (`index.lock`, `HEAD.lock`)
- Potential repository corruption with aggressive parallel agents

**Implication**: For truly parallel agent work, separate repository clones are safer than worktrees.

## Community Tools

### 1. Git Worktree Runner (GTR)

**Repository**: https://github.com/coderabbitai/git-worktree-runner

**Creator**: CodeRabbit AI

**Key Features**:
- Manages worktree lifecycle (create, cleanup)
- Runs commands in isolated worktrees
- Async hooks for pre/post execution
- Automatic cleanup on process termination

**Patterns to Consider**:
- Hook system for worktree lifecycle events
- Cleanup guarantees (atexit handlers)
- Worktree naming conventions

### 2. CCManager

**Repository**: https://github.com/kbwo/ccmanager

**Description**: Multi-agent session manager with worktree support

**Key Features**:
- Session persistence across restarts
- Worktree-per-agent isolation
- Context sharing between agents
- tmux/terminal integration

**Patterns to Consider**:
- Session-worktree linking
- Cross-agent context propagation
- Terminal multiplexer integration

### 3. Fish Shell Wrappers (Claude Code Issues)

**Reference**: https://github.com/anthropics/claude-code/issues/1052

**Community Solution**: Fish shell wrapper that:
- Detects worktree via `.git` file
- Sets `GIT_DIR` and `GIT_WORK_TREE` environment variables
- Forces CLI to operate in correct context

**Key Insight**: Environment variable overrides may be more reliable than CLI flags.

## Proposed Solution: Clone-Based Parallel Agents

### Why Clones Over Worktrees for Parallel Work

| Aspect | Worktrees | Clones |
|--------|-----------|--------|
| Storage | Shared `.git` | Isolated `.git` per clone |
| Thread Safety | **Risky** - shared locks | **Safe** - fully isolated |
| Disk Space | Efficient | More disk usage |
| Setup Speed | Fast (shared objects) | Slower (full clone) |
| Sync Complexity | Implicit (shared) | Explicit (git pull/push) |

### Recommended Architecture

```
/tmp/gobby-clones/
  <project-name>/
    <task-id-or-branch>/           # Full clone
      .git/                         # Isolated git directory
      ... project files ...
```

### New MCP Tools (Phase 4)

```python
# create_clone(branch_name, base_branch, task_id) -> Clone
#   - git clone --depth=1 --branch=base_branch repo /tmp/gobby-clones/...
#   - Shallow clone for speed
#   - Track in DB: clone_id, path, branch, task_id, created_at

# spawn_agent_in_clone(prompt, branch_name, task_id, provider, mode) -> AgentRun
#   - Creates clone if not exists
#   - Spawns agent with cwd=clone_path
#   - Agent sees regular .git directory

# sync_clone(clone_id, direction="pull"|"push") -> SyncResult
#   - pull: git pull --rebase origin base_branch
#   - push: git push origin branch_name

# delete_clone(clone_id, force=False) -> DeleteResult
#   - rm -rf clone_path
#   - Remove from DB
```

### When to Use Each Approach

| Scenario | Recommendation |
|----------|----------------|
| Sequential tasks (one agent at a time) | Worktree (efficient) |
| Parallel tasks (multiple agents) | Clones (safe) |
| Short-lived tasks | Worktree (fast setup) |
| Long-running tasks | Either (based on parallelism) |
| CI/CD environments | Clones (isolation) |

## Implementation Priority

1. **Immediate (Done)**:
   - Prompt injection for worktree context
   - `session_task` scoping for task suggestions

2. **Short-term**:
   - Add `spawn_agent_in_clone()` for parallel orchestrator
   - Update parallel-orchestrator workflow to use clones
   - **Update gobby-merge to handle clones**: Unlike worktrees (which share refs with main repo), clones need explicit sync before merge. `merge_start()` may need to fetch from clone's origin or accept a clone path.

3. **Medium-term**:
   - Environment variable approach (GIT_DIR/GIT_WORK_TREE)
   - File issue with Gemini CLI for worktree support

4. **Long-term**:
   - Evaluate adopting GTR patterns (cleanup hooks)
   - Consider CCManager-style session persistence

## References

- [Git Worktree Documentation](https://git-scm.com/docs/git-worktree)
- [Gemini CLI Source](https://github.com/google-gemini/gemini-cli)
- [Claude Code Worktree Issues](https://github.com/anthropics/claude-code/issues?q=worktree)
- [Git Thread Safety Discussion](https://stackoverflow.com/questions/5510000/is-git-thread-safe)

## Action Items

- [ ] Implement `spawn_agent_in_clone()` for parallel-orchestrator
- [ ] Update gobby-merge to handle clone sync/merge (clones don't share refs like worktrees)
- [ ] File bug report with Gemini CLI for worktree support
- [ ] Test environment variable approach (GIT_DIR/GIT_WORK_TREE)
- [ ] Benchmark clone vs worktree performance for typical task sizes
- [ ] Add cleanup hooks for abandoned clones (similar to GTR)
