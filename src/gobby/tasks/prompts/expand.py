"""
Expansion Prompt Builder.

Handles the construction of system and user prompts for task expansion,
instructing the agent to use create_task MCP tool calls instead of JSON output.
"""

from gobby.config.app import TaskExpansionConfig
from gobby.storage.tasks import Task
from gobby.tasks.context import ExpansionContext

# Default System Prompt (Tool-based expansion)
DEFAULT_SYSTEM_PROMPT = """You are a senior technical project manager and architect.
Your goal is to break down a high-level task into clear, actionable, and atomic subtasks.

## Available Tool

You have access to the `create_task` MCP tool to create subtasks. Use it for each subtask you generate.

### create_task Parameters

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| title | string | Yes | Short, actionable title for the subtask |
| description | string | No | Detailed description including implementation notes |
| priority | integer | No | 1=High, 2=Medium (default), 3=Low |
| task_type | string | No | "task" (default), "bug", "feature", "epic" |
| parent_task_id | string | No | ID of the parent task (provided in context) |
| blocks | array[string] | No | List of task IDs that this task blocks |
| labels | array[string] | No | Labels for categorization |

### Linking Subtasks to Parent

Always set `parent_task_id` to the parent task ID provided in the context. This creates the parent-child relationship.

### Wiring Dependencies with `blocks`

When a subtask must complete before another can start, use the `blocks` parameter:

1. Create the blocking task first (the one that must complete first)
2. Note its returned task ID
3. When creating the dependent task, pass the blocker's ID in the `blocks` array

Example sequence:
```
# Step 1: Create foundation task (returns {"id": "gt-abc123"})
create_task(title="Create database schema", parent_task_id="gt-parent")

# Step 2: Create dependent task, blocked by Step 1
create_task(title="Implement data access layer", parent_task_id="gt-parent", blocks=["gt-abc123"])
```

The `blocks` parameter means "this new task blocks the listed task IDs" - so if task B depends on task A,
you create A first, then create B with `blocks=[A.id]`.

### Setting Test Strategy

Include test strategy in the description field. Structure descriptions as:

```
<implementation details>

**Test Strategy:** <how to verify this subtask is complete>
```

Every coding subtask MUST have a test strategy section in its description.

## Rules

1. **Atomicity**: Each subtask should be small enough to be completed in one session (10-30 mins of work).
2. **Dependencies**: Use `blocks` to enforce logical order (e.g., create file before importing it).
3. **Context Awareness**: Reference specific existing files or functions from the provided codebase context.
4. **Testing**: Every coding subtask MUST have a test strategy in its description.
5. **Completeness**: The set of subtasks must fully accomplish the parent task.
6. **Order**: Create subtasks in logical execution order - blockers before dependents.

## Phases (Optional)

You may organize subtasks into logical phases, but this is for your planning only.
Create all subtasks using the tool - do not output JSON or markdown lists.
"""

# TDD Mode Addition
TDD_MODE_INSTRUCTIONS = """

## TDD Mode Enabled

For Test-Driven Development, create subtasks in test->implement pairs:

1. **Test subtask**: "Write tests for <feature>"
   - Description explains what tests to write
   - Test strategy: "Tests should fail initially (red phase)"

2. **Implementation subtask**: "Implement <feature>"
   - Set `blocks` to the test subtask's ID
   - Description explains minimal implementation to pass tests
   - Test strategy: "All tests from previous subtask should pass (green phase)"

Example TDD sequence:
```
# Create test task first (returns {"id": "gt-test1"})
create_task(
    title="Write tests for user authentication",
    description="Write failing tests for login, logout, and session management.\\n\\n**Test Strategy:** Tests should fail initially (red phase)",
    parent_task_id="gt-parent"
)

# Implementation task blocks the test task
create_task(
    title="Implement user authentication",
    description="Write minimal code to make authentication tests pass.\\n\\n**Test Strategy:** All authentication tests should pass (green phase)",
    parent_task_id="gt-parent",
    blocks=["gt-test1"]
)
```

This ensures tests are written first and implementation follows.
"""

# Default User Prompt Template
DEFAULT_USER_PROMPT = """Analyze and expand this task into subtasks using the create_task tool.

## Parent Task
- **ID**: {task_id}
- **Title**: {title}
- **Description**: {description}

## Context
{context_str}

## Research Findings
{research_str}

## Instructions

Use the create_task tool to create each subtask. Remember to:
1. Set `parent_task_id` to "{task_id}" for all subtasks
2. Use `blocks` parameter to wire dependencies between subtasks
3. Include test strategy in each subtask's description
4. Create subtasks in dependency order (blockers first)

Begin creating subtasks now."""


class ExpansionPromptBuilder:
    """Builds prompts for task expansion."""

    def __init__(self, config: TaskExpansionConfig):
        self.config = config

    def get_system_prompt(self, tdd_mode: bool = False) -> str:
        """
        Get the system prompt (from config or default).

        Args:
            tdd_mode: If True, append TDD-specific instructions.
        """
        base_prompt = self.config.system_prompt or DEFAULT_SYSTEM_PROMPT

        if tdd_mode:
            base_prompt += TDD_MODE_INSTRUCTIONS

        return base_prompt

    def build_user_prompt(
        self,
        task: Task,
        context: ExpansionContext,
        user_instructions: str | None = None,
    ) -> str:
        """
        Build the user prompt by injecting context into the template.
        """
        template = self.config.prompt or DEFAULT_USER_PROMPT

        # Format context string
        context_parts = []
        if context.relevant_files:
            context_parts.append("**Relevant Files:**")
            for f in context.relevant_files:
                context_parts.append(f"- {f}")

        if context.project_patterns:
            context_parts.append("\n**Project Patterns:**")
            for k, v in context.project_patterns.items():
                context_parts.append(f"- {k}: {v}")

        if context.related_tasks:
            context_parts.append("\n**Related Tasks:**")
            for t in context.related_tasks:
                context_parts.append(f"- {t.title} ({t.status})")

        context_str = "\n".join(context_parts) if context_parts else "No additional context available."

        # Format research findings
        research_str = context.agent_findings or "No research performed."

        # Inject into template
        prompt = template.format(
            task_id=task.id,
            title=task.title,
            description=task.description or "",
            context_str=context_str,
            research_str=research_str,
        )

        # Append specific user instructions if provided
        if user_instructions:
            prompt += f"\n\n## Additional Instructions\n{user_instructions}"

        return prompt
