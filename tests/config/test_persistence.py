"""
Tests for config/persistence.py module.

RED PHASE: Tests initially import from persistence.py (should fail),
then will pass once memory/skill config classes are extracted from app.py.
"""

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit

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
        assert config.search_backend == "auto"
        assert config.embedding_model == "text-embedding-3-small"
        assert config.embedding_weight == 0.6
        assert config.tfidf_weight == 0.4
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
# Backend Validator Tests
# =============================================================================


class TestMemoryConfigBackendValidator:
    """Test MemoryConfig backend validation."""

    def test_backend_validator_rejects_invalid(self) -> None:
        """Test that invalid backends are rejected."""
        from gobby.config.persistence import MemoryConfig

        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig(backend="invalid_backend")
        assert "invalid_backend" in str(exc_info.value).lower()

    def test_backend_sqlite_alias(self) -> None:
        """Test that 'sqlite' is accepted as alias for 'local'."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(backend="sqlite")
        assert config.backend == "local"


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


# =============================================================================
# MemoryConfig: Expanded search_backend options (Memory V4)
# =============================================================================


class TestMemoryConfigSearchBackendOptions:
    """Test expanded search_backend options for semantic search."""

    @pytest.mark.parametrize("backend", ["tfidf", "text", "embedding", "auto", "hybrid"])
    def test_valid_search_backends(self, backend: str) -> None:
        """Test that all valid search_backend values are accepted."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(search_backend=backend)
        assert config.search_backend == backend

    def test_invalid_search_backend_rejected(self) -> None:
        """Test that invalid search_backend values are rejected."""
        from gobby.config.persistence import MemoryConfig

        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig(search_backend="invalid")
        assert "invalid" in str(exc_info.value).lower()

    def test_default_search_backend_is_auto(self) -> None:
        """Test that the default search_backend is 'auto'."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert config.search_backend == "auto"


class TestMemoryConfigEmbeddingFields:
    """Test new embedding configuration fields."""

    def test_embedding_model_default(self) -> None:
        """Test default embedding_model value."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert config.embedding_model == "text-embedding-3-small"

    def test_embedding_model_custom(self) -> None:
        """Test setting a custom embedding model."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(embedding_model="text-embedding-3-large")
        assert config.embedding_model == "text-embedding-3-large"

    def test_embedding_weight_default(self) -> None:
        """Test default embedding_weight value."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert config.embedding_weight == 0.6

    def test_tfidf_weight_default(self) -> None:
        """Test default tfidf_weight value."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert config.tfidf_weight == 0.4

    def test_custom_weights(self) -> None:
        """Test setting custom search weights."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(embedding_weight=0.8, tfidf_weight=0.2)
        assert config.embedding_weight == 0.8
        assert config.tfidf_weight == 0.2

    def test_weight_validation_range(self) -> None:
        """Test that weights must be between 0 and 1."""
        from gobby.config.persistence import MemoryConfig

        with pytest.raises(ValidationError):
            MemoryConfig(embedding_weight=1.5)

        with pytest.raises(ValidationError):
            MemoryConfig(tfidf_weight=-0.1)


class TestMemoryConfigMem0Fields:
    """Test mem0_url and mem0_api_key fields on MemoryConfig."""

    def test_mem0_url_defaults_to_none(self) -> None:
        """mem0_url should default to None (standalone mode)."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert config.mem0_url is None

    def test_mem0_api_key_defaults_to_none(self) -> None:
        """mem0_api_key should default to None."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert config.mem0_api_key is None

    def test_mem0_url_accepts_valid_url(self) -> None:
        """Setting mem0_url to a valid URL should work."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(mem0_url="http://localhost:8888")
        assert config.mem0_url == "http://localhost:8888"

    def test_mem0_api_key_stores_env_var_pattern(self) -> None:
        """mem0_api_key should store ${ENV_VAR} as-is (expansion at load time)."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(mem0_api_key="${MEM0_API_KEY}")
        assert config.mem0_api_key == "${MEM0_API_KEY}"

    def test_none_mem0_url_means_standalone(self) -> None:
        """When mem0_url is None, the system operates in standalone mode."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(mem0_url=None)
        assert config.mem0_url is None

    def test_mem0_url_with_api_key(self) -> None:
        """Both mem0_url and mem0_api_key can be set together."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(
            mem0_url="https://api.mem0.ai",
            mem0_api_key="sk-test-key",
        )
        assert config.mem0_url == "https://api.mem0.ai"
        assert config.mem0_api_key == "sk-test-key"
