"""
Expansion Prompt Builder.

Handles the construction of system and user prompts for task expansion,
instructing the agent to return structured JSON for subtask creation.
"""

from gobby.config.app import TaskExpansionConfig
from gobby.storage.tasks import Task
from gobby.tasks.context import ExpansionContext

# JSON Schema for subtask output
SUBTASK_SCHEMA = """
{
  "subtasks": [
    {
      "title": "string (required) - Short, actionable title",
      "description": "string (optional) - Detailed description with implementation notes",
      "priority": "integer (optional) - 1=High, 2=Medium (default), 3=Low",
      "task_type": "string (optional) - task|bug|feature|epic (default: task)",
      "test_strategy": "string (optional) - How to verify completion",
      "depends_on": ["integer (optional) - Array of 0-based indices of subtasks this depends on"]
    }
  ]
}
"""

# Default System Prompt (Structured JSON output)
DEFAULT_SYSTEM_PROMPT = """You are a senior technical project manager and architect.
Your goal is to break down a high-level task into clear, actionable, and atomic subtasks.

## Output Format

You MUST respond with a JSON object containing a "subtasks" array. Each subtask has:

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| title | string | Yes | Short, actionable title for the subtask |
| description | string | No | Detailed description including implementation notes |
| priority | integer | No | 1=High, 2=Medium (default), 3=Low |
| task_type | string | No | "task" (default), "bug", "feature", "epic" |
| test_strategy | string | No | How to verify this subtask is complete |
| depends_on | array[int] | No | Indices (0-based) of subtasks this one depends on |

## Example Output

```json
{
  "subtasks": [
    {
      "title": "Create database schema",
      "description": "Define tables for users, sessions, and permissions",
      "priority": 1,
      "test_strategy": "Run migrations and verify tables exist"
    },
    {
      "title": "Implement data access layer",
      "description": "Create repository classes for CRUD operations",
      "depends_on": [0],
      "test_strategy": "Unit tests for all repository methods pass"
    },
    {
      "title": "Add API endpoints",
      "description": "REST endpoints for user management",
      "depends_on": [1],
      "test_strategy": "Integration tests for all endpoints pass"
    }
  ]
}
```

## Dependency System

Use `depends_on` to specify execution order:
- Reference subtasks by their 0-based index in the array
- A subtask with `depends_on: [0, 2]` requires subtasks 0 and 2 to complete first
- Order your array logically - dependencies should come before dependents

## Rules

1. **Atomicity**: Each subtask should be small enough to be completed in one session (10-30 mins of work).
2. **Dependencies**: Use `depends_on` to enforce logical order (e.g., create file before importing it).
3. **Context Awareness**: Reference specific existing files or functions from the provided codebase context.
4. **Testing**: Every coding subtask MUST have a test_strategy.
5. **Completeness**: The set of subtasks must fully accomplish the parent task.
6. **JSON Only**: Output ONLY valid JSON - no markdown, no explanation, no code blocks.
"""

# TDD Mode Addition
TDD_MODE_INSTRUCTIONS = """

## TDD Mode Enabled

**IMPORTANT:** Apply TDD only to coding/implementation tasks. For non-coding tasks (documentation, design, research, planning, configuration), use normal task structure without test pairs.

For coding tasks, create subtasks in test->implement pairs:

1. **Test subtask**: "Write tests for <feature>"
   - Description explains what tests to write
   - Test strategy: "Tests should fail initially (red phase)"

2. **Implementation subtask**: "Implement <feature>"
   - Set `depends_on` to reference the test subtask's index
   - Description explains minimal implementation to pass tests
   - Test strategy: "All tests from previous subtask should pass (green phase)"

Example TDD output:
```json
{
  "subtasks": [
    {
      "title": "Write tests for user authentication",
      "description": "Write failing tests for login, logout, and session management.",
      "test_strategy": "Tests should fail initially (red phase)"
    },
    {
      "title": "Implement user authentication",
      "description": "Write minimal code to make authentication tests pass.",
      "depends_on": [0],
      "test_strategy": "All authentication tests should pass (green phase)"
    }
  ]
}
```

This ensures tests are written first and implementation follows.
"""

# Default User Prompt Template
DEFAULT_USER_PROMPT = """Analyze and expand this task into subtasks.

## Parent Task
- **ID**: {task_id}
- **Title**: {title}
- **Description**: {description}

## Context
{context_str}

## Research Findings
{research_str}

## Instructions

Return a JSON object with a "subtasks" array. Remember to:
1. Use `depends_on` with 0-based indices to specify dependencies
2. Include a test_strategy for each coding subtask
3. Order subtasks logically - dependencies before dependents
4. Output ONLY valid JSON - no markdown, no explanation

Return the JSON now."""


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
            tdd_instructions = self.config.tdd_prompt or TDD_MODE_INSTRUCTIONS
            base_prompt += tdd_instructions

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

        if context.existing_tests:
            context_parts.append("\n**Existing Tests:**")
            for module, test_files in context.existing_tests.items():
                context_parts.append(f"- {module}:")
                for tf in test_files:
                    context_parts.append(f"  - {tf}")
            context_parts.append(
                "\n*Note: When creating test tasks for modules with existing tests, "
                "update the existing test files rather than creating new ones.*"
            )

        if context.function_signatures:
            context_parts.append("\n**Functions Being Modified:**")
            for file_path, signatures in context.function_signatures.items():
                context_parts.append(f"- {file_path}:")
                for sig in signatures:
                    context_parts.append(f"  - `{sig}`")
            context_parts.append(
                "\n*Note: Reference these signatures in validation criteria "
                "to ensure functions are preserved or properly refactored.*"
            )

        if context.project_patterns:
            context_parts.append("\n**Project Patterns:**")
            for k, v in context.project_patterns.items():
                context_parts.append(f"- {k}: {v}")

        if context.related_tasks:
            context_parts.append("\n**Related Tasks:**")
            for t in context.related_tasks:
                context_parts.append(f"- {t.title} ({t.status})")

        context_str = (
            "\n".join(context_parts) if context_parts else "No additional context available."
        )

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
