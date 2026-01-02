from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

# --- Workflow Definition Models (YAML) ---


class WorkflowRule(BaseModel):
    name: str | None = None
    when: str
    action: Literal["block", "allow", "require_approval", "warn"]
    message: str | None = None


class WorkflowTransition(BaseModel):
    to: str
    when: str
    on_transition: list[dict[str, Any]] = Field(default_factory=list)


class WorkflowExitCondition(BaseModel):
    type: str

    # Other fields depend on type (e.g. pattern, prompt, variable)
    model_config = ConfigDict(extra="allow")


class WorkflowStep(BaseModel):
    name: str
    description: str | None = None

    on_enter: list[dict[str, Any]] = Field(default_factory=list)

    # "all" or list of tool names
    allowed_tools: list[str] | Literal["all"] = Field(default="all")
    blocked_tools: list[str] = Field(default_factory=list)

    rules: list[WorkflowRule] = Field(default_factory=list)
    transitions: list[WorkflowTransition] = Field(default_factory=list)
    exit_conditions: list[dict[str, Any]] = Field(default_factory=list)  # flexible for now

    on_exit: list[dict[str, Any]] = Field(default_factory=list)


# Backward compatibility alias
WorkflowPhase = WorkflowStep


class WorkflowDefinition(BaseModel):
    name: str
    description: str | None = None
    version: str = "1.0"
    type: Literal["lifecycle", "phase"] = "phase"
    extends: str | None = None

    @field_validator("version", mode="before")
    @classmethod
    def coerce_version_to_string(cls, v: Any) -> str:
        """Accept numeric versions (1.0, 2) and coerce to string."""
        return str(v) if v is not None else "1.0"

    settings: dict[str, Any] = Field(default_factory=dict)
    variables: dict[str, Any] = Field(default_factory=dict)

    # Accept both 'steps' and 'phases' from YAML for backward compatibility
    steps: list[WorkflowStep] = Field(
        default_factory=list, validation_alias=AliasChoices("steps", "phases")
    )

    # Global triggers (on_session_start, etc.)
    triggers: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)

    on_error: list[dict[str, Any]] = Field(default_factory=list)

    def get_step(self, step_name: str) -> WorkflowStep | None:
        for s in self.steps:
            if s.name == step_name:
                return s
        return None

    # Backward compatibility aliases
    @property
    def phases(self) -> list[WorkflowStep]:
        return self.steps

    def get_phase(self, phase_name: str) -> WorkflowStep | None:
        return self.get_step(phase_name)


# --- Workflow State Models (Runtime) ---


class WorkflowState(BaseModel):
    session_id: str
    workflow_name: str
    # Accept both 'step' and 'phase' for backward compatibility
    step: str = Field(validation_alias=AliasChoices("step", "phase"))
    step_entered_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC),
        validation_alias=AliasChoices("step_entered_at", "phase_entered_at"),
    )

    step_action_count: int = Field(
        default=0, validation_alias=AliasChoices("step_action_count", "phase_action_count")
    )
    total_action_count: int = 0

    artifacts: dict[str, str] = Field(default_factory=dict)
    observations: list[dict[str, Any]] = Field(default_factory=list)

    reflection_pending: bool = False
    context_injected: bool = False

    variables: dict[str, Any] = Field(default_factory=dict)

    # Task decomposition state
    task_list: list[dict[str, Any]] | None = None
    current_task_index: int = 0
    files_modified_this_task: int = 0

    # Approval state for user_approval exit conditions
    approval_pending: bool = False
    approval_condition_id: str | None = None  # Which condition is awaiting approval
    approval_prompt: str | None = None  # The prompt shown to user
    approval_requested_at: datetime | None = None
    approval_timeout_seconds: int | None = None  # None = no timeout

    # Escape hatch: temporarily disable enforcement
    disabled: bool = False
    disabled_reason: str | None = None

    # Track initial step for reset functionality
    initial_step: str | None = Field(
        default=None, validation_alias=AliasChoices("initial_step", "initial_phase")
    )

    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Backward compatibility aliases
    @property
    def phase(self) -> str:
        return self.step

    @property
    def phase_entered_at(self) -> datetime:
        return self.step_entered_at

    @property
    def phase_action_count(self) -> int:
        return self.step_action_count

    @property
    def initial_phase(self) -> str | None:
        return self.initial_step
