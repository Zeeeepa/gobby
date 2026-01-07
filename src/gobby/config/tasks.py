"""
Task management configuration module.

Contains task-related Pydantic config models:
- CompactHandoffConfig: Compact handoff context configuration
- PatternCriteriaConfig: Pattern-specific validation criteria templates
- TaskExpansionConfig: Task breakdown/expansion settings
- TaskValidationConfig: Task completion validation settings
- GobbyTasksConfig: Combined gobby-tasks MCP server config
- WorkflowConfig: Workflow engine configuration

Extracted from app.py using Strangler Fig pattern for code decomposition.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "CompactHandoffConfig",
    "PatternCriteriaConfig",
    "TaskExpansionConfig",
    "TaskValidationConfig",
    "GobbyTasksConfig",
    "WorkflowConfig",
]


class CompactHandoffConfig(BaseModel):
    """Compact handoff context configuration for /compact command."""

    enabled: bool = Field(
        default=True,
        description="Enable compact handoff context extraction and injection",
    )
    # DEPRECATED: prompt field is no longer used.
    # Template is now defined in session-handoff.yaml workflow file.
    # Kept for backwards compatibility but will be removed in a future version.
    prompt: str | None = Field(
        default=None,
        description="DEPRECATED: Template moved to session-handoff.yaml workflow. "
        "This field is ignored.",
    )


class PatternCriteriaConfig(BaseModel):
    """Configuration for pattern-specific validation criteria templates.

    Defines validation criteria templates for common development patterns like
    strangler-fig, TDD, and refactoring. Templates can use placeholders that
    get replaced with actual values from project verification config.

    Placeholders:
    - {unit_tests}: Unit test command from project verification
    - {type_check}: Type check command from project verification
    - {lint}: Lint command from project verification
    - {original_module}, {new_module}, {function}, {original_file}: For strangler-fig pattern
    """

    patterns: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "strangler-fig": [
                "Original import still works: `from {original_module} import {function}`",
                "New import works: `from {new_module} import {function}`",
                "Delegation exists: `grep -c 'from .{new_module} import' {original_file}` >= 1",
                "No circular imports: `python -c 'from {original_module} import *'`",
            ],
            "tdd": [
                "Tests written before implementation (verify git log order)",
                "Tests initially fail (red phase)",
                "Implementation makes tests pass (green phase)",
            ],
            "refactoring": [
                "All existing tests pass: `{unit_tests}`",
                "No new type errors: `{type_check}`",
                "No lint violations: `{lint}`",
            ],
        },
        description="Pattern name to list of validation criteria templates. "
        "Templates can use placeholders like {unit_tests}, {type_check}, {lint}.",
    )
    detection_keywords: dict[str, list[str]] = Field(
        default_factory=lambda: {
            "strangler-fig": ["strangler fig", "strangler-fig", "strangler pattern", "delegation pattern"],
            "tdd": ["tdd", "test-driven", "test driven", "red-green", "red green"],
            "refactoring": ["refactor", "refactoring", "restructure", "reorganize"],
        },
        description="Pattern name to list of keywords that trigger pattern detection in task descriptions.",
    )


class TaskExpansionConfig(BaseModel):
    """Configuration for task expansion (breaking down broad tasks/epics)."""

    enabled: bool = Field(
        default=True,
        description="Enable automated task expansion",
    )
    provider: str = Field(
        default="claude",
        description="LLM provider to use for expansion",
    )
    model: str = Field(
        default="claude-opus-4-5",
        description="Model to use for expansion",
    )
    prompt: str | None = Field(
        default=None,
        description="Custom prompt template for task expansion",
    )
    codebase_research_enabled: bool = Field(
        default=True,
        description="Enable agentic codebase research for context gathering",
    )
    research_model: str | None = Field(
        default=None,
        description="Model to use for research agent (defaults to expansion model if None)",
    )
    research_max_steps: int = Field(
        default=10,
        description="Maximum number of steps for research agent loop",
    )
    research_system_prompt: str = Field(
        default="You are a senior developer researching a codebase. Use tools to find relevant code.",
        description="System prompt for the research agent",
    )
    system_prompt: str | None = Field(
        default=None,
        description="Custom system prompt for task expansion (overrides default in expand.py)",
    )
    tdd_prompt: str | None = Field(
        default=None,
        description="TDD mode instructions appended to system prompt when tdd_mode is enabled (overrides default in expand.py)",
    )
    web_research_enabled: bool = Field(
        default=True,
        description="Enable web research for task expansion using MCP tools",
    )
    tdd_mode: bool = Field(
        default=True,
        description="Enable TDD mode: create test->implement task pairs with appropriate blocking for coding tasks",
    )
    max_subtasks: int = Field(
        default=15,
        description="Maximum number of subtasks to create per expansion",
    )
    default_strategy: Literal["auto", "phased", "sequential", "parallel"] = Field(
        default="auto",
        description="Default expansion strategy: auto (LLM decides), phased, sequential, or parallel",
    )
    timeout: float = Field(
        default=300.0,
        description="Maximum time in seconds for entire task expansion (default: 5 minutes)",
    )
    research_timeout: float = Field(
        default=60.0,
        description="Maximum time in seconds for research phase (default: 60 seconds)",
    )
    pattern_criteria: PatternCriteriaConfig = Field(
        default_factory=PatternCriteriaConfig,
        description="Pattern-specific validation criteria templates",
    )


class TaskValidationConfig(BaseModel):
    """Configuration for task validation (checking completion against criteria)."""

    enabled: bool = Field(
        default=True,
        description="Enable automated task validation",
    )
    provider: str = Field(
        default="claude",
        description="LLM provider to use for validation",
    )
    model: str = Field(
        default="claude-haiku-4-5",
        description="Model to use for validation",
    )
    system_prompt: str = Field(
        default="You are a QA validator. Output ONLY valid JSON. No markdown, no explanation, no code blocks. Just the raw JSON object.",
        description="System prompt for task validation",
    )
    prompt: str | None = Field(
        default=None,
        description="Custom prompt template for task validation (use {title}, {criteria_text}, {changes_section} placeholders)",
    )
    criteria_system_prompt: str = Field(
        default="You are a QA engineer writing acceptance criteria. CRITICAL: Only include requirements explicitly stated in the task. Do NOT invent specific values, thresholds, timeouts, or edge cases that aren't mentioned. Vague tasks get vague criteria. Use markdown checkboxes.",
        description="System prompt for generating validation criteria",
    )
    criteria_prompt: str | None = Field(
        default=None,
        description="Custom prompt template for generating validation criteria (use {title}, {description} placeholders)",
    )
    # Validation loop control
    max_iterations: int = Field(
        default=10,
        description="Maximum validation attempts before escalation",
    )
    max_consecutive_errors: int = Field(
        default=3,
        description="Max consecutive errors before stopping validation loop",
    )
    recurring_issue_threshold: int = Field(
        default=3,
        description="Number of times same issue can recur before escalation",
    )
    issue_similarity_threshold: float = Field(
        default=0.8,
        description="Similarity threshold (0-1) for detecting recurring issues",
    )
    # Build verification
    run_build_first: bool = Field(
        default=True,
        description="Run build/test command before LLM validation",
    )
    build_command: str | None = Field(
        default=None,
        description="Custom build command (auto-detected if None: npm test, pytest, etc.)",
    )
    # External validator
    use_external_validator: bool = Field(
        default=False,
        description="Use external LLM for validation (different from task agent)",
    )
    external_validator_model: str | None = Field(
        default=None,
        description="Model for external validation (defaults to validation.model)",
    )
    # Escalation settings
    escalation_enabled: bool = Field(
        default=True,
        description="Enable task escalation on repeated validation failures",
    )
    escalation_notify: Literal["webhook", "slack", "none"] = Field(
        default="none",
        description="Notification method when task is escalated",
    )
    escalation_webhook_url: str | None = Field(
        default=None,
        description="Webhook URL for escalation notifications",
    )
    # Auto-generation settings
    auto_generate_on_create: bool = Field(
        default=True,
        description="Auto-generate validation criteria when creating tasks via create_task",
    )
    auto_generate_on_expand: bool = Field(
        default=True,
        description="Auto-generate validation criteria when expanding tasks via expand_task",
    )

    @field_validator("max_iterations", "max_consecutive_errors", "recurring_issue_threshold")
    @classmethod
    def validate_positive_int(cls, v: int) -> int:
        """Validate value is positive."""
        if v <= 0:
            raise ValueError("Value must be positive")
        return v

    @field_validator("issue_similarity_threshold")
    @classmethod
    def validate_threshold(cls, v: float) -> float:
        """Validate threshold is between 0 and 1."""
        if not 0 <= v <= 1:
            raise ValueError("issue_similarity_threshold must be between 0 and 1")
        return v


class GobbyTasksConfig(BaseModel):
    """Configuration for gobby-tasks internal MCP server."""

    model_config = {"populate_by_name": True}

    enabled: bool = Field(
        default=True,
        description="Enable gobby-tasks internal MCP server",
    )
    show_result_on_create: bool = Field(
        default=False,
        description="Show full task result on create_task (False = minimal output with just id)",
    )
    expansion: TaskExpansionConfig = Field(
        default_factory=lambda: TaskExpansionConfig(),
        description="Task expansion configuration",
    )
    validation: TaskValidationConfig = Field(
        default_factory=lambda: TaskValidationConfig(),
        description="Task validation configuration",
    )


class WorkflowConfig(BaseModel):
    """Workflow engine configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable workflow engine",
    )
    timeout: float = Field(
        default=0.0,
        description="Timeout in seconds for workflow execution. 0 = no timeout (default)",
    )
    require_task_before_edit: bool = Field(
        default=False,
        description="Require an active gobby-task (in_progress) before allowing Edit/Write tools",
    )
    protected_tools: list[str] = Field(
        default_factory=lambda: ["Edit", "Write", "NotebookEdit"],
        description="Tools that require an active task when require_task_before_edit is enabled",
    )

    @field_validator("timeout")
    @classmethod
    def validate_timeout(cls, v: float) -> float:
        """Validate timeout is non-negative."""
        if v < 0:
            raise ValueError("Timeout must be non-negative (0 = no timeout)")
        return v
