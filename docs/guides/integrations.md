# Integrations Guide

Gobby integrates with external project management tools to sync tasks bidirectionally.

## Overview

| Integration | Features |
|-------------|----------|
| **GitHub** | Import issues, sync tasks, create PRs |
| **Linear** | Import issues, sync tasks, create issues |

## GitHub Integration

### Setup

Link a GitHub repository to your project:

```bash
# Link repository
gobby github link https://github.com/owner/repo

# Check status
gobby github status
```

**Authentication:**

GitHub integration uses the `gh` CLI for authentication. Ensure you're logged in:

```bash
gh auth login
```

### CLI Commands

#### `gobby github status`

Show GitHub integration status.

```bash
gobby github status
```

Displays:
- Linked repository
- Authentication status
- Sync statistics

#### `gobby github link`

Link a GitHub repo to this project.

```bash
gobby github link REPO_URL
```

**Examples:**

```bash
gobby github link https://github.com/owner/repo
gobby github link owner/repo  # Shorthand
```

#### `gobby github unlink`

Remove GitHub repo link from this project.

```bash
gobby github unlink
```

#### `gobby github import`

Import GitHub issues as gobby tasks.

```bash
gobby github import [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--state` | Issue state: open, closed, all (default: open) |
| `--labels` | Filter by labels (comma-separated) |
| `--limit N` | Max issues to import |
| `--assignee` | Filter by assignee |

**Examples:**

```bash
# Import all open issues
gobby github import

# Import bugs only
gobby github import --labels bug

# Import with limit
gobby github import --limit 50 --state all
```

#### `gobby github sync`

Sync a task to its linked GitHub issue.

```bash
gobby github sync TASK_ID
```

Updates the GitHub issue with:
- Task status
- Comments/notes
- Labels

#### `gobby github pr`

Create a GitHub PR for a task.

```bash
gobby github pr TASK_ID [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--branch` | Source branch (auto-detected from task worktree) |
| `--base` | Base branch (default: main) |
| `--draft` | Create as draft PR |

**Examples:**

```bash
# Create PR for task
gobby github pr #123

# Create draft PR
gobby github pr #123 --draft

# Specify branches
gobby github pr #123 --branch feature/auth --base develop
```

### MCP Tools

GitHub tools are available via `gobby-tasks`:

#### import_github_issues

Import GitHub issues as tasks.

```python
call_tool(server_name="gobby-tasks", tool_name="import_github_issues", arguments={
    "state": "open",
    "labels": ["bug", "priority-high"],
    "limit": 50
})
```

#### sync_task_to_github

Sync task status to linked GitHub issue.

```python
call_tool(server_name="gobby-tasks", tool_name="sync_task_to_github", arguments={
    "task_id": "#123"
})
```

#### create_pr_for_task

Create a GitHub PR for a task.

```python
call_tool(server_name="gobby-tasks", tool_name="create_pr_for_task", arguments={
    "task_id": "#123",
    "base_branch": "main",
    "draft": False
})
```

#### link_github_repo

Link a GitHub repository to the project.

```python
call_tool(server_name="gobby-tasks", tool_name="link_github_repo", arguments={
    "repo_url": "https://github.com/owner/repo"
})
```

#### unlink_github_repo

Remove GitHub repo link.

```python
call_tool(server_name="gobby-tasks", tool_name="unlink_github_repo", arguments={})
```

#### get_github_status

Get GitHub integration status.

```python
call_tool(server_name="gobby-tasks", tool_name="get_github_status", arguments={})
```

### Mapping

| GitHub | Gobby |
|--------|-------|
| Issue | Task |
| Issue title | Task title |
| Issue body | Task description |
| Labels | Task labels |
| Assignee | Task assignee |
| Open | open |
| Closed | closed |

### Workflow Example

```bash
# 1. Link repository
gobby github link owner/repo

# 2. Import issues
gobby github import --labels "priority-high"

# 3. Work on task
gobby tasks update #123 --status in_progress

# 4. Create PR when done
gobby github pr #123

# 5. Sync status back
gobby github sync #123
```

---

## Linear Integration

### Setup

Link a Linear team to your project:

```bash
# Link team
gobby linear link TEAM_ID

# Check status
gobby linear status
```

**Authentication:**

Set your Linear API key:

```bash
export LINEAR_API_KEY="lin_api_..."
```

Or configure in `~/.gobby/config.yaml`:

```yaml
integrations:
  linear:
    api_key: "lin_api_..."
```

### CLI Commands

#### `gobby linear status`

Show Linear integration status.

```bash
gobby linear status
```

#### `gobby linear link`

Link a Linear team to this project.

```bash
gobby linear link TEAM_ID
```

#### `gobby linear unlink`

Remove Linear team link from this project.

```bash
gobby linear unlink
```

#### `gobby linear import`

Import Linear issues as gobby tasks.

```bash
gobby linear import [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--state` | Issue state filter |
| `--labels` | Filter by labels |
| `--limit N` | Max issues to import |
| `--project` | Filter by Linear project |

**Examples:**

```bash
# Import all active issues
gobby linear import

# Import from specific project
gobby linear import --project "Backend"

# Import with label filter
gobby linear import --labels "bug"
```

#### `gobby linear sync`

Sync a task to its linked Linear issue.

```bash
gobby linear sync TASK_ID
```

#### `gobby linear create`

Create a Linear issue from a gobby task.

```bash
gobby linear create TASK_ID [OPTIONS]
```

| Option | Description |
|--------|-------------|
| `--project` | Linear project to create in |
| `--labels` | Labels to apply |

### Mapping

| Linear | Gobby |
|--------|-------|
| Issue | Task |
| Title | Task title |
| Description | Task description |
| Labels | Task labels |
| Assignee | Task assignee |
| Backlog/Todo | open |
| In Progress | in_progress |
| Done | closed |

### Workflow Example

```bash
# 1. Link team
gobby linear link TEAM_123

# 2. Import issues
gobby linear import --project "Q1 Sprint"

# 3. Work on task
gobby tasks update #123 --status in_progress

# 4. Sync changes back to Linear
gobby linear sync #123

# 5. Or create new Linear issue from task
gobby linear create #456
```

---

## Bidirectional Sync

Both integrations support bidirectional sync:

### Import Flow

```text
GitHub/Linear Issue → gobby tasks import → Gobby Task
                                              ↓
                                    external_id stored
```

### Export Flow

```text
Gobby Task → gobby github/linear sync → GitHub/Linear Issue
     ↓
Updates:
- Status
- Comments
- Labels
```

### Conflict Resolution

When both sides have changes:

1. **Last-write-wins**: Most recent change takes precedence
2. **Manual resolution**: Review conflicts in CLI output
3. **Force sync**: `--force` flag overwrites remote

---

## Configuration

Configure integrations in `~/.gobby/config.yaml`:

```yaml
integrations:
  github:
    enabled: true
    auto_sync: false  # Auto-sync on task close
    default_labels: ["gobby-managed"]

  linear:
    enabled: true
    api_key: "${LINEAR_API_KEY}"  # Environment variable
    auto_sync: false
    default_project: "Backlog"
```

### Project-Level Configuration

Configure per-project in `.gobby/project.json`:

```json
{
  "integrations": {
    "github": {
      "repo": "owner/repo",
      "import_labels": ["bug", "feature"],
      "sync_on_close": true
    },
    "linear": {
      "team_id": "TEAM_123",
      "project_id": "PROJECT_456"
    }
  }
}
```

---

## Best Practices

### Do

- Link integrations at project start
- Import existing issues before creating tasks
- Use consistent labels across systems
- Sync regularly to keep systems aligned

### Don't

- Create duplicate tasks manually
- Ignore sync conflicts
- Delete linked issues without unlinking
- Store API keys in project files

## Troubleshooting

### GitHub: Authentication failed

```bash
# Re-authenticate with gh CLI
gh auth login
gh auth status
```

### Linear: API key invalid

```bash
# Verify key is set
echo $LINEAR_API_KEY

# Test with curl
curl -H "Authorization: $LINEAR_API_KEY" https://api.linear.app/graphql
```

### Sync conflicts

```bash
# Force sync from Gobby to remote
gobby github sync #123 --force

# Or re-import from remote
gobby github import --force
```

## See Also

- [tasks.md](tasks.md) - Task management
- [cli-commands.md](cli-commands.md) - Full CLI reference
- [mcp-tools.md](mcp-tools.md) - MCP tool reference
