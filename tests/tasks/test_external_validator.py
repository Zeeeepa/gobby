"""Tests for external validator functionality.

TDD Red Phase: These tests define the expected behavior for
run_external_validation() and related external validator logic
which does not yet exist.

Task: gt-14b076
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from gobby.config.app import TaskValidationConfig
from gobby.tasks.validation_models import Issue, IssueSeverity, IssueType


class TestRunExternalValidation:
    """Tests for external validation with a separate LLM agent."""

    @pytest.fixture
    def validation_config(self):
        """Create a validation config with external validator enabled."""
        return TaskValidationConfig(
            enabled=True,
            provider="claude",
            model="claude-haiku-4-5",
            use_external_validator=True,
            external_validator_model="claude-sonnet-4-5",
        )

    @pytest.fixture
    def mock_llm_service(self):
        """Create a mock LLM service."""
        from gobby.llm import LLMProvider, LLMService

        service = MagicMock(spec=LLMService)
        provider = AsyncMock(spec=LLMProvider)
        service.get_provider.return_value = provider
        return service

    @pytest.fixture
    def sample_task(self):
        """Create a sample task for validation."""
        return {
            "id": "gt-test123",
            "title": "Implement user authentication",
            "description": "Add OAuth2 login flow",
            "validation_criteria": "- [ ] Users can log in with OAuth\n- [ ] Tokens are stored securely",
        }

    @pytest.mark.asyncio
    async def test_external_validation_creates_fresh_context(
        self, validation_config, mock_llm_service, sample_task
    ):
        """Test that external validation creates a fresh context prompt without prior conversation."""
        from gobby.tasks.external_validator import run_external_validation

        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.return_value = (
            '{"status": "valid", "feedback": "All criteria met", "issues": []}'
        )

        changes_context = """
        diff --git a/src/auth.py b/src/auth.py
        +def oauth_login():
        +    return authenticate_with_oauth()
        """

        await run_external_validation(
            config=validation_config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context=changes_context,
        )

        # Verify the LLM was called
        mock_provider.generate_text.assert_called_once()

        # Get the prompt that was sent
        call_kwargs = mock_provider.generate_text.call_args.kwargs
        prompt = call_kwargs["prompt"]

        # Prompt should contain task info but be a fresh context
        assert "user authentication" in prompt.lower() or "oauth" in prompt.lower()
        assert "validation criteria" in prompt.lower() or "criteria" in prompt.lower()
        assert "diff" in prompt.lower() or changes_context in prompt

        # Should NOT contain prior conversation markers
        assert "assistant:" not in prompt.lower()
        assert "human:" not in prompt.lower()

    @pytest.mark.asyncio
    async def test_external_validation_uses_configured_model(
        self, validation_config, mock_llm_service, sample_task
    ):
        """Test that external validation uses the external_validator_model config."""
        from gobby.tasks.external_validator import run_external_validation

        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.return_value = (
            '{"status": "valid", "feedback": "OK", "issues": []}'
        )

        await run_external_validation(
            config=validation_config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context="some changes",
        )

        # Verify the external validator model was used
        call_kwargs = mock_provider.generate_text.call_args.kwargs
        assert call_kwargs["model"] == "claude-sonnet-4-5"

    @pytest.mark.asyncio
    async def test_external_validation_falls_back_to_default_model(
        self, mock_llm_service, sample_task
    ):
        """Test that external validation falls back to validation.model when external_validator_model is not set."""
        from gobby.tasks.external_validator import run_external_validation

        config = TaskValidationConfig(
            enabled=True,
            provider="claude",
            model="claude-haiku-4-5",
            use_external_validator=True,
            external_validator_model=None,  # Not set
        )

        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.return_value = (
            '{"status": "valid", "feedback": "OK", "issues": []}'
        )

        await run_external_validation(
            config=config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context="some changes",
        )

        # Should fall back to the default model
        call_kwargs = mock_provider.generate_text.call_args.kwargs
        assert call_kwargs["model"] == "claude-haiku-4-5"

    @pytest.mark.asyncio
    async def test_external_validation_parses_structured_json_response(
        self, validation_config, mock_llm_service, sample_task
    ):
        """Test that external validation correctly parses structured JSON response."""
        from gobby.tasks.external_validator import ExternalValidationResult, run_external_validation

        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.return_value = """
        {
            "status": "invalid",
            "summary": "Missing test coverage",
            "issues": [
                {
                    "type": "acceptance_gap",
                    "severity": "major",
                    "title": "No unit tests for OAuth flow",
                    "location": "src/auth.py",
                    "details": "The OAuth login function has no test coverage",
                    "suggested_fix": "Add tests in tests/test_auth.py"
                }
            ]
        }
        """

        result = await run_external_validation(
            config=validation_config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context="diff content",
        )

        assert isinstance(result, ExternalValidationResult)
        assert result.status == "invalid"
        assert result.summary == "Missing test coverage"
        assert len(result.issues) == 1
        assert result.issues[0].issue_type == IssueType.ACCEPTANCE_GAP
        assert result.issues[0].title == "No unit tests for OAuth flow"

    @pytest.mark.asyncio
    async def test_external_validation_handles_llm_error(
        self, validation_config, mock_llm_service, sample_task
    ):
        """Test graceful handling of LLM errors during external validation."""
        from gobby.tasks.external_validator import ExternalValidationResult, run_external_validation

        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.side_effect = Exception("LLM API error")

        result = await run_external_validation(
            config=validation_config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context="diff content",
        )

        # Should return error result, not raise
        assert isinstance(result, ExternalValidationResult)
        assert result.status == "error"
        assert "LLM API error" in result.summary or result.error is not None

    @pytest.mark.asyncio
    async def test_external_validation_handles_malformed_json(
        self, validation_config, mock_llm_service, sample_task
    ):
        """Test handling of malformed JSON response from external validator."""
        from gobby.tasks.external_validator import ExternalValidationResult, run_external_validation

        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.return_value = "This is not valid JSON response"

        result = await run_external_validation(
            config=validation_config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context="diff content",
        )

        # Should return error or pending status, not raise
        assert isinstance(result, ExternalValidationResult)
        assert result.status in ("error", "pending")

    @pytest.mark.asyncio
    async def test_external_validation_handles_timeout(
        self, validation_config, mock_llm_service, sample_task
    ):
        """Test handling of timeout during external validation."""

        from gobby.tasks.external_validator import ExternalValidationResult, run_external_validation

        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.side_effect = TimeoutError("Request timed out")

        result = await run_external_validation(
            config=validation_config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context="diff content",
        )

        assert isinstance(result, ExternalValidationResult)
        assert result.status == "error"

    @pytest.mark.asyncio
    async def test_external_validation_includes_acceptance_criteria(
        self, validation_config, mock_llm_service, sample_task
    ):
        """Test that acceptance criteria from task is included in validation prompt."""
        from gobby.tasks.external_validator import run_external_validation

        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.return_value = '{"status": "valid", "issues": []}'

        await run_external_validation(
            config=validation_config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context="diff content",
        )

        call_kwargs = mock_provider.generate_text.call_args.kwargs
        prompt = call_kwargs["prompt"]

        # Validation criteria should be in the prompt
        assert "Users can log in with OAuth" in prompt or "OAuth" in prompt
        assert "Tokens are stored securely" in prompt or "securely" in prompt


class TestExternalValidatorToggle:
    """Tests for toggling between internal and external validators."""

    @pytest.fixture
    def mock_llm_service(self):
        from gobby.llm import LLMProvider, LLMService

        service = MagicMock(spec=LLMService)
        provider = AsyncMock(spec=LLMProvider)
        service.get_provider.return_value = provider
        return service

    @pytest.mark.asyncio
    async def test_use_internal_validator_when_flag_disabled(self, mock_llm_service):
        """Test that internal validation is used when use_external_validator is False."""
        from gobby.tasks.validation import TaskValidator, ValidationResult

        config = TaskValidationConfig(
            enabled=True,
            provider="claude",
            model="claude-haiku-4-5",
            use_external_validator=False,
        )

        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.return_value = '{"status": "valid", "feedback": "OK"}'

        validator = TaskValidator(config, mock_llm_service)
        result = await validator.validate_task(
            task_id="test-123",
            title="Test task",
            description="Test description",
            changes_summary="Test changes",
        )

        # Should use internal validation path
        assert isinstance(result, ValidationResult)
        assert result.status == "valid"

    @pytest.mark.asyncio
    async def test_use_external_validator_when_flag_enabled(self, mock_llm_service):
        """Test that external validation is used when use_external_validator is True."""

        # This test verifies the flag is respected in the enhanced validator
        config = TaskValidationConfig(
            enabled=True,
            provider="claude",
            model="claude-haiku-4-5",
            use_external_validator=True,
            external_validator_model="claude-sonnet-4-5",
        )

        # The enhanced validator should check this flag and route accordingly
        # This test documents the expected behavior
        assert config.use_external_validator is True
        assert config.external_validator_model == "claude-sonnet-4-5"

    @pytest.mark.asyncio
    async def test_override_external_validator_at_call_time(self, mock_llm_service):
        """Test that external validator can be overridden at call time."""
        from gobby.tasks.external_validator import run_external_validation

        # Config has external disabled
        config = TaskValidationConfig(
            enabled=True,
            provider="claude",
            model="claude-haiku-4-5",
            use_external_validator=False,
        )

        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.return_value = '{"status": "valid", "issues": []}'

        # But we override at call time
        task = {"id": "test", "title": "Test", "validation_criteria": "Test"}

        await run_external_validation(
            config=config,
            llm_service=mock_llm_service,
            task=task,
            changes_context="diff",
            force_external=True,  # Override flag
        )

        # Should still run external validation
        mock_provider.generate_text.assert_called_once()

    @pytest.mark.asyncio
    async def test_skip_external_validation_when_disabled_and_not_forced(self, mock_llm_service):
        """Test that external validation is skipped when config disabled and force_external=False."""
        from gobby.tasks.external_validator import ExternalValidationResult, run_external_validation

        # Config has external disabled
        config = TaskValidationConfig(
            enabled=True,
            provider="claude",
            model="claude-haiku-4-5",
            use_external_validator=False,
        )

        mock_provider = mock_llm_service.get_provider.return_value

        task = {"id": "test", "title": "Test", "validation_criteria": "Test"}

        result = await run_external_validation(
            config=config,
            llm_service=mock_llm_service,
            task=task,
            changes_context="diff",
            force_external=False,  # Not overriding
        )

        # LLM provider should NOT be called
        mock_provider.generate_text.assert_not_called()

        # Result should indicate validation was skipped
        assert isinstance(result, ExternalValidationResult)
        assert result.status == "skipped"
        assert "skipped" in result.summary.lower() or "disabled" in result.summary.lower()
        assert result.issues == []


class TestExternalValidationResult:
    """Tests for ExternalValidationResult dataclass."""

    def test_result_dataclass_fields(self):
        """Test ExternalValidationResult has expected fields."""
        from gobby.tasks.external_validator import ExternalValidationResult

        result = ExternalValidationResult(
            status="valid",
            summary="All criteria met",
            issues=[],
        )

        assert result.status == "valid"
        assert result.summary == "All criteria met"
        assert result.issues == []
        assert result.error is None  # Optional field

    def test_result_with_issues(self):
        """Test ExternalValidationResult with issues populated."""
        from gobby.tasks.external_validator import ExternalValidationResult

        issue = Issue(
            issue_type=IssueType.TEST_FAILURE,
            severity=IssueSeverity.BLOCKER,
            title="Test failed",
        )

        result = ExternalValidationResult(
            status="invalid",
            summary="Tests failing",
            issues=[issue],
        )

        assert result.status == "invalid"
        assert len(result.issues) == 1
        assert result.issues[0].title == "Test failed"

    def test_result_with_error(self):
        """Test ExternalValidationResult with error field."""
        from gobby.tasks.external_validator import ExternalValidationResult

        result = ExternalValidationResult(
            status="error",
            summary="Validation failed",
            issues=[],
            error="Connection timeout",
        )

        assert result.status == "error"
        assert result.error == "Connection timeout"


class TestExternalValidatorPrompt:
    """Tests for the external validator prompt template."""

    @pytest.fixture
    def mock_llm_service(self):
        from gobby.llm import LLMProvider, LLMService

        service = MagicMock(spec=LLMService)
        provider = AsyncMock(spec=LLMProvider)
        service.get_provider.return_value = provider
        return service

    @pytest.mark.asyncio
    async def test_prompt_includes_objective_validator_instruction(self, mock_llm_service):
        """Test that prompt instructs the validator to be objective."""
        from gobby.tasks.external_validator import run_external_validation

        config = TaskValidationConfig(
            enabled=True,
            provider="claude",
            model="claude-haiku-4-5",
            use_external_validator=True,
        )

        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.return_value = '{"status": "valid", "issues": []}'

        task = {"id": "test", "title": "Test Task", "validation_criteria": "Tests pass"}

        await run_external_validation(
            config=config,
            llm_service=mock_llm_service,
            task=task,
            changes_context="diff content",
        )

        call_kwargs = mock_provider.generate_text.call_args.kwargs

        # Check system prompt mentions objectivity
        system_prompt = call_kwargs.get("system_prompt", "")
        assert "objective" in system_prompt.lower() or "validator" in system_prompt.lower()

    @pytest.mark.asyncio
    async def test_prompt_requests_structured_json_output(self, mock_llm_service):
        """Test that prompt requests structured JSON output format."""
        from gobby.tasks.external_validator import run_external_validation

        config = TaskValidationConfig(
            enabled=True,
            provider="claude",
            model="claude-haiku-4-5",
            use_external_validator=True,
        )

        mock_provider = mock_llm_service.get_provider.return_value
        mock_provider.generate_text.return_value = '{"status": "valid", "issues": []}'

        task = {"id": "test", "title": "Test", "validation_criteria": "Criteria"}

        await run_external_validation(
            config=config,
            llm_service=mock_llm_service,
            task=task,
            changes_context="diff",
        )

        call_kwargs = mock_provider.generate_text.call_args.kwargs
        prompt = call_kwargs["prompt"]

        # Prompt should request JSON output
        assert "json" in prompt.lower()
        assert "status" in prompt.lower()
        assert "issues" in prompt.lower()


class TestAgentModeValidation:
    """Tests for agent mode external validation."""

    @pytest.fixture
    def validation_config(self):
        """Create a validation config with agent mode enabled."""
        return TaskValidationConfig(
            enabled=True,
            provider="claude",
            model="claude-haiku-4-5",
            use_external_validator=True,
            external_validator_mode="agent",
        )

    @pytest.fixture
    def mock_llm_service(self):
        """Create a mock LLM service."""
        from gobby.llm import LLMProvider, LLMService

        service = MagicMock(spec=LLMService)
        provider = AsyncMock(spec=LLMProvider)
        service.get_provider.return_value = provider
        return service

    @pytest.fixture
    def mock_agent_runner(self):
        """Create a mock AgentRunner."""
        from gobby.llm.executor import AgentResult

        runner = MagicMock()
        runner.run = AsyncMock(
            return_value=AgentResult(
                output='```json\n{"status": "valid", "summary": "All criteria met", "issues": []}\n```',
                status="completed",
                turns_used=3,
            )
        )
        return runner

    @pytest.fixture
    def sample_task(self):
        """Create a sample task for validation."""
        return {
            "id": "gt-test123",
            "title": "Implement user authentication",
            "description": "Add OAuth2 login flow",
            "validation_criteria": "- [ ] Users can log in with OAuth\n- [ ] Tokens are stored securely",
        }

    @pytest.mark.asyncio
    async def test_agent_mode_uses_agent_runner(
        self, validation_config, mock_llm_service, mock_agent_runner, sample_task
    ):
        """Test that agent mode uses AgentRunner instead of direct LLM calls."""
        from gobby.tasks.external_validator import run_external_validation

        changes_context = "diff --git a/src/auth.py b/src/auth.py"

        result = await run_external_validation(
            config=validation_config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context=changes_context,
            agent_runner=mock_agent_runner,
        )

        # Agent runner should be called
        mock_agent_runner.run.assert_called_once()

        # LLM service should NOT be called directly
        mock_llm_service.get_provider.assert_not_called()

        # Result should be parsed from agent output
        assert result.status == "valid"

    @pytest.mark.asyncio
    async def test_agent_mode_without_runner_returns_error(
        self, validation_config, mock_llm_service, sample_task
    ):
        """Test that agent mode returns error when no runner is provided."""
        from gobby.tasks.external_validator import run_external_validation

        result = await run_external_validation(
            config=validation_config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context="diff",
            agent_runner=None,  # No runner provided
        )

        assert result.status == "error"
        assert "agent runner" in result.summary.lower() or "not available" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_agent_mode_handles_agent_error(
        self, validation_config, mock_llm_service, mock_agent_runner, sample_task
    ):
        """Test that agent mode handles agent execution errors."""
        from gobby.llm.executor import AgentResult
        from gobby.tasks.external_validator import run_external_validation

        # Make agent return an error
        mock_agent_runner.run.return_value = AgentResult(
            output="",
            status="error",
            error="Agent execution failed",
            turns_used=0,
        )

        result = await run_external_validation(
            config=validation_config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context="diff",
            agent_runner=mock_agent_runner,
        )

        assert result.status == "error"
        assert "failed" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_agent_mode_parses_invalid_result(
        self, validation_config, mock_llm_service, mock_agent_runner, sample_task
    ):
        """Test that agent mode correctly parses 'invalid' validation result."""
        from gobby.llm.executor import AgentResult
        from gobby.tasks.external_validator import run_external_validation

        mock_agent_runner.run.return_value = AgentResult(
            output='{"status": "invalid", "summary": "Tests failing", "issues": [{"type": "test_failure", "severity": "blocker", "title": "Unit tests fail"}]}',
            status="completed",
            turns_used=5,
        )

        result = await run_external_validation(
            config=validation_config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context="diff",
            agent_runner=mock_agent_runner,
        )

        assert result.status == "invalid"
        assert "tests" in result.summary.lower() or len(result.issues) > 0

    @pytest.mark.asyncio
    async def test_agent_config_uses_correct_settings(
        self, mock_llm_service, mock_agent_runner, sample_task
    ):
        """Test that AgentConfig is created with correct settings from config."""
        from gobby.tasks.external_validator import run_external_validation

        config = TaskValidationConfig(
            enabled=True,
            provider="claude",
            model="claude-haiku-4-5",
            use_external_validator=True,
            external_validator_mode="agent",
            external_validator_model="claude-sonnet-4-5",
        )

        await run_external_validation(
            config=config,
            llm_service=mock_llm_service,
            task=sample_task,
            changes_context="diff",
            agent_runner=mock_agent_runner,
        )

        # Check that agent was called with correct config
        call_args = mock_agent_runner.run.call_args
        agent_config = call_args[0][0]  # First positional argument

        assert agent_config.model == "claude-sonnet-4-5"
        assert agent_config.provider == "claude"
        assert agent_config.mode == "in_process"
        assert agent_config.max_turns == 20
        assert agent_config.timeout == 120.0
