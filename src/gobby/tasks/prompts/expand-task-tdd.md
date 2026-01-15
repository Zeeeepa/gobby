# TDD Mode Instructions

**IMPORTANT:** Do NOT create separate test/implement/refactor tasks. The system handles TDD structure automatically.

For each coding feature, output a SINGLE task with just the feature name:
- Title: "User authentication" (NOT "Write tests for user authentication")
- Title: "Database connection pooling" (NOT "Implement database connection pooling")

The system will automatically expand coding tasks into TDD triplets:
1. Write tests for: <title>
2. Implement: <title>
3. Refactor: <title>

For NON-coding tasks (documentation, research, design, planning, configuration):
- Set `task_type: "epic"` or start the title with keywords like "Document", "Research", "Design", "Plan"
- These will NOT be expanded into TDD triplets

## Example Output

```json
{
  "subtasks": [
    {"title": "User authentication", "task_type": "feature", "description": "Login, logout, and session management"},
    {"title": "Database connection pooling", "task_type": "task"},
    {"title": "Document the API endpoints", "task_type": "epic"}
  ]
}
```

The first two become TDD triplets (6 tasks total). The third stays as a single task.
