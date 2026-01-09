"""
Tests for config/tasks.py module.

RED PHASE: Tests initially import from tasks.py (should fail),
then will pass once task-related config classes are extracted from app.py.
"""

import unittest.mock

import pytest
from pydantic import ValidationError

# =============================================================================
# Import Tests (RED phase targets)
# =============================================================================


class TestCompactHandoffConfigImport:
    """Test that CompactHandoffConfig can be imported from the tasks module."""

    def test_import_from_tasks_module(self) -> None:
        """Test importing CompactHandoffConfig from config.tasks (RED phase target)."""
        from gobby.config.tasks import CompactHandoffConfig

        assert CompactHandoffConfig is not None


class TestPatternCriteriaConfigImport:
    """Test that PatternCriteriaConfig can be imported from the tasks module."""

    def test_import_from_tasks_module(self) -> None:
        """Test importing PatternCriteriaConfig from config.tasks (RED phase target)."""
        from gobby.config.tasks import PatternCriteriaConfig

        assert PatternCriteriaConfig is not None


class TestTaskExpansionConfigImport:
    """Test that TaskExpansionConfig can be imported from the tasks module."""

    def test_import_from_tasks_module(self) -> None:
        """Test importing TaskExpansionConfig from config.tasks (RED phase target)."""
        from gobby.config.tasks import TaskExpansionConfig

        assert TaskExpansionConfig is not None


class TestTaskValidationConfigImport:
    """Test that TaskValidationConfig can be imported from the tasks module."""

    def test_import_from_tasks_module(self) -> None:
        """Test importing TaskValidationConfig from config.tasks (RED phase target)."""
        from gobby.config.tasks import TaskValidationConfig

        assert TaskValidationConfig is not None


class TestGobbyTasksConfigImport:
    """Test that GobbyTasksConfig can be imported from the tasks module."""

    def test_import_from_tasks_module(self) -> None:
        """Test importing GobbyTasksConfig from config.tasks (RED phase target)."""
        from gobby.config.tasks import GobbyTasksConfig

        assert GobbyTasksConfig is not None


class TestWorkflowConfigImport:
    """Test that WorkflowConfig can be imported from the tasks module."""

    def test_import_from_tasks_module(self) -> None:
        """Test importing WorkflowConfig from config.tasks (RED phase target)."""
        from gobby.config.tasks import WorkflowConfig

        assert WorkflowConfig is not None


# =============================================================================
# CompactHandoffConfig Tests
# =============================================================================


class TestCompactHandoffConfigDefaults:
    """Test CompactHandoffConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test CompactHandoffConfig creates with all defaults."""
        from gobby.config.tasks import CompactHandoffConfig

        config = CompactHandoffConfig()
        assert config.enabled is True
        assert config.prompt is None

    def test_disabled_handoff(self) -> None:
        """Test CompactHandoffConfig with disabled handoff."""
        from gobby.config.tasks import CompactHandoffConfig

        config = CompactHandoffConfig(enabled=False)
        assert config.enabled is False


# =============================================================================
# PatternCriteriaConfig Tests
# =============================================================================


class TestPatternCriteriaConfigDefaults:
    """Test PatternCriteriaConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test PatternCriteriaConfig creates with defaults."""
        from gobby.config.tasks import PatternCriteriaConfig

        config = PatternCriteriaConfig()
        assert "strangler-fig" in config.patterns
        assert "tdd" in config.patterns
        assert "refactoring" in config.patterns

    def test_default_patterns_content(self) -> None:
        """Test default patterns have criteria."""
        from gobby.config.tasks import PatternCriteriaConfig

        config = PatternCriteriaConfig()
        assert len(config.patterns["strangler-fig"]) > 0
        assert len(config.patterns["tdd"]) > 0
        assert len(config.patterns["refactoring"]) > 0

    def test_default_detection_keywords(self) -> None:
        """Test default detection keywords exist."""
        from gobby.config.tasks import PatternCriteriaConfig

        config = PatternCriteriaConfig()
        assert "strangler-fig" in config.detection_keywords
        assert "tdd" in config.detection_keywords
        assert "refactoring" in config.detection_keywords


class TestPatternCriteriaConfigCustom:
    """Test PatternCriteriaConfig with custom values."""

    def test_custom_patterns(self) -> None:
        """Test setting custom patterns."""
        from gobby.config.tasks import PatternCriteriaConfig

        custom_patterns = {
            "my-pattern": ["criteria 1", "criteria 2"],
        }
        config = PatternCriteriaConfig(patterns=custom_patterns)
        assert config.patterns == custom_patterns

    def test_custom_detection_keywords(self) -> None:
        """Test setting custom detection keywords."""
        from gobby.config.tasks import PatternCriteriaConfig

        custom_keywords = {
            "my-pattern": ["keyword1", "keyword2"],
        }
        config = PatternCriteriaConfig(detection_keywords=custom_keywords)
        assert config.detection_keywords == custom_keywords


# =============================================================================
# TaskExpansionConfig Tests
# =============================================================================


class TestTaskExpansionConfigDefaults:
    """Test TaskExpansionConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test TaskExpansionConfig creates with all defaults."""
        from gobby.config.tasks import TaskExpansionConfig

        config = TaskExpansionConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-opus-4-5"
        assert config.prompt is None
        assert config.codebase_research_enabled is True
        assert config.research_model is None
        assert config.research_max_steps == 10
        assert config.tdd_mode is True
        assert config.max_subtasks == 15
        assert config.default_strategy == "auto"
        assert config.timeout == 300.0
        assert config.research_timeout == 60.0

    def test_default_pattern_criteria(self) -> None:
        """Test TaskExpansionConfig includes default pattern_criteria."""
        from gobby.config.tasks import TaskExpansionConfig

        config = TaskExpansionConfig()
        assert config.pattern_criteria is not None
        assert "strangler-fig" in config.pattern_criteria.patterns


class TestTaskExpansionConfigCustom:
    """Test TaskExpansionConfig with custom values."""

    def test_custom_model(self) -> None:
        """Test setting custom model."""
        from gobby.config.tasks import TaskExpansionConfig

        config = TaskExpansionConfig(model="claude-sonnet-4-5")
        assert config.model == "claude-sonnet-4-5"

    def test_custom_provider(self) -> None:
        """Test setting custom provider."""
        from gobby.config.tasks import TaskExpansionConfig

        config = TaskExpansionConfig(provider="gemini")
        assert config.provider == "gemini"

    def test_tdd_mode_disabled(self) -> None:
        """Test disabling TDD mode."""
        from gobby.config.tasks import TaskExpansionConfig

        config = TaskExpansionConfig(tdd_mode=False)
        assert config.tdd_mode is False

    def test_custom_max_subtasks(self) -> None:
        """Test setting custom max_subtasks."""
        from gobby.config.tasks import TaskExpansionConfig

        config = TaskExpansionConfig(max_subtasks=20)
        assert config.max_subtasks == 20

    def test_strategy_options(self) -> None:
        """Test different strategy options."""
        from gobby.config.tasks import TaskExpansionConfig

        for strategy in ["auto", "phased", "sequential", "parallel"]:
            config = TaskExpansionConfig(default_strategy=strategy)  # type: ignore
            assert config.default_strategy == strategy

    def test_custom_timeouts(self) -> None:
        """Test setting custom timeouts."""
        from gobby.config.tasks import TaskExpansionConfig

        config = TaskExpansionConfig(timeout=600.0, research_timeout=120.0)
        assert config.timeout == 600.0
        assert config.research_timeout == 120.0


class TestTaskExpansionConfigValidation:
    """Test TaskExpansionConfig validation."""

    def test_invalid_strategy(self) -> None:
        """Test that invalid strategy raises ValidationError."""
        from gobby.config.tasks import TaskExpansionConfig

        with pytest.raises(ValidationError):
            TaskExpansionConfig(default_strategy="invalid")  # type: ignore


# =============================================================================
# TaskValidationConfig Tests
# =============================================================================


class TestTaskValidationConfigDefaults:
    """Test TaskValidationConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test TaskValidationConfig creates with all defaults."""
        from gobby.config.tasks import TaskValidationConfig

        config = TaskValidationConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-haiku-4-5"
        assert config.prompt is None
        assert config.max_iterations == 10
        assert config.max_consecutive_errors == 3
        assert config.recurring_issue_threshold == 3
        assert config.issue_similarity_threshold == 0.8
        assert config.run_build_first is True
        assert config.build_command is None
        assert config.use_external_validator is False
        assert config.external_validator_model is None
        assert config.external_validator_mode == "llm"
        assert config.escalation_enabled is True
        assert config.escalation_notify == "none"
        assert config.auto_generate_on_create is True
        assert config.auto_generate_on_expand is True


class TestTaskValidationConfigCustom:
    """Test TaskValidationConfig with custom values."""

    def test_custom_max_iterations(self) -> None:
        """Test setting custom max_iterations."""
        from gobby.config.tasks import TaskValidationConfig

        config = TaskValidationConfig(max_iterations=5)
        assert config.max_iterations == 5

    def test_custom_build_command(self) -> None:
        """Test setting custom build command."""
        from gobby.config.tasks import TaskValidationConfig

        config = TaskValidationConfig(build_command="uv run pytest")
        assert config.build_command == "uv run pytest"

    def test_external_validator(self) -> None:
        """Test enabling external validator."""
        from gobby.config.tasks import TaskValidationConfig

        config = TaskValidationConfig(
            use_external_validator=True,
            external_validator_model="claude-opus-4-5",
        )
        assert config.use_external_validator is True
        assert config.external_validator_model == "claude-opus-4-5"

    def test_external_validator_mode_llm(self) -> None:
        """Test external validator mode set to llm (default)."""
        from gobby.config.tasks import TaskValidationConfig

        config = TaskValidationConfig(external_validator_mode="llm")
        assert config.external_validator_mode == "llm"

    def test_external_validator_mode_agent(self) -> None:
        """Test external validator mode set to agent."""
        from gobby.config.tasks import TaskValidationConfig

        config = TaskValidationConfig(external_validator_mode="agent")
        assert config.external_validator_mode == "agent"

    def test_external_validator_mode_spawn(self) -> None:
        """Test external validator mode set to spawn."""
        from gobby.config.tasks import TaskValidationConfig

        config = TaskValidationConfig(external_validator_mode="spawn")
        assert config.external_validator_mode == "spawn"

    def test_external_validator_full_config(self) -> None:
        """Test external validator with all options configured."""
        from gobby.config.tasks import TaskValidationConfig

        config = TaskValidationConfig(
            use_external_validator=True,
            external_validator_model="claude-sonnet-4-5",
            external_validator_mode="spawn",
        )
        assert config.use_external_validator is True
        assert config.external_validator_model == "claude-sonnet-4-5"
        assert config.external_validator_mode == "spawn"

    def test_escalation_webhook(self) -> None:
        """Test escalation with webhook."""
        from gobby.config.tasks import TaskValidationConfig

        config = TaskValidationConfig(
            escalation_notify="webhook",
            escalation_webhook_url="https://example.com/webhook",
        )
        assert config.escalation_notify == "webhook"
        assert config.escalation_webhook_url == "https://example.com/webhook"


class TestTaskValidationConfigValidation:
    """Test TaskValidationConfig validation."""

    def test_max_iterations_must_be_positive(self) -> None:
        """Test that max_iterations must be positive."""
        from gobby.config.tasks import TaskValidationConfig

        with pytest.raises(ValidationError) as exc_info:
            TaskValidationConfig(max_iterations=0)
        assert "positive" in str(exc_info.value).lower()

        with pytest.raises(ValidationError) as exc_info:
            TaskValidationConfig(max_iterations=-1)
        assert "positive" in str(exc_info.value).lower()

    def test_max_consecutive_errors_must_be_positive(self) -> None:
        """Test that max_consecutive_errors must be positive."""
        from gobby.config.tasks import TaskValidationConfig

        with pytest.raises(ValidationError) as exc_info:
            TaskValidationConfig(max_consecutive_errors=0)
        assert "positive" in str(exc_info.value).lower()

    def test_recurring_issue_threshold_must_be_positive(self) -> None:
        """Test that recurring_issue_threshold must be positive."""
        from gobby.config.tasks import TaskValidationConfig

        with pytest.raises(ValidationError) as exc_info:
            TaskValidationConfig(recurring_issue_threshold=0)
        assert "positive" in str(exc_info.value).lower()

    def test_issue_similarity_threshold_range(self) -> None:
        """Test that issue_similarity_threshold must be between 0 and 1."""
        from gobby.config.tasks import TaskValidationConfig

        # Too low
        with pytest.raises(ValidationError) as exc_info:
            TaskValidationConfig(issue_similarity_threshold=-0.1)
        assert "0" in str(exc_info.value) and "1" in str(exc_info.value)

        # Too high
        with pytest.raises(ValidationError) as exc_info:
            TaskValidationConfig(issue_similarity_threshold=1.1)
        assert "0" in str(exc_info.value) and "1" in str(exc_info.value)

    def test_issue_similarity_threshold_boundaries(self) -> None:
        """Test issue_similarity_threshold at valid boundary values."""
        from gobby.config.tasks import TaskValidationConfig

        config = TaskValidationConfig(issue_similarity_threshold=0.0)
        assert config.issue_similarity_threshold == 0.0

        config = TaskValidationConfig(issue_similarity_threshold=1.0)
        assert config.issue_similarity_threshold == 1.0

    def test_invalid_escalation_notify(self) -> None:
        """Test that invalid escalation_notify raises ValidationError."""
        from gobby.config.tasks import TaskValidationConfig

        with pytest.raises(ValidationError):
            TaskValidationConfig(escalation_notify="invalid")  # type: ignore

    def test_invalid_external_validator_mode(self) -> None:
        """Test that invalid external_validator_mode raises ValidationError."""
        from gobby.config.tasks import TaskValidationConfig

        with pytest.raises(ValidationError):
            TaskValidationConfig(external_validator_mode="invalid")  # type: ignore


# =============================================================================
# GobbyTasksConfig Tests
# =============================================================================


class TestGobbyTasksConfigDefaults:
    """Test GobbyTasksConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test GobbyTasksConfig creates with all defaults."""
        from gobby.config.tasks import GobbyTasksConfig

        config = GobbyTasksConfig()
        assert config.enabled is True
        assert config.show_result_on_create is False

    def test_default_nested_configs(self) -> None:
        """Test default nested expansion and validation configs."""
        from gobby.config.tasks import GobbyTasksConfig

        config = GobbyTasksConfig()
        assert config.expansion is not None
        assert config.expansion.enabled is True
        assert config.validation is not None
        assert config.validation.enabled is True


class TestGobbyTasksConfigCustom:
    """Test GobbyTasksConfig with custom values."""

    def test_disabled(self) -> None:
        """Test disabling gobby-tasks."""
        from gobby.config.tasks import GobbyTasksConfig

        config = GobbyTasksConfig(enabled=False)
        assert config.enabled is False

    def test_show_result_on_create(self) -> None:
        """Test enabling show_result_on_create."""
        from gobby.config.tasks import GobbyTasksConfig

        config = GobbyTasksConfig(show_result_on_create=True)
        assert config.show_result_on_create is True

    def test_custom_expansion_config(self) -> None:
        """Test custom expansion config."""
        from gobby.config.tasks import GobbyTasksConfig, TaskExpansionConfig

        expansion = TaskExpansionConfig(model="claude-sonnet-4-5", tdd_mode=False)
        config = GobbyTasksConfig(expansion=expansion)
        assert config.expansion.model == "claude-sonnet-4-5"
        assert config.expansion.tdd_mode is False

    def test_custom_validation_config(self) -> None:
        """Test custom validation config."""
        from gobby.config.tasks import GobbyTasksConfig, TaskValidationConfig

        validation = TaskValidationConfig(max_iterations=5)
        config = GobbyTasksConfig(validation=validation)
        assert config.validation.max_iterations == 5


# =============================================================================
# WorkflowConfig Tests
# =============================================================================


class TestWorkflowConfigDefaults:
    """Test WorkflowConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test WorkflowConfig creates with all defaults."""
        from gobby.config.tasks import WorkflowConfig

        config = WorkflowConfig()
        assert config.enabled is True
        assert config.timeout == 0.0
        assert config.require_task_before_edit is False
        assert "Edit" in config.protected_tools
        assert "Write" in config.protected_tools
        assert "NotebookEdit" in config.protected_tools


class TestWorkflowConfigCustom:
    """Test WorkflowConfig with custom values."""

    def test_disabled_workflow(self) -> None:
        """Test disabling workflow engine."""
        from gobby.config.tasks import WorkflowConfig

        config = WorkflowConfig(enabled=False)
        assert config.enabled is False

    def test_custom_timeout(self) -> None:
        """Test setting custom timeout."""
        from gobby.config.tasks import WorkflowConfig

        config = WorkflowConfig(timeout=60.0)
        assert config.timeout == 60.0

    def test_require_task_before_edit(self) -> None:
        """Test enabling require_task_before_edit."""
        from gobby.config.tasks import WorkflowConfig

        config = WorkflowConfig(require_task_before_edit=True)
        assert config.require_task_before_edit is True

    def test_custom_protected_tools(self) -> None:
        """Test custom protected_tools list."""
        from gobby.config.tasks import WorkflowConfig

        config = WorkflowConfig(protected_tools=["Edit", "Write", "Bash"])
        assert config.protected_tools == ["Edit", "Write", "Bash"]


class TestWorkflowConfigValidation:
    """Test WorkflowConfig validation."""

    def test_timeout_must_be_non_negative(self) -> None:
        """Test that timeout must be non-negative."""
        from gobby.config.tasks import WorkflowConfig

        with pytest.raises(ValidationError) as exc_info:
            WorkflowConfig(timeout=-1.0)
        assert "non-negative" in str(exc_info.value).lower()

    def test_timeout_zero_allowed(self) -> None:
        """Test that timeout=0 is allowed (means no timeout)."""
        from gobby.config.tasks import WorkflowConfig

        config = WorkflowConfig(timeout=0.0)
        assert config.timeout == 0.0


# =============================================================================
# Baseline Tests (import from app.py)
# =============================================================================


class TestCompactHandoffConfigFromAppPy:
    """Verify that tests pass when importing from app.py (reference implementation)."""

    def test_import_from_app_py(self) -> None:
        """Test importing CompactHandoffConfig from app.py works (baseline)."""
        from gobby.config.app import CompactHandoffConfig

        config = CompactHandoffConfig()
        assert config.enabled is True


class TestPatternCriteriaConfigFromAppPy:
    """Verify PatternCriteriaConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing PatternCriteriaConfig from app.py works (baseline)."""
        from gobby.config.app import PatternCriteriaConfig

        config = PatternCriteriaConfig()
        assert "strangler-fig" in config.patterns


class TestTaskExpansionConfigFromAppPy:
    """Verify TaskExpansionConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing TaskExpansionConfig from app.py works (baseline)."""
        from gobby.config.app import TaskExpansionConfig

        config = TaskExpansionConfig()
        assert config.enabled is True
        assert config.tdd_mode is True


class TestTaskValidationConfigFromAppPy:
    """Verify TaskValidationConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing TaskValidationConfig from app.py works (baseline)."""
        from gobby.config.app import TaskValidationConfig

        config = TaskValidationConfig()
        assert config.enabled is True
        assert config.max_iterations == 10

    def test_validation_via_app_py(self) -> None:
        """Test validation works when imported from app.py."""
        from gobby.config.app import TaskValidationConfig

        with pytest.raises(ValidationError):
            TaskValidationConfig(max_iterations=0)


class TestGobbyTasksConfigFromAppPy:
    """Verify GobbyTasksConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing GobbyTasksConfig from app.py works (baseline)."""
        from gobby.config.app import GobbyTasksConfig

        config = GobbyTasksConfig()
        assert config.enabled is True


class TestWorkflowConfigFromAppPy:
    """Verify WorkflowConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing WorkflowConfig from app.py works (baseline)."""
        from gobby.config.app import WorkflowConfig

        config = WorkflowConfig()
        assert config.enabled is True
        assert config.timeout == 0.0

    def test_validation_via_app_py(self) -> None:
        """Test validation works when imported from app.py."""
        from gobby.config.app import WorkflowConfig

        with pytest.raises(ValidationError):
            WorkflowConfig(timeout=-1.0)


# =============================================================================
# WorkflowVariablesConfig Tests
# =============================================================================


class TestWorkflowVariablesConfigImport:
    """Test that WorkflowVariablesConfig can be imported from the tasks module."""

    def test_import_from_tasks_module(self) -> None:
        """Test importing WorkflowVariablesConfig from config.tasks."""
        from gobby.config.tasks import WorkflowVariablesConfig

        assert WorkflowVariablesConfig is not None


class TestWorkflowVariablesConfigDefaults:
    """Test WorkflowVariablesConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test WorkflowVariablesConfig creates with all defaults."""
        from gobby.config.tasks import WorkflowVariablesConfig

        config = WorkflowVariablesConfig()
        assert config.require_task_before_edit is False
        assert config.require_commit_before_stop is True
        assert config.auto_decompose is True
        assert config.tdd_mode is True
        assert config.memory_injection_enabled is True
        assert config.memory_injection_limit == 10
        assert config.session_task is None

    def test_all_fields_have_correct_types(self) -> None:
        """Test that all fields have correct types."""
        from gobby.config.tasks import WorkflowVariablesConfig

        config = WorkflowVariablesConfig()
        assert isinstance(config.require_task_before_edit, bool)
        assert isinstance(config.require_commit_before_stop, bool)
        assert isinstance(config.auto_decompose, bool)
        assert isinstance(config.tdd_mode, bool)
        assert isinstance(config.memory_injection_enabled, bool)
        assert isinstance(config.memory_injection_limit, int)
        # session_task can be None, str, or list


class TestWorkflowVariablesConfigCustom:
    """Test WorkflowVariablesConfig with custom values."""

    def test_custom_boolean_values(self) -> None:
        """Test setting custom boolean values."""
        from gobby.config.tasks import WorkflowVariablesConfig

        config = WorkflowVariablesConfig(
            require_task_before_edit=True,
            require_commit_before_stop=False,
            auto_decompose=False,
            tdd_mode=False,
            memory_injection_enabled=False,
        )
        assert config.require_task_before_edit is True
        assert config.require_commit_before_stop is False
        assert config.auto_decompose is False
        assert config.tdd_mode is False
        assert config.memory_injection_enabled is False

    def test_custom_memory_injection_limit(self) -> None:
        """Test setting custom memory_injection_limit."""
        from gobby.config.tasks import WorkflowVariablesConfig

        config = WorkflowVariablesConfig(memory_injection_limit=25)
        assert config.memory_injection_limit == 25

    def test_session_task_string_value(self) -> None:
        """Test session_task with single task ID string."""
        from gobby.config.tasks import WorkflowVariablesConfig

        config = WorkflowVariablesConfig(session_task="gt-abc123")
        assert config.session_task == "gt-abc123"

    def test_session_task_list_value(self) -> None:
        """Test session_task with list of task IDs."""
        from gobby.config.tasks import WorkflowVariablesConfig

        config = WorkflowVariablesConfig(session_task=["gt-abc", "gt-def"])
        assert config.session_task == ["gt-abc", "gt-def"]

    def test_session_task_wildcard(self) -> None:
        """Test session_task with wildcard '*' for all ready tasks."""
        from gobby.config.tasks import WorkflowVariablesConfig

        config = WorkflowVariablesConfig(session_task="*")
        assert config.session_task == "*"


class TestWorkflowVariablesConfigValidation:
    """Test WorkflowVariablesConfig validation."""

    def test_memory_injection_limit_must_be_positive(self) -> None:
        """Test that memory_injection_limit must be positive."""
        from gobby.config.tasks import WorkflowVariablesConfig

        with pytest.raises(ValidationError) as exc_info:
            WorkflowVariablesConfig(memory_injection_limit=0)
        assert "positive" in str(exc_info.value).lower()

    def test_memory_injection_limit_negative_rejected(self) -> None:
        """Test that negative memory_injection_limit is rejected."""
        from gobby.config.tasks import WorkflowVariablesConfig

        with pytest.raises(ValidationError) as exc_info:
            WorkflowVariablesConfig(memory_injection_limit=-5)
        assert "positive" in str(exc_info.value).lower()


# =============================================================================
# WorkflowVariablesConfig Merge Logic Tests
# =============================================================================


class TestWorkflowVariablesMergeWithDB:
    """Tests for merging YAML defaults with DB session overrides.

    Tests the merge flow:
    workflow YAML variables (defaults) → DB workflow_states.variables (session overrides) → effective config
    """

    def test_no_db_overrides_returns_yaml_defaults(self) -> None:
        """When DB has no overrides, YAML defaults are used."""
        from gobby.config.tasks import WorkflowVariablesConfig

        # YAML defaults (from session-lifecycle.yaml pattern)
        yaml_defaults = {
            "require_task_before_edit": False,
            "require_commit_before_stop": True,
            "auto_decompose": True,
            "tdd_mode": True,
            "memory_injection_enabled": True,
            "memory_injection_limit": 10,
            "session_task": None,
        }

        # DB has no overrides (empty dict)
        db_overrides: dict = {}

        # Merge: YAML | DB (DB takes precedence)
        effective = {**yaml_defaults, **db_overrides}

        # Should match YAML defaults exactly
        assert effective == yaml_defaults

        # Validate through config class
        config = WorkflowVariablesConfig(**effective)
        assert config.auto_decompose is True
        assert config.tdd_mode is True
        assert config.memory_injection_limit == 10

    def test_partial_db_overrides_merge_correctly(self) -> None:
        """Partial DB overrides merge with YAML defaults."""
        from gobby.config.tasks import WorkflowVariablesConfig

        yaml_defaults = {
            "require_task_before_edit": False,
            "require_commit_before_stop": True,
            "auto_decompose": True,
            "tdd_mode": True,
            "memory_injection_enabled": True,
            "memory_injection_limit": 10,
            "session_task": None,
        }

        # DB overrides only some fields
        db_overrides = {
            "auto_decompose": False,  # Override
            "session_task": "gt-xyz789",  # Override
        }

        # Merge
        effective = {**yaml_defaults, **db_overrides}

        # Verify partial overrides work
        assert effective["auto_decompose"] is False  # From DB
        assert effective["session_task"] == "gt-xyz789"  # From DB
        assert effective["tdd_mode"] is True  # From YAML (not overridden)
        assert effective["memory_injection_limit"] == 10  # From YAML

        # Validate through config class
        config = WorkflowVariablesConfig(**effective)
        assert config.auto_decompose is False
        assert config.session_task == "gt-xyz789"
        assert config.tdd_mode is True

    def test_full_db_overrides_take_precedence(self) -> None:
        """Full DB overrides completely override YAML defaults."""
        from gobby.config.tasks import WorkflowVariablesConfig

        yaml_defaults = {
            "require_task_before_edit": False,
            "require_commit_before_stop": True,
            "auto_decompose": True,
            "tdd_mode": True,
            "memory_injection_enabled": True,
            "memory_injection_limit": 10,
            "session_task": None,
        }

        # DB overrides everything
        db_overrides = {
            "require_task_before_edit": True,
            "require_commit_before_stop": False,
            "auto_decompose": False,
            "tdd_mode": False,
            "memory_injection_enabled": False,
            "memory_injection_limit": 5,
            "session_task": ["gt-aaa", "gt-bbb"],
        }

        effective = {**yaml_defaults, **db_overrides}

        # All values should be from DB
        assert effective == db_overrides

        # Validate through config class
        config = WorkflowVariablesConfig(**effective)
        assert config.require_task_before_edit is True
        assert config.require_commit_before_stop is False
        assert config.auto_decompose is False
        assert config.tdd_mode is False
        assert config.memory_injection_enabled is False
        assert config.memory_injection_limit == 5
        assert config.session_task == ["gt-aaa", "gt-bbb"]

    def test_invalid_db_values_rejected_wrong_type_bool(self) -> None:
        """Invalid boolean value from DB is rejected by validator."""
        from gobby.config.tasks import WorkflowVariablesConfig

        yaml_defaults = {"auto_decompose": True}

        # DB has wrong type - string instead of bool
        db_overrides = {"auto_decompose": "not_a_bool"}

        effective = {**yaml_defaults, **db_overrides}

        # Pydantic should coerce or reject
        # "not_a_bool" as string is truthy but shouldn't be valid
        with pytest.raises(ValidationError):
            WorkflowVariablesConfig(**effective)

    def test_invalid_db_values_rejected_memory_limit_zero(self) -> None:
        """Invalid memory_injection_limit=0 from DB is rejected."""
        from gobby.config.tasks import WorkflowVariablesConfig

        yaml_defaults = {"memory_injection_limit": 10}
        db_overrides = {"memory_injection_limit": 0}

        effective = {**yaml_defaults, **db_overrides}

        with pytest.raises(ValidationError) as exc_info:
            WorkflowVariablesConfig(**effective)
        assert "positive" in str(exc_info.value).lower()

    def test_invalid_db_values_rejected_memory_limit_negative(self) -> None:
        """Invalid negative memory_injection_limit from DB is rejected."""
        from gobby.config.tasks import WorkflowVariablesConfig

        yaml_defaults = {"memory_injection_limit": 10}
        db_overrides = {"memory_injection_limit": -100}

        effective = {**yaml_defaults, **db_overrides}

        with pytest.raises(ValidationError) as exc_info:
            WorkflowVariablesConfig(**effective)
        assert "positive" in str(exc_info.value).lower()

    def test_invalid_db_values_rejected_wrong_type_int(self) -> None:
        """Invalid type for memory_injection_limit from DB is rejected."""
        from gobby.config.tasks import WorkflowVariablesConfig

        yaml_defaults = {"memory_injection_limit": 10}
        db_overrides = {"memory_injection_limit": "not_an_int"}

        effective = {**yaml_defaults, **db_overrides}

        with pytest.raises(ValidationError):
            WorkflowVariablesConfig(**effective)

    def test_extra_db_fields_are_ignored(self) -> None:
        """Extra fields from DB that aren't in config are ignored (model_config)."""
        from gobby.config.tasks import WorkflowVariablesConfig

        yaml_defaults = {"auto_decompose": True}
        db_overrides = {
            "auto_decompose": False,
            "unknown_field": "should_be_ignored",
        }

        effective = {**yaml_defaults, **db_overrides}

        # Should not raise - extra fields are ignored by default Pydantic
        config = WorkflowVariablesConfig(**effective)
        assert config.auto_decompose is False
        # unknown_field should not be accessible
        assert not hasattr(config, "unknown_field")


# =============================================================================
# merge_workflow_variables Function Tests
# =============================================================================


class TestMergeWorkflowVariablesFunction:
    """Tests for the merge_workflow_variables function."""

    def test_import_function(self) -> None:
        """Test merge_workflow_variables can be imported."""
        from gobby.config.tasks import merge_workflow_variables

        assert merge_workflow_variables is not None
        assert callable(merge_workflow_variables)

    def test_merge_with_no_overrides(self) -> None:
        """When db_overrides is None, returns YAML defaults."""
        from gobby.config.tasks import merge_workflow_variables

        yaml_defaults = {
            "auto_decompose": True,
            "tdd_mode": True,
            "memory_injection_limit": 10,
        }

        effective = merge_workflow_variables(yaml_defaults, None)

        assert effective["auto_decompose"] is True
        assert effective["tdd_mode"] is True
        assert effective["memory_injection_limit"] == 10

    def test_merge_with_empty_overrides(self) -> None:
        """When db_overrides is empty dict, returns YAML defaults."""
        from gobby.config.tasks import merge_workflow_variables

        yaml_defaults = {"auto_decompose": True}
        effective = merge_workflow_variables(yaml_defaults, {})

        assert effective["auto_decompose"] is True

    def test_merge_partial_overrides(self) -> None:
        """Partial DB overrides merge correctly with YAML defaults."""
        from gobby.config.tasks import merge_workflow_variables

        yaml_defaults = {
            "auto_decompose": True,
            "tdd_mode": True,
            "memory_injection_limit": 10,
        }
        db_overrides = {"auto_decompose": False}

        effective = merge_workflow_variables(yaml_defaults, db_overrides)

        assert effective["auto_decompose"] is False  # From DB
        assert effective["tdd_mode"] is True  # From YAML
        assert effective["memory_injection_limit"] == 10  # From YAML

    def test_merge_full_overrides(self) -> None:
        """Full DB overrides take precedence."""
        from gobby.config.tasks import merge_workflow_variables

        yaml_defaults = {
            "require_task_before_edit": False,
            "require_commit_before_stop": True,
            "auto_decompose": True,
            "tdd_mode": True,
            "memory_injection_enabled": True,
            "memory_injection_limit": 10,
            "session_task": None,
        }
        db_overrides = {
            "require_task_before_edit": True,
            "require_commit_before_stop": False,
            "auto_decompose": False,
            "tdd_mode": False,
            "memory_injection_enabled": False,
            "memory_injection_limit": 5,
            "session_task": "gt-xyz",
        }

        effective = merge_workflow_variables(yaml_defaults, db_overrides)

        # All should come from DB
        assert effective["require_task_before_edit"] is True
        assert effective["require_commit_before_stop"] is False
        assert effective["auto_decompose"] is False
        assert effective["tdd_mode"] is False
        assert effective["memory_injection_enabled"] is False
        assert effective["memory_injection_limit"] == 5
        assert effective["session_task"] == "gt-xyz"

    def test_validation_enabled_by_default(self) -> None:
        """By default, validation is enabled and returns validated model."""
        from gobby.config.tasks import merge_workflow_variables

        # Should fill in defaults for missing fields
        effective = merge_workflow_variables({"auto_decompose": False}, None)

        # Should have all fields from model defaults
        assert "require_task_before_edit" in effective
        assert "memory_injection_limit" in effective

    def test_validation_rejects_invalid_values(self) -> None:
        """Invalid values are rejected when validation is enabled."""
        from gobby.config.tasks import merge_workflow_variables

        with pytest.raises(ValidationError):
            merge_workflow_variables({"memory_injection_limit": 0})

    def test_validation_disabled_skips_validation(self) -> None:
        """When validate=False, validation is skipped."""
        from gobby.config.tasks import merge_workflow_variables

        # Invalid value but with validation disabled
        effective = merge_workflow_variables({"memory_injection_limit": 0}, None, validate=False)

        # Should pass through without validation
        assert effective["memory_injection_limit"] == 0

    def test_returns_dict_for_action_access(self) -> None:
        """Returns dict that actions can access like effective['key']."""
        from gobby.config.tasks import merge_workflow_variables

        effective = merge_workflow_variables({"auto_decompose": True})

        # Should be a dict, not a Pydantic model
        assert isinstance(effective, dict)
        assert effective["auto_decompose"] is True


# =============================================================================
# Backward Compatibility Layer Tests
# =============================================================================


class TestBackwardCompatibilityLayer:
    """Tests for backward compatibility with old config.yaml settings.

    The old location for behavior settings was in config.yaml under various sections:
    - workflow.require_task_before_edit
    - gobby-tasks.expansion.tdd_mode
    - memory.injection_limit

    The new location is workflow YAML variables section.

    Backward compatibility requirements:
    1. Old config.yaml settings still work
    2. Deprecation warning logged when old location used
    3. New location (workflow YAML) takes precedence
    4. Missing in both locations uses hardcoded defaults
    """

    def test_old_config_location_still_works(self) -> None:
        """Settings in old config.yaml location still work.

        When workflow YAML has no variables set, fall back to config.yaml values.
        """
        from gobby.config.tasks import WorkflowVariablesConfig

        # Simulate old config.yaml values (from WorkflowConfig, TaskExpansionConfig, etc.)
        old_config_values = {
            "require_task_before_edit": True,  # From WorkflowConfig
            "tdd_mode": False,  # From TaskExpansionConfig
            "memory_injection_limit": 5,  # From MemoryConfig
        }

        # New workflow YAML has empty variables (not specified)
        yaml_variables: dict = {}

        # Merge with old config as fallback
        # Pattern: yaml_variables | old_config_values | hardcoded_defaults
        hardcoded_defaults = WorkflowVariablesConfig().model_dump()
        effective = {**hardcoded_defaults, **old_config_values, **yaml_variables}

        # Old config values should be used
        assert effective["require_task_before_edit"] is True
        assert effective["tdd_mode"] is False
        assert effective["memory_injection_limit"] == 5

    def test_new_location_takes_precedence_over_old(self) -> None:
        """New workflow YAML location takes precedence over old config.yaml."""
        from gobby.config.tasks import WorkflowVariablesConfig

        # Old config.yaml values
        old_config_values = {
            "require_task_before_edit": True,
            "tdd_mode": False,
            "memory_injection_limit": 5,
        }

        # New workflow YAML variables (takes precedence)
        yaml_variables = {
            "require_task_before_edit": False,  # Override old config
            "tdd_mode": True,  # Override old config
        }

        # Merge order: defaults < old_config < yaml_variables
        hardcoded_defaults = WorkflowVariablesConfig().model_dump()
        effective = {**hardcoded_defaults, **old_config_values, **yaml_variables}

        # New YAML values should take precedence
        assert effective["require_task_before_edit"] is False  # From YAML
        assert effective["tdd_mode"] is True  # From YAML
        # Old config value used where YAML doesn't override
        assert effective["memory_injection_limit"] == 5  # From old config

    def test_both_locations_missing_uses_hardcoded_defaults(self) -> None:
        """When both old config and new YAML are missing, use hardcoded defaults."""
        from gobby.config.tasks import WorkflowVariablesConfig

        # No old config values
        old_config_values: dict = {}

        # No YAML variables
        yaml_variables: dict = {}

        # Merge
        hardcoded_defaults = WorkflowVariablesConfig().model_dump()
        effective = {**hardcoded_defaults, **old_config_values, **yaml_variables}

        # Should match hardcoded defaults
        assert effective["require_task_before_edit"] is False
        assert effective["require_commit_before_stop"] is True
        assert effective["auto_decompose"] is True
        assert effective["tdd_mode"] is True
        assert effective["memory_injection_enabled"] is True
        assert effective["memory_injection_limit"] == 10
        assert effective["session_task"] is None

    def test_deprecation_warning_logged_for_old_location(self) -> None:
        """Deprecation warning is logged when old config.yaml location is used.

        This test documents the expected behavior for the implementation phase.
        The actual logging will be implemented in gt-1428cb.
        """
        import logging

        from gobby.config.tasks import WorkflowVariablesConfig

        # Test structure for deprecation detection
        def get_effective_with_deprecation_check(
            yaml_variables: dict,
            old_config_values: dict,
            logger: logging.Logger,
        ) -> dict:
            """Get effective config with deprecation warnings for old config usage."""
            hardcoded_defaults = WorkflowVariablesConfig().model_dump()

            # Check which old config values will be used (not overridden by YAML)
            deprecated_keys_used = []
            for key in old_config_values:
                if key not in yaml_variables and key in hardcoded_defaults:
                    deprecated_keys_used.append(key)

            # Log deprecation warning if old config values are being used
            if deprecated_keys_used:
                logger.warning(
                    f"Using deprecated config.yaml settings: {deprecated_keys_used}. "
                    "Move these to workflow YAML variables section."
                )

            return {**hardcoded_defaults, **old_config_values, **yaml_variables}

        # Test the deprecation detection
        test_logger = logging.getLogger("test_deprecation")

        # When old config is used without YAML override, warning should be possible
        yaml_variables: dict = {}
        old_config_values = {"tdd_mode": False}

        with unittest.mock.patch.object(test_logger, "warning") as mock_warning:
            get_effective_with_deprecation_check(yaml_variables, old_config_values, test_logger)
            mock_warning.assert_called_once()
            warning_msg = mock_warning.call_args[0][0]
            assert "deprecated" in warning_msg.lower()
            assert "tdd_mode" in warning_msg

    def test_no_deprecation_warning_when_yaml_overrides(self) -> None:
        """No deprecation warning when YAML variables override old config."""
        import logging

        from gobby.config.tasks import WorkflowVariablesConfig

        def get_effective_with_deprecation_check(
            yaml_variables: dict,
            old_config_values: dict,
            logger: logging.Logger,
        ) -> dict:
            hardcoded_defaults = WorkflowVariablesConfig().model_dump()

            deprecated_keys_used = []
            for key in old_config_values:
                if key not in yaml_variables and key in hardcoded_defaults:
                    deprecated_keys_used.append(key)

            if deprecated_keys_used:
                logger.warning(f"Using deprecated config.yaml settings: {deprecated_keys_used}.")

            return {**hardcoded_defaults, **old_config_values, **yaml_variables}

        test_logger = logging.getLogger("test_no_deprecation")

        # YAML overrides old config - no warning should be logged
        yaml_variables = {"tdd_mode": True}  # Overrides old config
        old_config_values = {"tdd_mode": False}

        with unittest.mock.patch.object(test_logger, "warning") as mock_warning:
            get_effective_with_deprecation_check(yaml_variables, old_config_values, test_logger)
            mock_warning.assert_not_called()
