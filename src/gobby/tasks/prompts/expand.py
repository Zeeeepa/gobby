"""
Expansion Prompt Builder.

Handles the construction of system and user prompts for task expansion,
injecting dynamic context (files, related tasks, research results) into templates.
"""

from typing import Any

from gobby.config.app import TaskExpansionConfig
from gobby.storage.tasks import Task
from gobby.tasks.context import ExpansionContext

# Default System Prompt (Schema & Behavior)
DEFAULT_SYSTEM_PROMPT = """You are a senior technical project manager and architect.
Your goal is to break down a high-level task into clear, actionable, and atomic subtasks.

### Output Schema
You MUST output valid JSON matching this schema:

{
  "complexity_analysis": {
    "score": <1-10>,
    "reasoning": "<brief explanation>",
    "recommended_subtasks": <integer>
  },
  "phases": [
    {
      "name": "<Phase Name>",
      "description": "<Phase Goal>",
      "subtasks": [
        {
          "title": "<Actionable Title>",
          "description": "<What to do>",
          "details": "<Implementation notes, specific files to edit, patterns to use>",
          "test_strategy": "<How to verify this subtask>",
          "depends_on_indices": [<integers of subtasks in THIS expansion that must finish first>],
          "files_touched": ["<list of filenames>"]
        }
      ]
    }
  ]
}

### Rules
1. **Atomicity**: Each subtask should be small enough to be completed in one session (10-30 mins).
2. **Dependencies**: Use `depends_on_indices` to enforce logical order (e.g. create file before importing it). Indices are 0-based within the flattened list of all subtasks generated.
3. **Context Awareness**: Use the provided codebase context to mention specific existing files or functions.
4. **Testing**: Every coding subtask MUST have a `test_strategy`.
5. **Completeness**: The set of subtasks must fully accomplish the parent task.
"""

# Default User Prompt Template
DEFAULT_USER_PROMPT = """Analyze and expand this task:

Task: {title}
Description: {description}

### Context
{context_str}

### Research Findings
{research_str}

Break this down into phases and subtasks."""


class ExpansionPromptBuilder:
    """Builds prompts for task expansion."""

    def __init__(self, config: TaskExpansionConfig):
        self.config = config

    def get_system_prompt(self) -> str:
        """Get the system prompt (from config or default)."""
        return self.config.system_prompt or DEFAULT_SYSTEM_PROMPT

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
            context_parts.append("Relevant Files:")
            for f in context.relevant_files:
                context_parts.append(f"- {f}")

        if context.project_patterns:
            context_parts.append("\nProject Patterns:")
            for k, v in context.project_patterns.items():
                context_parts.append(f"- {k}: {v}")

        if context.related_tasks:
            context_parts.append("\nRelated Tasks:")
            for t in context.related_tasks:
                context_parts.append(f"- {t.title} ({t.status})")

        context_str = "\n".join(context_parts)

        # Format research findings
        research_str = context.agent_findings or "No research performed."

        # Inject into template
        prompt = template.format(
            title=task.title,
            description=task.description or "",
            context_str=context_str,
            research_str=research_str,
        )

        # Append specific user instructions if provided
        if user_instructions:
            prompt += f"\n\nAdditional Instructions:\n{user_instructions}"

        return prompt

    def get_output_schema(self) -> dict[str, Any]:
        """Return the JSON schema for validation/documentation."""
        return {
            "type": "object",
            "properties": {
                "complexity_analysis": {
                    "type": "object",
                    "properties": {
                        "score": {"type": "integer", "minimum": 1, "maximum": 10},
                        "reasoning": {"type": "string"},
                        "recommended_subtasks": {"type": "integer"},
                    },
                    "required": ["score", "reasoning"],
                },
                "phases": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "subtasks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string"},
                                        "description": {"type": "string"},
                                        "details": {"type": "string"},
                                        "test_strategy": {"type": "string"},
                                        "depends_on_indices": {
                                            "type": "array",
                                            "items": {"type": "integer"},
                                        },
                                        "files_touched": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                    "required": ["title", "description"],
                                },
                            },
                        },
                        "required": ["name", "subtasks"],
                    },
                },
            },
            "required": ["complexity_analysis", "phases"],
        }
