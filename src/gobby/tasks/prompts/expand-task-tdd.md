# TDD Mode Instructions

**IMPORTANT:** Do NOT create separate test/implement/refactor tasks. The system handles TDD structure automatically.

For each coding feature, output a SINGLE task with just the feature name:
- Title: "User authentication" (NOT "Write tests for user authentication")
- Title: "Database connection pooling" (NOT "Implement database connection pooling")

The system will automatically expand coding tasks into TDD triplets:
1. Write tests for: <title>
2. Implement: <title>
3. Refactor: <title>

## Task Types

| task_type | Description | TDD Expansion |
|-----------|-------------|---------------|
| `feature` | New functionality requiring code implementation | Yes - expands to TDD triplet |
| `task` | General coding work (default) | Yes - expands to TDD triplet |
| `bug` | Bug fix requiring code changes | Yes - expands to TDD triplet |
| `epic` | Non-coding tasks: documentation, research, design, planning | No - stays as single task |

For NON-coding tasks (documentation, research, design, planning, configuration):
- Set `task_type: "epic"` or start the title with keywords like "Document", "Research", "Design", "Plan"
- These will NOT be expanded into TDD triplets

## Subtask Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| title | string | Yes | Short, actionable title for the subtask |
| description | string | No | Detailed description with implementation notes and context |
| task_type | string | No | One of: "feature", "task" (default), "bug", "epic" |

## Example Output

```json
{
  "subtasks": [
    {"title": "User authentication", "task_type": "feature", "description": "Login, logout, and session management"},
    {"title": "Database connection pooling", "task_type": "task", "description": "Add pooling for database connections"},
    {"title": "Document the API endpoints", "task_type": "epic", "description": "Write API documentation for all endpoints"}
  ]
}
```

The first two become TDD triplets (6 tasks total). The third stays as a single task.
