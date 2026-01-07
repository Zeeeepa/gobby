"""
Tests for config/persistence.py module.

RED PHASE: Tests initially import from persistence.py (should fail),
then will pass once memory/skill config classes are extracted from app.py.
"""

import pytest
from pydantic import ValidationError


# =============================================================================
# Import Tests (RED phase targets)
# =============================================================================


class TestMemoryConfigImport:
    """Test that MemoryConfig can be imported from the persistence module."""

    def test_import_from_persistence_module(self) -> None:
        """Test importing MemoryConfig from config.persistence (RED phase target)."""
        from gobby.config.persistence import MemoryConfig

        assert MemoryConfig is not None


class TestMemorySyncConfigImport:
    """Test that MemorySyncConfig can be imported from the persistence module."""

    def test_import_from_persistence_module(self) -> None:
        """Test importing MemorySyncConfig from config.persistence (RED phase target)."""
        from gobby.config.persistence import MemorySyncConfig

        assert MemorySyncConfig is not None


class TestSkillSyncConfigImport:
    """Test that SkillSyncConfig can be imported from the persistence module."""

    def test_import_from_persistence_module(self) -> None:
        """Test importing SkillSyncConfig from config.persistence (RED phase target)."""
        from gobby.config.persistence import SkillSyncConfig

        assert SkillSyncConfig is not None


class TestSkillConfigImport:
    """Test that SkillConfig can be imported from the persistence module."""

    def test_import_from_persistence_module(self) -> None:
        """Test importing SkillConfig from config.persistence (RED phase target)."""
        from gobby.config.persistence import SkillConfig

        assert SkillConfig is not None


# =============================================================================
# MemoryConfig Tests
# =============================================================================


class TestMemoryConfigDefaults:
    """Test MemoryConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test MemoryConfig creates with all defaults."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert config.enabled is True
        assert config.auto_extract is True
        assert config.injection_limit == 10
        assert config.importance_threshold == 0.3
        assert config.decay_enabled is True
        assert config.decay_rate == 0.05
        assert config.decay_floor == 0.1
        assert config.semantic_search_enabled is True
        assert config.embedding_provider == "openai"
        assert config.embedding_model == "text-embedding-3-small"
        assert config.auto_embed is True
        assert config.access_debounce_seconds == 60
        assert config.provider == "claude"
        assert config.model == "claude-haiku-4-5"

    def test_prompts_present(self) -> None:
        """Test default prompts are present."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert config.extraction_prompt is not None
        assert len(config.extraction_prompt) > 0
        assert "{summary}" in config.extraction_prompt

        assert config.agent_md_extraction_prompt is not None
        assert "{content}" in config.agent_md_extraction_prompt

        assert config.codebase_extraction_prompt is not None
        assert "{content}" in config.codebase_extraction_prompt


class TestMemoryConfigCustom:
    """Test MemoryConfig with custom values."""

    def test_disabled_memory(self) -> None:
        """Test disabling memory system."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(enabled=False)
        assert config.enabled is False

    def test_custom_injection_limit(self) -> None:
        """Test setting custom injection limit."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(injection_limit=20)
        assert config.injection_limit == 20

    def test_custom_importance_threshold(self) -> None:
        """Test setting custom importance threshold."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(importance_threshold=0.5)
        assert config.importance_threshold == 0.5

    def test_custom_decay_settings(self) -> None:
        """Test setting custom decay settings."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(
            decay_enabled=False,
            decay_rate=0.1,
            decay_floor=0.2,
        )
        assert config.decay_enabled is False
        assert config.decay_rate == 0.1
        assert config.decay_floor == 0.2

    def test_custom_embedding_settings(self) -> None:
        """Test setting custom embedding settings."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(
            semantic_search_enabled=False,
            embedding_provider="litellm",
            embedding_model="voyage-code-2",
            auto_embed=False,
        )
        assert config.semantic_search_enabled is False
        assert config.embedding_provider == "litellm"
        assert config.embedding_model == "voyage-code-2"
        assert config.auto_embed is False

    def test_custom_llm_settings(self) -> None:
        """Test setting custom LLM settings."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(provider="gemini", model="gemini-2.0-flash")
        assert config.provider == "gemini"
        assert config.model == "gemini-2.0-flash"


class TestMemoryConfigValidation:
    """Test MemoryConfig validation."""

    def test_injection_limit_non_negative(self) -> None:
        """Test that injection_limit must be non-negative."""
        from gobby.config.persistence import MemoryConfig

        # Zero is allowed
        config = MemoryConfig(injection_limit=0)
        assert config.injection_limit == 0

        # Negative is not
        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig(injection_limit=-1)
        assert "non-negative" in str(exc_info.value).lower()

    def test_importance_threshold_range(self) -> None:
        """Test that importance_threshold must be between 0 and 1."""
        from gobby.config.persistence import MemoryConfig

        # Boundaries are valid
        config = MemoryConfig(importance_threshold=0.0)
        assert config.importance_threshold == 0.0

        config = MemoryConfig(importance_threshold=1.0)
        assert config.importance_threshold == 1.0

        # Out of range
        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig(importance_threshold=-0.1)
        assert "0" in str(exc_info.value) and "1" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig(importance_threshold=1.1)
        assert "0" in str(exc_info.value) and "1" in str(exc_info.value)

    def test_decay_rate_range(self) -> None:
        """Test that decay_rate must be between 0 and 1."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(decay_rate=0.0)
        assert config.decay_rate == 0.0

        config = MemoryConfig(decay_rate=1.0)
        assert config.decay_rate == 1.0

        with pytest.raises(ValidationError):
            MemoryConfig(decay_rate=-0.1)

        with pytest.raises(ValidationError):
            MemoryConfig(decay_rate=1.1)

    def test_decay_floor_range(self) -> None:
        """Test that decay_floor must be between 0 and 1."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(decay_floor=0.0)
        assert config.decay_floor == 0.0

        config = MemoryConfig(decay_floor=1.0)
        assert config.decay_floor == 1.0

        with pytest.raises(ValidationError):
            MemoryConfig(decay_floor=-0.1)

        with pytest.raises(ValidationError):
            MemoryConfig(decay_floor=1.1)


# =============================================================================
# MemorySyncConfig Tests
# =============================================================================


class TestMemorySyncConfigDefaults:
    """Test MemorySyncConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test MemorySyncConfig creates with all defaults."""
        from gobby.config.persistence import MemorySyncConfig

        config = MemorySyncConfig()
        assert config.enabled is True
        assert config.stealth is False
        assert config.export_debounce == 5.0


class TestMemorySyncConfigCustom:
    """Test MemorySyncConfig with custom values."""

    def test_stealth_mode(self) -> None:
        """Test enabling stealth mode (local storage only)."""
        from gobby.config.persistence import MemorySyncConfig

        config = MemorySyncConfig(stealth=True)
        assert config.stealth is True

    def test_disabled_sync(self) -> None:
        """Test disabling memory sync."""
        from gobby.config.persistence import MemorySyncConfig

        config = MemorySyncConfig(enabled=False)
        assert config.enabled is False

    def test_custom_debounce(self) -> None:
        """Test setting custom export debounce."""
        from gobby.config.persistence import MemorySyncConfig

        config = MemorySyncConfig(export_debounce=10.0)
        assert config.export_debounce == 10.0


class TestMemorySyncConfigValidation:
    """Test MemorySyncConfig validation."""

    def test_export_debounce_non_negative(self) -> None:
        """Test that export_debounce must be non-negative."""
        from gobby.config.persistence import MemorySyncConfig

        # Zero is allowed
        config = MemorySyncConfig(export_debounce=0.0)
        assert config.export_debounce == 0.0

        # Negative is not
        with pytest.raises(ValidationError) as exc_info:
            MemorySyncConfig(export_debounce=-1.0)
        assert "non-negative" in str(exc_info.value).lower()


# =============================================================================
# SkillSyncConfig Tests
# =============================================================================


class TestSkillSyncConfigDefaults:
    """Test SkillSyncConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test SkillSyncConfig creates with all defaults."""
        from gobby.config.persistence import SkillSyncConfig

        config = SkillSyncConfig()
        assert config.enabled is True
        assert config.stealth is False
        assert config.export_debounce == 5.0


class TestSkillSyncConfigCustom:
    """Test SkillSyncConfig with custom values."""

    def test_stealth_mode(self) -> None:
        """Test enabling stealth mode."""
        from gobby.config.persistence import SkillSyncConfig

        config = SkillSyncConfig(stealth=True)
        assert config.stealth is True

    def test_disabled_sync(self) -> None:
        """Test disabling skill sync."""
        from gobby.config.persistence import SkillSyncConfig

        config = SkillSyncConfig(enabled=False)
        assert config.enabled is False

    def test_custom_debounce(self) -> None:
        """Test setting custom export debounce."""
        from gobby.config.persistence import SkillSyncConfig

        config = SkillSyncConfig(export_debounce=15.0)
        assert config.export_debounce == 15.0


class TestSkillSyncConfigValidation:
    """Test SkillSyncConfig validation."""

    def test_export_debounce_non_negative(self) -> None:
        """Test that export_debounce must be non-negative."""
        from gobby.config.persistence import SkillSyncConfig

        config = SkillSyncConfig(export_debounce=0.0)
        assert config.export_debounce == 0.0

        with pytest.raises(ValidationError) as exc_info:
            SkillSyncConfig(export_debounce=-0.5)
        assert "non-negative" in str(exc_info.value).lower()


# =============================================================================
# SkillConfig Tests
# =============================================================================


class TestSkillConfigDefaults:
    """Test SkillConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test SkillConfig creates with all defaults."""
        from gobby.config.persistence import SkillConfig

        config = SkillConfig()
        assert config.enabled is True
        assert config.provider == "claude"
        assert config.model == "claude-haiku-4-5"

    def test_prompt_present(self) -> None:
        """Test default prompt is present."""
        from gobby.config.persistence import SkillConfig

        config = SkillConfig()
        assert config.prompt is not None
        assert len(config.prompt) > 0
        assert "{transcript}" in config.prompt


class TestSkillConfigCustom:
    """Test SkillConfig with custom values."""

    def test_disabled_skills(self) -> None:
        """Test disabling skill learning."""
        from gobby.config.persistence import SkillConfig

        config = SkillConfig(enabled=False)
        assert config.enabled is False

    def test_custom_provider(self) -> None:
        """Test setting custom provider."""
        from gobby.config.persistence import SkillConfig

        config = SkillConfig(provider="gemini")
        assert config.provider == "gemini"

    def test_custom_model(self) -> None:
        """Test setting custom model."""
        from gobby.config.persistence import SkillConfig

        config = SkillConfig(model="claude-sonnet-4-5")
        assert config.model == "claude-sonnet-4-5"

    def test_custom_prompt(self) -> None:
        """Test setting custom prompt."""
        from gobby.config.persistence import SkillConfig

        custom_prompt = "Custom prompt with {transcript}"
        config = SkillConfig(prompt=custom_prompt)
        assert config.prompt == custom_prompt


# =============================================================================
# Baseline Tests (import from app.py)
# =============================================================================


class TestMemoryConfigFromAppPy:
    """Verify that tests pass when importing from app.py (reference implementation)."""

    def test_import_from_app_py(self) -> None:
        """Test importing MemoryConfig from app.py works (baseline)."""
        from gobby.config.app import MemoryConfig

        config = MemoryConfig()
        assert config.enabled is True
        assert config.injection_limit == 10

    def test_validation_via_app_py(self) -> None:
        """Test validation works when imported from app.py."""
        from gobby.config.app import MemoryConfig

        with pytest.raises(ValidationError):
            MemoryConfig(injection_limit=-1)


class TestMemorySyncConfigFromAppPy:
    """Verify MemorySyncConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing MemorySyncConfig from app.py works (baseline)."""
        from gobby.config.app import MemorySyncConfig

        config = MemorySyncConfig()
        assert config.enabled is True
        assert config.stealth is False


class TestSkillSyncConfigFromAppPy:
    """Verify SkillSyncConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing SkillSyncConfig from app.py works (baseline)."""
        from gobby.config.app import SkillSyncConfig

        config = SkillSyncConfig()
        assert config.enabled is True
        assert config.export_debounce == 5.0


class TestSkillConfigFromAppPy:
    """Verify SkillConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing SkillConfig from app.py works (baseline)."""
        from gobby.config.app import SkillConfig

        config = SkillConfig()
        assert config.enabled is True
        assert config.provider == "claude"
