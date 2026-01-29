---
name: expansion-user
description: User prompt template for task expansion with context injection
version: "1.0"
variables:
  task_id:
    type: str
    required: true
    description: The parent task ID
  title:
    type: str
    required: true
    description: The parent task title
  description:
    type: str
    default: ""
    description: The parent task description
  context_str:
    type: str
    default: "No additional context available."
    description: Formatted context information (files, tests, patterns)
  research_str:
    type: str
    default: "No research performed."
    description: Agent research findings
---
Analyze and expand this task into subtasks.

## Parent Task
- **ID**: {{ task_id }}
- **Title**: {{ title }}
- **Description**: {{ description }}

## Context
{{ context_str }}

## Research Findings
{{ research_str }}

## Instructions

Return a JSON object with a "subtasks" array. Each subtask must have these fields:

### Required Fields
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `title` | string | Yes | Brief, imperative task title (e.g., "Add login endpoint") |
| `description` | string | Yes | Detailed description of what needs to be done |
| `priority` | integer | No | 1=High, 2=Medium (default), 3=Low |
| `task_type` | string | No | "task" (default), "bug", "feature", "epic", "spike" |
| `category` | string | Yes | See allowed values below |
| `validation` | string | No | How to verify completion (e.g., "Tests pass", "File exists") |
| `depends_on` | array | No | 0-based indices of subtasks this depends on (e.g., [0, 1]) |

### Allowed Categories
Use exactly one of: `code`, `config`, `docs`, `refactor`, `research`, `planning`, `manual`

**Note**: The category `test` is forbidden — use `code` for test-related tasks.

### Example Output
```json
{
  "subtasks": [
    {
      "title": "Create database schema",
      "description": "Define the SQLite schema for user accounts",
      "priority": 1,
      "task_type": "task",
      "category": "code",
      "validation": "Schema file exists and migrations run",
      "depends_on": []
    },
    {
      "title": "Implement user model",
      "description": "Create User class with CRUD operations",
      "priority": 2,
      "task_type": "task",
      "category": "code",
      "validation": "Unit tests pass for User model",
      "depends_on": [0]
    }
  ]
}
```

### Rules
1. Order subtasks logically — dependencies before dependents
2. Use `depends_on` with 0-based indices referring to earlier subtasks
3. Output ONLY valid JSON — no markdown, no explanation

Return the JSON now.
