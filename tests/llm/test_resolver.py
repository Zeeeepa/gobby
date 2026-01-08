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


class TestCreateCodexExecutorIntegration:
    """Integration tests for _create_codex_executor."""

    def test_creates_executor_with_api_key(self):
        """Test creating Codex executor with API key."""
        import sys
        from unittest.mock import MagicMock, patch

        # Mock openai module
        mock_openai = MagicMock()

        with patch.dict(sys.modules, {"openai": mock_openai}):
            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                from gobby.llm.resolver import _create_codex_executor

                executor = _create_codex_executor(None, None)

                assert executor.provider_name == "codex"
                assert executor.auth_mode == "api_key"

    def test_creates_executor_with_provider_config(self):
        """Test creating Codex executor with provider config."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_openai = MagicMock()

        with patch.dict(sys.modules, {"openai": mock_openai}):
            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                # Mock shutil.which to return a path for 'codex'
                with patch("shutil.which", return_value="/usr/bin/codex"):
                    from gobby.llm.resolver import _create_codex_executor

                    mock_config = MagicMock()
                    mock_config.auth_mode = "subscription"
                    mock_config.models = "gpt-4-turbo, gpt-4o"

                    executor = _create_codex_executor(mock_config, None)

                    assert executor.provider_name == "codex"
                    assert executor.auth_mode == "subscription"
                    assert executor.default_model == "gpt-4-turbo"


class TestResolveProviderAdvanced:
    """Advanced tests for resolve_provider covering edge cases."""

    def test_workflow_provider_validates_against_config(self):
        """Test that workflow provider is validated against config."""
        mock_workflow = MagicMock()
        mock_workflow.variables = {"provider": "litellm"}

        mock_config = MagicMock()
        mock_config.llm_providers.get_enabled_providers.return_value = ["claude"]

        with pytest.raises(ProviderNotConfiguredError) as exc_info:
            resolve_provider(
                workflow=mock_workflow,
                config=mock_config,
                allow_unconfigured=False,
            )

        assert exc_info.value.provider == "litellm"
        assert "claude" in exc_info.value.available

    def test_workflow_with_non_string_model(self):
        """Test that non-string workflow model is ignored."""
        mock_workflow = MagicMock()
        mock_workflow.variables = {"provider": "claude", "model": 123}  # Non-string model

        result = resolve_provider(workflow=mock_workflow)

        assert result.provider == "claude"
        assert result.source == "workflow"
        assert result.model is None  # Should be None for non-string

    def test_workflow_with_none_model(self):
        """Test that None workflow model is handled correctly."""
        mock_workflow = MagicMock()
        mock_workflow.variables = {"provider": "claude", "model": None}

        result = resolve_provider(workflow=mock_workflow)

        assert result.provider == "claude"
        assert result.source == "workflow"
        assert result.model is None

    def test_workflow_without_provider(self):
        """Test workflow without provider falls through to config."""
        mock_workflow = MagicMock()
        mock_workflow.variables = {"other_setting": "value"}  # No provider

        mock_config = MagicMock()
        mock_config.llm_providers.get_enabled_providers.return_value = ["gemini"]

        result = resolve_provider(workflow=mock_workflow, config=mock_config)

        assert result.provider == "gemini"
        assert result.source == "config"

    def test_config_with_empty_enabled_providers(self):
        """Test config with empty enabled providers falls to default."""
        mock_config = MagicMock()
        mock_config.llm_providers.get_enabled_providers.return_value = []

        result = resolve_provider(config=mock_config)

        assert result.provider == DEFAULT_PROVIDER
        assert result.source == "default"

    def test_default_fallback_when_not_in_config(self):
        """Test that default fallback uses first enabled when default not configured."""
        mock_config = MagicMock()
        # Default is "claude" but only gemini and litellm are enabled
        mock_config.llm_providers.get_enabled_providers.return_value = ["gemini", "litellm"]

        result = resolve_provider(config=mock_config, allow_unconfigured=False)

        # Should return first enabled provider since default not available
        assert result.provider == "gemini"
        assert result.source == "config"

    def test_config_with_none_llm_providers(self):
        """Test config with None llm_providers falls to default."""
        mock_config = MagicMock()
        mock_config.llm_providers = None

        result = resolve_provider(config=mock_config)

        assert result.provider == DEFAULT_PROVIDER
        assert result.source == "default"


class TestCreateExecutorAdvanced:
    """Advanced tests for create_executor covering edge cases."""

    def test_create_codex_executor(self):
        """Test creating a Codex executor."""
        with patch("gobby.llm.resolver._create_codex_executor") as mock_create:
            mock_executor = MagicMock()
            mock_executor.provider_name = "codex"
            mock_create.return_value = mock_executor

            executor = create_executor("codex")

            assert executor.provider_name == "codex"
            mock_create.assert_called_once()

    def test_non_provider_error_wrapped(self):
        """Test that non-ProviderError exceptions are wrapped in ExecutorCreationError."""
        with patch("gobby.llm.resolver._create_claude_executor") as mock_create:
            mock_create.side_effect = RuntimeError("Unexpected error")

            with pytest.raises(ExecutorCreationError) as exc_info:
                create_executor("claude")

            assert exc_info.value.provider == "claude"
            assert "Unexpected error" in str(exc_info.value)
            assert exc_info.value.__cause__ is not None

    def test_provider_error_not_wrapped(self):
        """Test that ProviderError exceptions are not wrapped."""
        with patch("gobby.llm.resolver._create_claude_executor") as mock_create:
            mock_create.side_effect = InvalidProviderError("claude", "test reason")

            with pytest.raises(InvalidProviderError) as exc_info:
                create_executor("claude")

            assert exc_info.value.provider == "claude"
            assert exc_info.value.reason == "test reason"

    def test_create_executor_with_config_no_llm_providers(self):
        """Test create_executor when config has no llm_providers."""
        mock_config = MagicMock()
        mock_config.llm_providers = None

        with patch("gobby.llm.resolver._create_claude_executor") as mock_create:
            mock_executor = MagicMock()
            mock_create.return_value = mock_executor

            create_executor("claude", config=mock_config)

            # Should pass None as provider_config
            call_args = mock_create.call_args
            assert call_args[0][0] is None  # provider_config


class TestExecutorCreationWithConfig:
    """Tests for executor creation with provider config."""

    def test_claude_executor_with_models_config(self):
        """Test Claude executor uses first model from config."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_anthropic = MagicMock()

        with patch.dict(sys.modules, {"anthropic": mock_anthropic, "anthropic.types": MagicMock()}):
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                from gobby.llm.resolver import _create_claude_executor

                mock_config = MagicMock()
                mock_config.auth_mode = "api_key"
                mock_config.models = "claude-opus-4-5, claude-sonnet-4-5"

                executor = _create_claude_executor(mock_config, None)

                assert executor.default_model == "claude-opus-4-5"

    def test_claude_executor_model_override(self):
        """Test Claude executor model override takes precedence."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_anthropic = MagicMock()

        with patch.dict(sys.modules, {"anthropic": mock_anthropic, "anthropic.types": MagicMock()}):
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                from gobby.llm.resolver import _create_claude_executor

                mock_config = MagicMock()
                mock_config.auth_mode = "api_key"
                mock_config.models = "claude-sonnet-4-5"

                executor = _create_claude_executor(mock_config, "claude-opus-4-20250514")

                assert executor.default_model == "claude-opus-4-20250514"

    def test_claude_executor_with_empty_models(self):
        """Test Claude executor with empty models string uses default."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_anthropic = MagicMock()

        with patch.dict(sys.modules, {"anthropic": mock_anthropic, "anthropic.types": MagicMock()}):
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                from gobby.llm.resolver import _create_claude_executor

                mock_config = MagicMock()
                mock_config.auth_mode = "api_key"
                mock_config.models = ""  # Empty string

                executor = _create_claude_executor(mock_config, None)

                assert executor.default_model == "claude-sonnet-4-20250514"

    def test_claude_executor_with_whitespace_only_models(self):
        """Test Claude executor with whitespace-only models uses default."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_anthropic = MagicMock()

        with patch.dict(sys.modules, {"anthropic": mock_anthropic, "anthropic.types": MagicMock()}):
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                from gobby.llm.resolver import _create_claude_executor

                mock_config = MagicMock()
                mock_config.auth_mode = "api_key"
                mock_config.models = "  ,  ,  "  # Whitespace-only entries

                executor = _create_claude_executor(mock_config, None)

                assert executor.default_model == "claude-sonnet-4-20250514"

    def test_claude_executor_with_none_auth_mode(self):
        """Test Claude executor defaults auth_mode when None."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_anthropic = MagicMock()

        with patch.dict(sys.modules, {"anthropic": mock_anthropic, "anthropic.types": MagicMock()}):
            with patch.dict("os.environ", {"ANTHROPIC_API_KEY": "test-key"}):
                from gobby.llm.resolver import _create_claude_executor

                mock_config = MagicMock()
                mock_config.auth_mode = None  # Explicitly None
                mock_config.models = None

                executor = _create_claude_executor(mock_config, None)

                assert executor.auth_mode == "api_key"

    def test_gemini_executor_with_models_config(self):
        """Test Gemini executor uses first model from config."""
        import sys
        from unittest.mock import MagicMock, patch

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

                mock_config = MagicMock()
                mock_config.auth_mode = "api_key"
                mock_config.models = "gemini-1.5-pro, gemini-2.0-flash"

                executor = _create_gemini_executor(mock_config, None)

                assert executor.default_model == "gemini-1.5-pro"

    def test_gemini_executor_with_none_auth_mode(self):
        """Test Gemini executor defaults auth_mode when None."""
        import sys
        from unittest.mock import MagicMock, patch

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

                mock_config = MagicMock()
                mock_config.auth_mode = None
                mock_config.models = None

                executor = _create_gemini_executor(mock_config, None)

                assert executor.auth_mode == "api_key"

    def test_litellm_executor_with_models_config(self):
        """Test LiteLLM executor uses first model from config."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_litellm = MagicMock()

        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            from gobby.llm.resolver import _create_litellm_executor

            mock_provider_config = MagicMock()
            mock_provider_config.models = "gpt-4, gpt-4o-mini"
            mock_provider_config.api_base = None

            executor = _create_litellm_executor(mock_provider_config, None, None)

            assert executor.default_model == "gpt-4"

    def test_litellm_executor_with_api_base(self):
        """Test LiteLLM executor with api_base from config."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_litellm = MagicMock()

        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            from gobby.llm.resolver import _create_litellm_executor

            mock_provider_config = MagicMock()
            mock_provider_config.models = None
            mock_provider_config.api_base = "https://my-proxy.example.com"

            executor = _create_litellm_executor(mock_provider_config, None, None)

            assert executor.api_base == "https://my-proxy.example.com"

    def test_litellm_executor_with_api_keys(self):
        """Test LiteLLM executor with api_keys from config."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_litellm = MagicMock()

        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            from gobby.llm.resolver import _create_litellm_executor

            mock_provider_config = MagicMock()
            mock_provider_config.models = None
            mock_provider_config.api_base = None

            mock_config = MagicMock()
            mock_config.llm_providers.api_keys = {"OPENAI_API_KEY": "sk-test"}

            # Clear existing env var to test setting it
            with patch.dict("os.environ", {}, clear=True):
                executor = _create_litellm_executor(mock_provider_config, mock_config, None)

                # Verify executor was created (api_keys are set in env, not stored)
                assert executor.provider_name == "litellm"

    def test_litellm_executor_with_none_api_keys(self):
        """Test LiteLLM executor with None api_keys from config."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_litellm = MagicMock()

        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            from gobby.llm.resolver import _create_litellm_executor

            mock_provider_config = MagicMock()
            mock_provider_config.models = None
            mock_provider_config.api_base = None

            mock_config = MagicMock()
            mock_config.llm_providers.api_keys = None

            executor = _create_litellm_executor(mock_provider_config, mock_config, None)

            # Verify executor was created (None api_keys means no env vars set)
            assert executor.provider_name == "litellm"

    def test_codex_executor_with_none_auth_mode(self):
        """Test Codex executor defaults auth_mode when None."""
        import sys
        from unittest.mock import MagicMock, patch

        mock_openai = MagicMock()

        with patch.dict(sys.modules, {"openai": mock_openai}):
            with patch.dict("os.environ", {"OPENAI_API_KEY": "test-key"}):
                from gobby.llm.resolver import _create_codex_executor

                mock_config = MagicMock()
                mock_config.auth_mode = None
                mock_config.models = None

                executor = _create_codex_executor(mock_config, None)

                assert executor.auth_mode == "api_key"


class TestExecutorRegistryAdvanced:
    """Advanced tests for ExecutorRegistry class."""

    def test_cache_key_includes_model(self):
        """Test that cache key includes model for separate caching."""
        with patch("gobby.llm.resolver.create_executor") as mock_create:
            executor1 = MagicMock()
            executor2 = MagicMock()
            mock_create.side_effect = [executor1, executor2]

            registry = ExecutorRegistry()
            result1 = registry.get(provider="claude", model="claude-opus-4-5")
            result2 = registry.get(provider="claude", model="claude-sonnet-4-5")

            assert result1 is not result2
            assert mock_create.call_count == 2

    def test_cache_key_with_workflow_model(self):
        """Test that workflow model is included in cache key."""
        with patch("gobby.llm.resolver.create_executor") as mock_create:
            executor1 = MagicMock()
            executor2 = MagicMock()
            mock_create.side_effect = [executor1, executor2]

            mock_workflow1 = MagicMock()
            mock_workflow1.variables = {"provider": "claude", "model": "claude-opus-4-5"}

            mock_workflow2 = MagicMock()
            mock_workflow2.variables = {"provider": "claude", "model": "claude-sonnet-4-5"}

            registry = ExecutorRegistry()
            result1 = registry.get(workflow=mock_workflow1)
            result2 = registry.get(workflow=mock_workflow2)

            assert result1 is not result2
            assert mock_create.call_count == 2

    def test_explicit_model_overrides_workflow_model(self):
        """Test that explicit model override takes precedence over workflow model."""
        with patch("gobby.llm.resolver.create_executor") as mock_create:
            mock_executor = MagicMock()
            mock_create.return_value = mock_executor

            mock_workflow = MagicMock()
            mock_workflow.variables = {"provider": "claude", "model": "workflow-model"}

            registry = ExecutorRegistry()
            registry.get(workflow=mock_workflow, model="explicit-model")

            # Check that explicit model was passed to create_executor
            call_kwargs = mock_create.call_args
            assert call_kwargs[1]["model"] == "explicit-model"

    def test_get_with_config(self):
        """Test that registry passes config to create_executor."""
        with patch("gobby.llm.resolver.create_executor") as mock_create:
            mock_executor = MagicMock()
            mock_create.return_value = mock_executor

            mock_config = MagicMock()
            mock_config.llm_providers = None

            registry = ExecutorRegistry(config=mock_config)
            registry.get(provider="claude")

            # Verify config was passed
            call_kwargs = mock_create.call_args
            assert call_kwargs[1]["config"] is mock_config

    def test_get_all_returns_copy(self):
        """Test that get_all returns a copy of the cache."""
        with patch("gobby.llm.resolver.create_executor") as mock_create:
            mock_executor = MagicMock()
            mock_create.return_value = mock_executor

            registry = ExecutorRegistry()
            registry.get(provider="claude")

            all_executors = registry.get_all()
            # Modifying the returned dict should not affect the cache
            all_executors["new_key"] = "new_value"

            # Original cache should be unchanged
            assert "new_key" not in registry.get_all()


class TestValidateProviderConfigured:
    """Tests for _validate_provider_configured function."""

    def test_provider_configured(self):
        """Test no error when provider is configured."""
        from gobby.llm.resolver import _validate_provider_configured

        mock_llm_providers = MagicMock()
        mock_llm_providers.get_enabled_providers.return_value = ["claude", "gemini"]

        # Should not raise
        _validate_provider_configured("claude", mock_llm_providers)

    def test_provider_not_configured(self):
        """Test error when provider is not configured."""
        from gobby.llm.resolver import _validate_provider_configured

        mock_llm_providers = MagicMock()
        mock_llm_providers.get_enabled_providers.return_value = ["claude"]

        with pytest.raises(ProviderNotConfiguredError) as exc_info:
            _validate_provider_configured("gemini", mock_llm_providers)

        assert exc_info.value.provider == "gemini"
        assert "claude" in exc_info.value.available


class TestResolvedProviderDataclass:
    """Tests for ResolvedProvider dataclass."""

    def test_default_model_is_none(self):
        """Test that model defaults to None."""
        result = ResolvedProvider(provider="claude", source="explicit")
        assert result.model is None

    def test_all_fields_set(self):
        """Test creating ResolvedProvider with all fields."""
        result = ResolvedProvider(
            provider="claude",
            source="workflow",
            model="claude-opus-4-5",
        )
        assert result.provider == "claude"
        assert result.source == "workflow"
        assert result.model == "claude-opus-4-5"

    def test_resolution_sources(self):
        """Test all valid resolution sources."""
        sources = ["explicit", "workflow", "config", "default"]
        for source in sources:
            result = ResolvedProvider(provider="claude", source=source)  # type: ignore
            assert result.source == source
