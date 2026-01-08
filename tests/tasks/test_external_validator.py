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


class TestAgentSpawnValidation:
    """Tests for external validation via spawned agent process.

    TDD Red Phase: These tests verify that when external_validator_mode="spawn",
    a separate agent process is spawned via gobby-agents.start_agent rather than
    using an in-process AgentRunner. The implementation does not exist yet.

    Task: gt-09277c
    """

    @pytest.fixture
    def validation_config_spawn(self):
        """Create a validation config with agent spawn mode enabled."""
        return TaskValidationConfig(
            enabled=True,
            provider="claude",
            model="claude-haiku-4-5",
            use_external_validator=True,
            external_validator_mode="spawn",  # Spawn separate process
            external_validator_model="claude-sonnet-4-5",
        )

    @pytest.fixture
    def mock_agent_spawner(self):
        """Mock the gobby-agents spawner interface."""
        spawner = MagicMock()
        spawner.start_agent = AsyncMock(
            return_value={
                "success": True,
                "agent_id": "agent-validator-123",
                "status": "running",
            }
        )
        spawner.get_agent_result = AsyncMock(
            return_value={
                "success": True,
                "status": "completed",
                "output": '{"status": "valid", "summary": "All criteria met", "issues": []}',
            }
        )
        return spawner

    @pytest.fixture
    def sample_task(self):
        """Create a sample task for validation."""
        return {
            "id": "gt-test456",
            "title": "Implement secure file upload",
            "description": "Add file upload with virus scanning",
            "validation_criteria": "- [ ] Files are scanned for viruses\n- [ ] Upload size limit enforced",
        }

    @pytest.mark.asyncio
    async def test_spawn_mode_invokes_agent_spawner(
        self, validation_config_spawn, mock_agent_spawner, sample_task
    ):
        """Test that spawn mode invokes gobby-agents.start_agent."""
        from gobby.tasks.external_validator import run_external_validation

        result = await run_external_validation(
            config=validation_config_spawn,
            llm_service=None,  # Not used in spawn mode
            task=sample_task,
            changes_context="diff --git a/src/upload.py",
            agent_spawner=mock_agent_spawner,
        )

        # Agent spawner should be invoked
        mock_agent_spawner.start_agent.assert_called_once()

        # Should poll for result
        mock_agent_spawner.get_agent_result.assert_called()

        # Result should be parsed
        assert result.status == "valid"

    @pytest.mark.asyncio
    async def test_spawn_mode_uses_headless_mode(
        self, validation_config_spawn, mock_agent_spawner, sample_task
    ):
        """Test that spawned agent uses headless mode (no terminal UI)."""
        from gobby.tasks.external_validator import run_external_validation

        await run_external_validation(
            config=validation_config_spawn,
            llm_service=None,
            task=sample_task,
            changes_context="diff content",
            agent_spawner=mock_agent_spawner,
        )

        call_kwargs = mock_agent_spawner.start_agent.call_args.kwargs
        assert call_kwargs.get("mode") == "headless"

    @pytest.mark.asyncio
    async def test_spawn_mode_passes_correct_model(
        self, validation_config_spawn, mock_agent_spawner, sample_task
    ):
        """Test that spawned agent uses external_validator_model."""
        from gobby.tasks.external_validator import run_external_validation

        await run_external_validation(
            config=validation_config_spawn,
            llm_service=None,
            task=sample_task,
            changes_context="diff content",
            agent_spawner=mock_agent_spawner,
        )

        call_kwargs = mock_agent_spawner.start_agent.call_args.kwargs
        assert call_kwargs.get("model") == "claude-sonnet-4-5"

    @pytest.mark.asyncio
    async def test_spawn_mode_creates_validation_prompt(
        self, validation_config_spawn, mock_agent_spawner, sample_task
    ):
        """Test that spawned agent receives validation-specific prompt."""
        from gobby.tasks.external_validator import run_external_validation

        await run_external_validation(
            config=validation_config_spawn,
            llm_service=None,
            task=sample_task,
            changes_context="diff --git a/src/upload.py",
            agent_spawner=mock_agent_spawner,
        )

        call_kwargs = mock_agent_spawner.start_agent.call_args.kwargs
        prompt = call_kwargs.get("prompt", "")

        # Prompt should contain validation instructions
        assert "validat" in prompt.lower()  # validate/validation/validator
        assert sample_task["id"] in prompt or sample_task["title"] in prompt
        assert "criteria" in prompt.lower()

    @pytest.mark.asyncio
    async def test_spawn_mode_includes_changes_context(
        self, validation_config_spawn, mock_agent_spawner, sample_task
    ):
        """Test that spawned agent prompt includes changes context."""
        from gobby.tasks.external_validator import run_external_validation

        changes = "diff --git a/src/upload.py b/src/upload.py\n+def scan_file():"

        await run_external_validation(
            config=validation_config_spawn,
            llm_service=None,
            task=sample_task,
            changes_context=changes,
            agent_spawner=mock_agent_spawner,
        )

        call_kwargs = mock_agent_spawner.start_agent.call_args.kwargs
        prompt = call_kwargs.get("prompt", "")

        # Changes should be included
        assert "diff" in prompt.lower() or "upload.py" in prompt

    @pytest.mark.asyncio
    async def test_spawn_mode_sets_max_turns(
        self, validation_config_spawn, mock_agent_spawner, sample_task
    ):
        """Test that spawned agent has limited max_turns."""
        from gobby.tasks.external_validator import run_external_validation

        await run_external_validation(
            config=validation_config_spawn,
            llm_service=None,
            task=sample_task,
            changes_context="diff",
            agent_spawner=mock_agent_spawner,
        )

        call_kwargs = mock_agent_spawner.start_agent.call_args.kwargs
        # Validator should have limited turns (single-shot or few turns)
        max_turns = call_kwargs.get("max_turns")
        assert max_turns is not None
        assert int(max_turns) <= 10  # Validation shouldn't need many turns

    @pytest.mark.asyncio
    async def test_spawn_mode_without_spawner_returns_error(
        self, validation_config_spawn, sample_task
    ):
        """Test that spawn mode returns error when no spawner is available."""
        from gobby.tasks.external_validator import run_external_validation

        result = await run_external_validation(
            config=validation_config_spawn,
            llm_service=None,
            task=sample_task,
            changes_context="diff",
            agent_spawner=None,  # No spawner
        )

        assert result.status == "error"
        assert "spawn" in result.summary.lower() or "not available" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_spawn_mode_handles_spawn_failure(
        self, validation_config_spawn, mock_agent_spawner, sample_task
    ):
        """Test that spawn mode handles agent spawn failures."""
        from gobby.tasks.external_validator import run_external_validation

        mock_agent_spawner.start_agent.return_value = {
            "success": False,
            "error": "Failed to spawn agent",
        }

        result = await run_external_validation(
            config=validation_config_spawn,
            llm_service=None,
            task=sample_task,
            changes_context="diff",
            agent_spawner=mock_agent_spawner,
        )

        assert result.status == "error"
        assert "spawn" in result.summary.lower() or "failed" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_spawn_mode_handles_agent_timeout(
        self, validation_config_spawn, mock_agent_spawner, sample_task
    ):
        """Test that spawn mode handles agent execution timeout."""
        from gobby.tasks.external_validator import run_external_validation

        mock_agent_spawner.get_agent_result.return_value = {
            "success": False,
            "status": "timeout",
            "error": "Agent execution timed out",
        }

        result = await run_external_validation(
            config=validation_config_spawn,
            llm_service=None,
            task=sample_task,
            changes_context="diff",
            agent_spawner=mock_agent_spawner,
        )

        assert result.status == "error"
        assert "timeout" in result.summary.lower() or "timed out" in result.summary.lower()

    @pytest.mark.asyncio
    async def test_spawn_mode_parses_invalid_result(
        self, validation_config_spawn, mock_agent_spawner, sample_task
    ):
        """Test that spawn mode correctly parses 'invalid' result from agent."""
        from gobby.tasks.external_validator import run_external_validation

        mock_agent_spawner.get_agent_result.return_value = {
            "success": True,
            "status": "completed",
            "output": '{"status": "invalid", "summary": "Missing virus scanning", "issues": [{"type": "acceptance_gap", "severity": "major", "title": "No virus scan implemented"}]}',
        }

        result = await run_external_validation(
            config=validation_config_spawn,
            llm_service=None,
            task=sample_task,
            changes_context="diff",
            agent_spawner=mock_agent_spawner,
        )

        assert result.status == "invalid"
        assert len(result.issues) >= 1

    @pytest.mark.asyncio
    async def test_spawn_mode_agent_runs_in_separate_context(
        self, validation_config_spawn, mock_agent_spawner, sample_task
    ):
        """Test that spawned agent does not share context with implementation agent.

        This is critical: the validator must not see the implementation agent's
        conversation history to avoid bias.
        """
        from gobby.tasks.external_validator import run_external_validation

        await run_external_validation(
            config=validation_config_spawn,
            llm_service=None,
            task=sample_task,
            changes_context="diff",
            agent_spawner=mock_agent_spawner,
        )

        call_kwargs = mock_agent_spawner.start_agent.call_args.kwargs

        # Should not pass parent_session_id (no context inheritance)
        # or should explicitly pass session_context=None
        assert call_kwargs.get("parent_session_id") is None
        assert call_kwargs.get("session_context") in (None, "", "none")

    @pytest.mark.asyncio
    async def test_spawn_mode_agent_has_validator_system_prompt(
        self, validation_config_spawn, mock_agent_spawner, sample_task
    ):
        """Test that spawned agent receives validator-specific system instructions.

        The validator should be instructed to:
        1. Be objective and adversarial
        2. Not assume success
        3. Verify each criterion independently
        """
        from gobby.tasks.external_validator import run_external_validation

        await run_external_validation(
            config=validation_config_spawn,
            llm_service=None,
            task=sample_task,
            changes_context="diff",
            agent_spawner=mock_agent_spawner,
        )

        call_kwargs = mock_agent_spawner.start_agent.call_args.kwargs
        prompt = call_kwargs.get("prompt", "")

        # System prompt should instruct objectivity
        prompt_lower = prompt.lower()
        assert any(
            word in prompt_lower
            for word in ["objective", "adversarial", "critical", "independently", "verify"]
        )
