"""
Expansion Prompt Builder.

Handles the construction of system and user prompts for task expansion,
instructing the agent to return structured JSON for subtask creation.
"""

import logging
from pathlib import Path

from gobby.config.app import TaskExpansionConfig
from gobby.prompts import PromptLoader
from gobby.storage.tasks import Task
from gobby.tasks.context import ExpansionContext

logger = logging.getLogger(__name__)

# JSON Schema for subtask output
SUBTASK_SCHEMA = """
{
  "subtasks": [
    {
      "title": "string (required) - Short, actionable title",
      "description": "string (optional) - Detailed description with implementation notes",
      "priority": "integer (optional) - 1=High, 2=Medium (default), 3=Low",
      "task_type": "string (optional) - task|bug|feature|epic (default: task)",
      "category": "string (required for actionable tasks) - code|config|docs|test|research|planning|manual",
      "validation": "string (optional) - Acceptance criteria with project commands",
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
| category | string | Yes* | Task domain: code, config, docs, test, research, planning, manual |
| validation | string | No | Acceptance criteria with project commands |
| depends_on | array[int] | No | Indices (0-based) of subtasks this one depends on |

*Required for actionable tasks. Use "planning" for epic/phase tasks.

## Category Values

Choose the appropriate category for each subtask:
- **code**: Implementation tasks (write/modify source code)
- **config**: Configuration file changes (.yaml, .toml, .json, .env)
- **docs**: Documentation tasks (README, docstrings, guides)
- **test**: Test-writing tasks (unit tests, integration tests)
- **research**: Investigation/exploration tasks
- **planning**: Design/architecture tasks, parent phases
- **manual**: Manual verification/testing tasks

## Example Output

```json
{
  "subtasks": [
    {
      "title": "Create database schema",
      "description": "Define tables for users, sessions, and permissions",
      "priority": 1,
      "category": "code",
      "validation": "Run migrations and verify tables exist with `{unit_tests}`"
    },
    {
      "title": "Implement data access layer",
      "description": "Create repository classes for CRUD operations",
      "depends_on": [0],
      "category": "code",
      "validation": "Unit tests for all repository methods pass"
    },
    {
      "title": "Add API endpoints",
      "description": "REST endpoints for user management",
      "depends_on": [1],
      "category": "code",
      "validation": "Integration tests for all endpoints pass"
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
4. **Categories Required**: Every actionable subtask MUST have a category from the enum.
5. **Validation Criteria**: Include validation criteria for code/config/test tasks.
6. **Completeness**: The set of subtasks must fully accomplish the parent task.
7. **JSON Only**: Output ONLY valid JSON - no markdown, no explanation, no code blocks.
8. **No Scope Creep**: Do NOT include optional features, alternatives, or "nice-to-haves". Each subtask must be a concrete requirement from the parent task. Never invent additional features, suggest "consider also adding X", or include "(Optional)" sections. Implement exactly what is specified.

## Validation Criteria Rules

For each subtask, generate PRECISE validation criteria in the `validation` field.
Use the project's verification commands (provided in context) rather than hardcoded commands.

### 1. Measurable
Use exact commands from project context, not vague descriptions.

| BAD (Vague) | GOOD (Measurable) |
|-------------|-------------------|
| "Tests pass" | "`{unit_tests}` exits with code 0" |
| "No type errors" | "`{type_check}` reports no errors" |
| "Linting passes" | "`{lint}` exits with code 0" |

### 2. Specific
Reference actual files and functions from the provided context.

| BAD (Generic) | GOOD (Specific) |
|---------------|-----------------|
| "Function moved correctly" | "`ClassName` exists in `path/to/new/file.ext` with same signature" |
| "Tests updated" | "`tests/module/test_file.ext` imports from new location" |
| "Config added" | "`ConfigName` in `path/to/config.ext` has required fields" |

### 3. Verifiable
Include commands that can be executed to verify completion.

| BAD (Unverifiable) | GOOD (Verifiable) |
|--------------------|-------------------|
| "No regressions" | "No test files removed: `git diff --name-only HEAD~1 | grep -v test`" |
| "Module importable" | "Import succeeds without errors in project's runtime" |
| "File created" | "File exists at expected path with expected exports" |

**Important:** Replace `{unit_tests}`, `{type_check}`, `{lint}` with actual commands from the Project Verification Commands section in the context.
"""

# NOTE: TDD_MODE_INSTRUCTIONS removed - TDD is now applied automatically post-expansion
# by _apply_tdd_sandwich() in task_expansion.py for non-epic code/config tasks

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
2. Include a category for each coding subtask
3. Order subtasks logically - dependencies before dependents
4. Output ONLY valid JSON - no markdown, no explanation

Return the JSON now."""


class ExpansionPromptBuilder:
    """Builds prompts for task expansion."""

    def __init__(self, config: TaskExpansionConfig, project_dir: Path | None = None):
        self.config = config
        self._loader = PromptLoader(project_dir=project_dir)

        # Register fallbacks for strangler fig pattern
        # NOTE: TDD is applied post-expansion, not in prompt
        self._loader.register_fallback("expansion/system", lambda: DEFAULT_SYSTEM_PROMPT)
        self._loader.register_fallback("expansion/user", lambda: DEFAULT_USER_PROMPT)

    def get_system_prompt(self, tdd_mode: bool = False) -> str:
        """
        Get the system prompt (from config, template file, or default).

        Precedence order:
        1. Inline config (deprecated): config.system_prompt
        2. Config path: config.system_prompt_path
        3. Template file: expansion/system.md
        4. Python constant fallback: DEFAULT_SYSTEM_PROMPT

        Args:
            tdd_mode: Deprecated, ignored. TDD is now applied post-expansion.
        """
        # 1. Inline config (deprecated, for backwards compatibility)
        if self.config.system_prompt:
            return self.config.system_prompt

        # 2. Config path or 3. Template file
        prompt_path = self.config.system_prompt_path or "expansion/system"

        try:
            # Pass empty context - tdd_mode no longer used in templates
            return self._loader.render(prompt_path, {})
        except FileNotFoundError:
            logger.debug(f"Prompt template '{prompt_path}' not found, using fallback")
            # 4. Python constant fallback
            return DEFAULT_SYSTEM_PROMPT

    def build_user_prompt(
        self,
        task: Task,
        context: ExpansionContext,
        user_instructions: str | None = None,
    ) -> str:
        """
        Build the user prompt by injecting context into the template.

        Precedence order:
        1. Inline config (deprecated): config.prompt
        2. Config path: config.prompt_path
        3. Template file: expansion/user.md
        4. Python constant fallback: DEFAULT_USER_PROMPT
        """
        # Check if using inline config (deprecated)
        use_legacy_template = self.config.prompt is not None

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

        if context.verification_commands:
            context_parts.append("\n**Project Verification Commands:**")
            context_parts.append("Use these commands in validation criteria:")
            for name, cmd in context.verification_commands.items():
                context_parts.append(f"- `{{{name}}}` = `{cmd}`")

        if context.project_patterns:
            context_parts.append("\n**Project Patterns:**")
            for k, v in context.project_patterns.items():
                context_parts.append(f"- {k}: {v}")

        if context.related_tasks:
            context_parts.append("\n**Related Tasks:**")
            for t in context.related_tasks:
                context_parts.append(f"- {t.title} ({t.status})")

        if context.project_structure:
            context_parts.append("\n**Project Structure:**")
            context_parts.append(context.project_structure)
            context_parts.append(
                "\n*IMPORTANT: Use these actual paths when referencing files. "
                "Do NOT invent paths like 'gt/core/' or 'lib/utils/' - only use paths shown above.*"
            )

        context_str = (
            "\n".join(context_parts) if context_parts else "No additional context available."
        )

        # Format research findings
        research_str = context.agent_findings or "No research performed."

        # Build context for template rendering
        template_context = {
            "task_id": task.id,
            "title": task.title,
            "description": task.description or "",
            "context_str": context_str,
            "research_str": research_str,
        }

        # Render using appropriate method
        if use_legacy_template:
            # 1. Inline config (deprecated)
            template = self.config.prompt or DEFAULT_USER_PROMPT
            prompt = template.format(**template_context)
        else:
            # 2. Config path or 3. Template file
            prompt_path = self.config.prompt_path or "expansion/user"
            try:
                prompt = self._loader.render(prompt_path, template_context)
            except FileNotFoundError:
                logger.debug(f"Prompt template '{prompt_path}' not found, using fallback")
                # 4. Python constant fallback
                prompt = DEFAULT_USER_PROMPT.format(**template_context)

        # Append specific user instructions if provided
        if user_instructions:
            prompt += f"\n\n## Additional Instructions\n{user_instructions}"

        return prompt
