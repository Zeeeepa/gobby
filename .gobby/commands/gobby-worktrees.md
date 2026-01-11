---
description: This skill should be used when the user asks to "/gobby-worktrees", "create worktree", "spawn in worktree". Manage git worktrees for parallel development - create, list, spawn agents, and cleanup.
---

# /gobby-worktrees - Worktree Management Skill

This skill manages git worktrees via the gobby-worktrees MCP server. Parse the user's input to determine which subcommand to execute.

## Subcommands

### `/gobby-worktrees create <branch-name>` - Create a new worktree
Call `gobby-worktrees.create_worktree` with:
- `branch_name`: Name for the new branch
- `task_id`: Optional task ID to associate
- `base_branch`: Optional base branch (default: current)

Creates an isolated git worktree for parallel development.

Example: `/gobby-worktrees create feature/auth`
→ `create_worktree(branch_name="feature/auth")`

Example: `/gobby-worktrees create feature/auth --task gt-abc123`
→ `create_worktree(branch_name="feature/auth", task_id="gt-abc123")`

### `/gobby-worktrees list` - List all worktrees
Call `gobby-worktrees.list_worktrees` with:
- `status`: Optional filter (active, stale, merged, abandoned)

Returns worktrees with path, branch, status, and associated task.

Example: `/gobby-worktrees list` → `list_worktrees()`
Example: `/gobby-worktrees list active` → `list_worktrees(status="active")`

### `/gobby-worktrees spawn <branch-name> <prompt>` - Spawn agent in new worktree
Call `gobby-worktrees.spawn_agent_in_worktree` with:
- `branch_name`: Name for the new branch
- `prompt`: Task description for the agent
- `task_id`: Optional task ID
- `mode`: Agent mode (terminal, headless)

Creates worktree + spawns agent in one call.

Example: `/gobby-worktrees spawn feature/auth Implement OAuth login`
→ `spawn_agent_in_worktree(branch_name="feature/auth", prompt="Implement OAuth login")`

### `/gobby-worktrees cleanup` - Clean up stale worktrees
Call `gobby-worktrees.cleanup_worktrees` to remove:
- Merged worktrees (already merged to main)
- Stale worktrees (no activity for 7+ days)
- Abandoned worktrees (marked abandoned)

Example: `/gobby-worktrees cleanup` → `cleanup_worktrees()`

## Response Format

After executing the appropriate MCP tool, present the results clearly:
- For create: Show worktree path, branch name, and status
- For list: Table with branch, path, status, task ID
- For spawn: Show worktree + agent creation confirmation
- For cleanup: Summary of removed worktrees

## Worktree Lifecycle

1. `active` - Currently in use
2. `stale` - No recent activity
3. `merged` - Branch merged to main
4. `abandoned` - Manually marked for cleanup

## Error Handling

If the subcommand is not recognized, show available subcommands:
- create, list, spawn, cleanup
