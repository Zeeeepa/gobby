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
        assert config.importance_threshold == 0.7
        assert config.decay_enabled is True
        assert config.decay_rate == 0.05
        assert config.decay_floor == 0.1
        assert config.search_backend == "tfidf"
        assert config.access_debounce_seconds == 60


class TestMemoryConfigCustom:
    """Test MemoryConfig with custom values."""

    def test_disabled_memory(self) -> None:
        """Test disabling memory system."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(enabled=False)
        assert config.enabled is False

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


class TestMemoryConfigValidation:
    """Test MemoryConfig validation."""

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
        from pathlib import Path

        from gobby.config.persistence import MemorySyncConfig

        config = MemorySyncConfig()
        assert config.enabled is True
        assert config.export_debounce == 5.0
        assert config.export_path == Path(".gobby/memories.jsonl")


class TestMemorySyncConfigCustom:
    """Test MemorySyncConfig with custom values."""

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

    def test_custom_export_path(self) -> None:
        """Test setting custom export path."""
        from pathlib import Path

        from gobby.config.persistence import MemorySyncConfig

        config = MemorySyncConfig(export_path=Path("/custom/memories.jsonl"))
        assert config.export_path == Path("/custom/memories.jsonl")


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
# Baseline Tests (import from app.py)
# =============================================================================


class TestMemoryConfigFromAppPy:
    """Verify that tests pass when importing from app.py (reference implementation)."""

    def test_import_from_app_py(self) -> None:
        """Test importing MemoryConfig from app.py works (baseline)."""
        from gobby.config.app import MemoryConfig

        config = MemoryConfig()
        assert config.enabled is True


class TestMemorySyncConfigFromAppPy:
    """Verify MemorySyncConfig tests pass when importing from app.py."""

    def test_import_from_app_py(self) -> None:
        """Test importing MemorySyncConfig from app.py works (baseline)."""
        from gobby.config.app import MemorySyncConfig

        config = MemorySyncConfig()
        assert config.enabled is True
        assert config.export_debounce == 5.0
