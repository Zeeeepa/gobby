"""Tests for provider resolution logic."""

from unittest.mock import MagicMock, patch

import pytest

# Import the resolver module directly - it doesn't import executors at module level
from gobby.llm.resolver import (
    DEFAULT_PROVIDER,
    ExecutorCreationError,
    ExecutorRegistry,
    InvalidProviderError,
    MissingProviderError,
    ProviderNotConfiguredError,
    ResolvedProvider,
    create_executor,
    resolve_provider,
    validate_provider_name,
)


class TestValidateProviderName:
    """Tests for validate_provider_name function."""

    def test_valid_provider_names(self):
        """Test that valid provider names pass validation."""
        assert validate_provider_name("claude") == "claude"
        assert validate_provider_name("gemini") == "gemini"
        assert validate_provider_name("litellm") == "litellm"
        assert validate_provider_name("openai") == "openai"
        assert validate_provider_name("claude-3") == "claude-3"
        assert validate_provider_name("my_provider") == "my_provider"
        assert validate_provider_name("Provider123") == "Provider123"

    def test_none_raises_error(self):
        """Test that None raises InvalidProviderError."""
        with pytest.raises(InvalidProviderError) as exc_info:
            validate_provider_name(None)

        assert exc_info.value.provider is None
        assert "None" in str(exc_info.value)

    def test_empty_string_raises_error(self):
        """Test that empty string raises InvalidProviderError."""
        with pytest.raises(InvalidProviderError) as exc_info:
            validate_provider_name("")

        assert "empty" in exc_info.value.reason.lower()

    def test_whitespace_only_raises_error(self):
        """Test that whitespace-only string raises InvalidProviderError."""
        with pytest.raises(InvalidProviderError):
            validate_provider_name("   ")

    def test_strips_whitespace(self):
        """Test that leading/trailing whitespace is stripped."""
        # Valid after stripping
        assert validate_provider_name("  claude  ") == "claude"

    def test_too_long_raises_error(self):
        """Test that names over 64 characters raise InvalidProviderError."""
        long_name = "a" * 65
        with pytest.raises(InvalidProviderError) as exc_info:
            validate_provider_name(long_name)

        assert "64" in str(exc_info.value)

    def test_max_length_accepted(self):
        """Test that 64 character names are accepted."""
        name_64 = "a" * 64
        assert validate_provider_name(name_64) == name_64

    def test_special_characters_rejected(self):
        """Test that special characters are rejected."""
        invalid_names = [
            "provider@v1",
            "provider/openai",
            "my provider",
            "provider.name",
            "provider!",
            "provider#1",
        ]

        for name in invalid_names:
            with pytest.raises(InvalidProviderError):
                validate_provider_name(name)

    def test_numeric_only_accepted(self):
        """Test that numeric-only names are accepted."""
        assert validate_provider_name("123") == "123"


class TestResolveProvider:
    """Tests for resolve_provider function."""

    def test_explicit_provider_highest_priority(self):
        """Test that explicit provider has highest priority."""
        result = resolve_provider(explicit_provider="gemini")

        assert isinstance(result, ResolvedProvider)
        assert result.provider == "gemini"
        assert result.source == "explicit"

    def test_workflow_provider_second_priority(self):
        """Test that workflow provider has second priority."""
        # Create mock workflow
        mock_workflow = MagicMock()
        mock_workflow.variables = {"provider": "litellm", "model": "gpt-4o"}

        result = resolve_provider(workflow=mock_workflow)

        assert result.provider == "litellm"
        assert result.source == "workflow"
        assert result.model == "gpt-4o"

    def test_config_provider_third_priority(self):
        """Test that config provider has third priority."""
        # Create mock config
        mock_config = MagicMock()
        mock_config.llm_providers.get_enabled_providers.return_value = ["gemini", "litellm"]

        result = resolve_provider(config=mock_config)

        # Should prefer claude if available, otherwise first
        assert result.provider == "gemini"
        assert result.source == "config"

    def test_config_prefers_claude(self):
        """Test that config prefers claude when available."""
        mock_config = MagicMock()
        mock_config.llm_providers.get_enabled_providers.return_value = [
            "gemini",
            "claude",
            "litellm",
        ]

        result = resolve_provider(config=mock_config)

        assert result.provider == "claude"
        assert result.source == "config"

    def test_default_provider_lowest_priority(self):
        """Test that default is used when nothing else is available."""
        result = resolve_provider()

        assert result.provider == DEFAULT_PROVIDER
        assert result.source == "default"

    def test_explicit_overrides_workflow(self):
        """Test that explicit provider overrides workflow."""
        mock_workflow = MagicMock()
        mock_workflow.variables = {"provider": "litellm"}

        result = resolve_provider(explicit_provider="claude", workflow=mock_workflow)

        assert result.provider == "claude"
        assert result.source == "explicit"

    def test_workflow_overrides_config(self):
        """Test that workflow overrides config."""
        mock_workflow = MagicMock()
        mock_workflow.variables = {"provider": "litellm"}

        mock_config = MagicMock()
        mock_config.llm_providers.get_enabled_providers.return_value = ["claude", "litellm"]

        result = resolve_provider(workflow=mock_workflow, config=mock_config)

        assert result.provider == "litellm"
        assert result.source == "workflow"

    def test_validates_explicit_provider(self):
        """Test that explicit provider is validated."""
        with pytest.raises(InvalidProviderError):
            resolve_provider(explicit_provider="invalid/provider")

    def test_validates_against_config(self):
        """Test provider validation against config when not allow_unconfigured."""
        mock_config = MagicMock()
        mock_config.llm_providers.get_enabled_providers.return_value = ["claude"]

        with pytest.raises(ProviderNotConfiguredError) as exc_info:
            resolve_provider(
                explicit_provider="gemini",
                config=mock_config,
                allow_unconfigured=False,
            )

        assert exc_info.value.provider == "gemini"
        assert "claude" in exc_info.value.available

    def test_allow_unconfigured_skips_validation(self):
        """Test that allow_unconfigured=True skips config validation."""
        mock_config = MagicMock()
        mock_config.llm_providers.get_enabled_providers.return_value = ["claude"]

        # Should not raise
        result = resolve_provider(
            explicit_provider="gemini",
            config=mock_config,
            allow_unconfigured=True,
        )

        assert result.provider == "gemini"


class TestCreateExecutor:
    """Tests for create_executor function."""

    def test_create_claude_executor(self):
        """Test creating a Claude executor."""
        with patch("gobby.llm.resolver._create_claude_executor") as mock_create:
            mock_executor = MagicMock()
            mock_executor.provider_name = "claude"
            mock_create.return_value = mock_executor

            executor = create_executor("claude")

            assert executor.provider_name == "claude"
            mock_create.assert_called_once()

    def test_create_gemini_executor(self):
        """Test creating a Gemini executor."""
        with patch("gobby.llm.resolver._create_gemini_executor") as mock_create:
            mock_executor = MagicMock()
            mock_executor.provider_name = "gemini"
            mock_create.return_value = mock_executor

            executor = create_executor("gemini")

            assert executor.provider_name == "gemini"
            mock_create.assert_called_once()

    def test_create_litellm_executor(self):
        """Test creating a LiteLLM executor."""
        with patch("gobby.llm.resolver._create_litellm_executor") as mock_create:
            mock_executor = MagicMock()
            mock_executor.provider_name = "litellm"
            mock_create.return_value = mock_executor

            executor = create_executor("litellm")

            assert executor.provider_name == "litellm"
            mock_create.assert_called_once()

    def test_unknown_provider_raises_error(self):
        """Test that unknown provider raises ExecutorCreationError."""
        with pytest.raises(ExecutorCreationError) as exc_info:
            create_executor("unknown-provider")

        assert exc_info.value.provider == "unknown-provider"
        assert "Unknown provider" in str(exc_info.value)

    def test_invalid_provider_raises_error(self):
        """Test that invalid provider name raises InvalidProviderError."""
        with pytest.raises(InvalidProviderError):
            create_executor("invalid/provider")

    def test_uses_model_override(self):
        """Test that model override is passed to executor."""
        with patch("gobby.llm.resolver._create_claude_executor") as mock_create:
            mock_executor = MagicMock()
            mock_create.return_value = mock_executor

            create_executor("claude", model="claude-opus-4-20250514")

            # Check that model was passed (positional arg at index 1)
            call_args = mock_create.call_args
            # _create_claude_executor(provider_config, model) - model is at position 1
            assert call_args[0][1] == "claude-opus-4-20250514"

    def test_uses_config_model(self):
        """Test that config model is used when no override."""
        mock_config = MagicMock()
        mock_provider_config = MagicMock()
        mock_provider_config.models = "claude-haiku-4-5,claude-sonnet-4-5"
        mock_provider_config.auth_mode = "api_key"
        mock_config.llm_providers.claude = mock_provider_config

        with patch("gobby.llm.resolver._create_claude_executor") as mock_create:
            mock_executor = MagicMock()
            mock_create.return_value = mock_executor

            create_executor("claude", config=mock_config)

            # Verify provider config was passed
            mock_create.assert_called_once()


class TestExecutorRegistry:
    """Tests for ExecutorRegistry class."""

    def test_get_creates_executor(self):
        """Test that get() creates an executor."""
        with patch("gobby.llm.resolver.create_executor") as mock_create:
            mock_executor = MagicMock()
            mock_executor.provider_name = "claude"
            mock_create.return_value = mock_executor

            registry = ExecutorRegistry()
            executor = registry.get(provider="claude")

            assert executor.provider_name == "claude"
            mock_create.assert_called_once()

    def test_get_caches_executor(self):
        """Test that get() caches executors."""
        with patch("gobby.llm.resolver.create_executor") as mock_create:
            mock_executor = MagicMock()
            mock_executor.provider_name = "claude"
            mock_create.return_value = mock_executor

            registry = ExecutorRegistry()
            executor1 = registry.get(provider="claude")
            executor2 = registry.get(provider="claude")

            assert executor1 is executor2
            # Should only create once
            assert mock_create.call_count == 1

    def test_get_different_providers(self):
        """Test getting different providers."""
        with patch("gobby.llm.resolver.create_executor") as mock_create:
            claude_executor = MagicMock()
            claude_executor.provider_name = "claude"

            gemini_executor = MagicMock()
            gemini_executor.provider_name = "gemini"

            mock_create.side_effect = [claude_executor, gemini_executor]

            registry = ExecutorRegistry()
            result1 = registry.get(provider="claude")
            result2 = registry.get(provider="gemini")

            assert result1.provider_name == "claude"
            assert result2.provider_name == "gemini"
            assert result1 is not result2

    def test_get_resolves_from_workflow(self):
        """Test that get() resolves from workflow."""
        with patch("gobby.llm.resolver.create_executor") as mock_create:
            mock_executor = MagicMock()
            mock_executor.provider_name = "litellm"
            mock_create.return_value = mock_executor

            mock_workflow = MagicMock()
            mock_workflow.variables = {"provider": "litellm"}

            registry = ExecutorRegistry()
            executor = registry.get(workflow=mock_workflow)

            assert executor.provider_name == "litellm"

    def test_get_all_returns_cached(self):
        """Test that get_all() returns cached executors."""
        with patch("gobby.llm.resolver.create_executor") as mock_create:
            mock_executor = MagicMock()
            mock_create.return_value = mock_executor

            registry = ExecutorRegistry()
            registry.get(provider="claude")

            all_executors = registry.get_all()

            assert len(all_executors) == 1
            assert any("claude" in key for key in all_executors)

    def test_clear_cache(self):
        """Test that clear_cache() clears executors."""
        with patch("gobby.llm.resolver.create_executor") as mock_create:
            mock_executor = MagicMock()
            mock_create.return_value = mock_executor

            registry = ExecutorRegistry()
            registry.get(provider="claude")

            assert len(registry.get_all()) == 1

            registry.clear_cache()

            assert len(registry.get_all()) == 0


class TestExceptionTypes:
    """Tests for exception types."""

    def test_invalid_provider_error_fields(self):
        """Test InvalidProviderError has correct fields."""
        error = InvalidProviderError("bad-provider", "invalid characters")

        assert error.provider == "bad-provider"
        assert error.reason == "invalid characters"
        assert "bad-provider" in str(error)
        assert "invalid characters" in str(error)

    def test_missing_provider_error_fields(self):
        """Test MissingProviderError has correct fields."""
        error = MissingProviderError(["explicit", "workflow", "config"])

        assert error.checked_levels == ["explicit", "workflow", "config"]
        assert "explicit" in str(error)
        assert "workflow" in str(error)
        assert "config" in str(error)

    def test_provider_not_configured_error_fields(self):
        """Test ProviderNotConfiguredError has correct fields."""
        error = ProviderNotConfiguredError("gemini", ["claude", "litellm"])

        assert error.provider == "gemini"
        assert error.available == ["claude", "litellm"]
        assert "gemini" in str(error)
        assert "claude" in str(error)

    def test_executor_creation_error_fields(self):
        """Test ExecutorCreationError has correct fields."""
        error = ExecutorCreationError("claude", "API key missing")

        assert error.provider == "claude"
        assert error.reason == "API key missing"
        assert "claude" in str(error)
        assert "API key missing" in str(error)


class TestCreateClaudeExecutorIntegration:
    """Integration tests for _create_claude_executor."""

    def test_creates_executor_with_api_key(self):
        """Test creating Claude executor with API key."""
        import sys
        from unittest.mock import MagicMock, patch

        # Mock anthropic module
        mock_anthropic = MagicMock()

        with patch.dict(sys.modules, {"anthropic": mock_anthropic, "anthropic.types": MagicMock()}):
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                # Re-import to get fresh module
                from gobby.llm.resolver import _create_claude_executor

                executor = _create_claude_executor(None, None)

                assert executor.provider_name == "claude"
                assert executor.auth_mode == "api_key"


class TestCreateGeminiExecutorIntegration:
    """Integration tests for _create_gemini_executor."""

    def test_creates_executor_with_api_key(self):
        """Test creating Gemini executor with API key."""
        import sys
        from unittest.mock import MagicMock, patch

        # Mock google modules
        mock_genai = MagicMock()

        with patch.dict(
            sys.modules,
            {
                "google": MagicMock(),
                "google.generativeai": mock_genai,
                "google.auth": MagicMock(),
            },
        ):
            with patch.dict("os.environ", {"GEMINI_API_KEY": "test-key"}):
                from gobby.llm.resolver import _create_gemini_executor

                executor = _create_gemini_executor(None, None)

                assert executor.provider_name == "gemini"
                assert executor.auth_mode == "api_key"


class TestCreateLitellmExecutorIntegration:
    """Integration tests for _create_litellm_executor."""

    def test_creates_executor(self):
        """Test creating LiteLLM executor."""
        import sys
        from unittest.mock import MagicMock, patch

        # Mock litellm module
        mock_litellm = MagicMock()

        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            from gobby.llm.resolver import _create_litellm_executor

            executor = _create_litellm_executor(None, None, None)

            assert executor.provider_name == "litellm"
