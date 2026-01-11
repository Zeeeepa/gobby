---
description: This skill should be used when the user asks to "/tasks", "task management", "create task", "list tasks", "close task". Manage gobby tasks - create, list, close, expand, suggest, validate, and show tasks.
version: "1.0"
---

# /tasks - Task Management Skill

This skill manages tasks via the gobby-tasks MCP server. Parse the user's input to determine which subcommand to execute.

## Subcommands

### `/tasks create <title>` - Create a new task
Call `gobby-tasks.create_task` with:
- `title`: The task title from user input
- `task_type`: Default to "task" unless user specifies (task, bug, feature, epic)
- `description`: Optional, include if user provides additional context

Example: `/tasks create Fix login button` → `create_task(title="Fix login button", task_type="task")`

### `/tasks list [status]` - List tasks
Call `gobby-tasks.list_tasks` with:
- `status`: Optional filter (open, in_progress, closed). If not provided, list all open tasks.

Example: `/tasks list in_progress` → `list_tasks(status="in_progress")`
Example: `/tasks list` → `list_tasks(status="open")`

### `/tasks close <task-id>` - Close/complete a task
Call `gobby-tasks.close_task` with:
- `task_id`: The task ID (e.g., gt-abc123)
- `commit_sha`: Get from latest commit if work was committed
- `no_commit_needed`: Set to true only if task required no code changes

**IMPORTANT**: Always commit changes first, then close with the commit SHA.

Example: `/tasks close gt-abc123` → First commit, then `close_task(task_id="gt-abc123", commit_sha="<sha>")`

### `/tasks expand <task-id>` - Expand task into subtasks
Call `gobby-tasks.expand_task` with:
- `task_id`: The task ID to expand

This uses AI to break down the task into actionable subtasks.

Example: `/tasks expand gt-abc123` → `expand_task(task_id="gt-abc123")`

### `/tasks suggest` - Get AI-suggested next task
Call `gobby-tasks.suggest_next_task` with:
- `parent_id`: Optional, scope to specific epic/feature
- `prefer_subtasks`: Default true, prefer leaf tasks

Returns the highest-priority ready task to work on.

Example: `/tasks suggest` → `suggest_next_task()`

### `/tasks validate <task-id>` - Validate task completion
Call `gobby-tasks.validate_task` with:
- `task_id`: The task ID to validate

Runs validation against the task's validation_criteria.

Example: `/tasks validate gt-abc123` → `validate_task(task_id="gt-abc123")`

### `/tasks show <task-id>` - Show task details
Call `gobby-tasks.get_task` with:
- `task_id`: The task ID to show

Displays full task details including description, status, validation criteria, test strategy, etc.

Example: `/tasks show gt-abc123` → `get_task(task_id="gt-abc123")`

## Response Format

After executing the appropriate MCP tool, present the results clearly:
- For create: Show the new task ID and title
- For list: Format as a table or list with ID, title, status, priority
- For close: Confirm closure with task ID
- For expand: List the created subtasks
- For suggest: Show the suggested task with reasoning
- For validate: Show validation result (pass/fail) with feedback
- For show: Display all task fields in a readable format

## Error Handling

If the subcommand is not recognized, show available subcommands:
- create, list, close, expand, suggest, validate, show
