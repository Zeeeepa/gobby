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
# Mem0Config Tests
# =============================================================================


class TestMem0ConfigImport:
    """Test that Mem0Config can be imported from the persistence module."""

    def test_import_from_persistence_module(self) -> None:
        """Test importing Mem0Config from config.persistence."""
        from gobby.config.persistence import Mem0Config

        assert Mem0Config is not None


class TestMem0ConfigDefaults:
    """Test Mem0Config default values."""

    def test_default_instantiation(self) -> None:
        """Test Mem0Config creates with all defaults (None values)."""
        from gobby.config.persistence import Mem0Config

        config = Mem0Config()
        assert config.api_key is None
        assert config.user_id is None
        assert config.org_id is None


class TestMem0ConfigCustom:
    """Test Mem0Config with custom values."""

    def test_with_api_key(self) -> None:
        """Test setting API key."""
        from gobby.config.persistence import Mem0Config

        config = Mem0Config(api_key="test-api-key")
        assert config.api_key == "test-api-key"

    def test_with_user_id(self) -> None:
        """Test setting user ID."""
        from gobby.config.persistence import Mem0Config

        config = Mem0Config(user_id="test-user")
        assert config.user_id == "test-user"

    def test_with_org_id(self) -> None:
        """Test setting organization ID."""
        from gobby.config.persistence import Mem0Config

        config = Mem0Config(org_id="test-org")
        assert config.org_id == "test-org"

    def test_full_configuration(self) -> None:
        """Test setting all configuration values."""
        from gobby.config.persistence import Mem0Config

        config = Mem0Config(
            api_key="my-api-key",
            user_id="my-user",
            org_id="my-org",
        )
        assert config.api_key == "my-api-key"
        assert config.user_id == "my-user"
        assert config.org_id == "my-org"


class TestMemoryConfigMem0Integration:
    """Test MemoryConfig integration with Mem0Config."""

    def test_default_mem0_config(self) -> None:
        """Test that MemoryConfig has default Mem0Config."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert config.mem0 is not None
        assert config.mem0.api_key is None

    def test_mem0_backend_selection(self) -> None:
        """Test selecting mem0 backend."""
        from gobby.config.persistence import Mem0Config, MemoryConfig

        config = MemoryConfig(
            backend="mem0",
            mem0=Mem0Config(api_key="test-key"),
        )
        assert config.backend == "mem0"
        assert config.mem0.api_key == "test-key"

    def test_backend_validator_accepts_mem0(self) -> None:
        """Test that 'mem0' is a valid backend option."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(backend="mem0")
        assert config.backend == "mem0"

    def test_backend_validator_rejects_invalid(self) -> None:
        """Test that invalid backends are rejected."""
        from gobby.config.persistence import MemoryConfig

        with pytest.raises(ValidationError) as exc_info:
            MemoryConfig(backend="invalid_backend")
        assert "invalid_backend" in str(exc_info.value).lower()


# =============================================================================
# OpenMemoryConfig Tests
# =============================================================================


class TestOpenMemoryConfigImport:
    """Test that OpenMemoryConfig can be imported from the persistence module."""

    def test_import_from_persistence_module(self) -> None:
        """Test importing OpenMemoryConfig from config.persistence."""
        from gobby.config.persistence import OpenMemoryConfig

        assert OpenMemoryConfig is not None


class TestOpenMemoryConfigDefaults:
    """Test OpenMemoryConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test OpenMemoryConfig creates with all defaults."""
        from gobby.config.persistence import OpenMemoryConfig

        config = OpenMemoryConfig()
        assert config.base_url == "http://localhost:8080"
        assert config.api_key is None
        assert config.user_id is None


class TestOpenMemoryConfigCustom:
    """Test OpenMemoryConfig with custom values."""

    def test_with_base_url(self) -> None:
        """Test setting custom base URL."""
        from gobby.config.persistence import OpenMemoryConfig

        config = OpenMemoryConfig(base_url="http://memory.example.com:9000")
        assert config.base_url == "http://memory.example.com:9000"

    def test_with_https_url(self) -> None:
        """Test setting HTTPS URL."""
        from gobby.config.persistence import OpenMemoryConfig

        config = OpenMemoryConfig(base_url="https://memory.example.com")
        assert config.base_url == "https://memory.example.com"

    def test_with_api_key(self) -> None:
        """Test setting API key."""
        from gobby.config.persistence import OpenMemoryConfig

        config = OpenMemoryConfig(api_key="test-api-key")
        assert config.api_key == "test-api-key"

    def test_with_user_id(self) -> None:
        """Test setting user ID."""
        from gobby.config.persistence import OpenMemoryConfig

        config = OpenMemoryConfig(user_id="test-user")
        assert config.user_id == "test-user"

    def test_full_configuration(self) -> None:
        """Test setting all configuration values."""
        from gobby.config.persistence import OpenMemoryConfig

        config = OpenMemoryConfig(
            base_url="https://memory.example.com:8443",
            api_key="my-api-key",
            user_id="my-user",
        )
        assert config.base_url == "https://memory.example.com:8443"
        assert config.api_key == "my-api-key"
        assert config.user_id == "my-user"


class TestOpenMemoryConfigValidation:
    """Test OpenMemoryConfig validation."""

    def test_url_trailing_slash_stripped(self) -> None:
        """Test that trailing slash is stripped from base_url."""
        from gobby.config.persistence import OpenMemoryConfig

        config = OpenMemoryConfig(base_url="http://localhost:8080/")
        assert config.base_url == "http://localhost:8080"

    def test_invalid_url_rejected(self) -> None:
        """Test that invalid URLs are rejected."""
        from gobby.config.persistence import OpenMemoryConfig

        with pytest.raises(ValidationError) as exc_info:
            OpenMemoryConfig(base_url="not-a-url")
        assert "http://" in str(exc_info.value) or "https://" in str(exc_info.value)

    def test_ftp_url_rejected(self) -> None:
        """Test that non-HTTP URLs are rejected."""
        from gobby.config.persistence import OpenMemoryConfig

        with pytest.raises(ValidationError):
            OpenMemoryConfig(base_url="ftp://memory.example.com")


class TestMemoryConfigOpenMemoryIntegration:
    """Test MemoryConfig integration with OpenMemoryConfig."""

    def test_default_openmemory_config(self) -> None:
        """Test that MemoryConfig has default OpenMemoryConfig."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert config.openmemory is not None
        assert config.openmemory.base_url == "http://localhost:8080"

    def test_openmemory_backend_selection(self) -> None:
        """Test selecting openmemory backend."""
        from gobby.config.persistence import MemoryConfig, OpenMemoryConfig

        config = MemoryConfig(
            backend="openmemory",
            openmemory=OpenMemoryConfig(base_url="https://memory.myserver.com"),
        )
        assert config.backend == "openmemory"
        assert config.openmemory.base_url == "https://memory.myserver.com"

    def test_backend_validator_accepts_openmemory(self) -> None:
        """Test that 'openmemory' is a valid backend option."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(backend="openmemory")
        assert config.backend == "openmemory"


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
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert config.enabled is True


class TestMemorySyncConfigFromAppPy:
    """Verify MemorySyncConfig tests pass when importing from app.py."""

    def test_import_from_persistence_module(self) -> None:
        """Test importing MemorySyncConfig from persistence module works."""
        from gobby.config.persistence import MemorySyncConfig

        config = MemorySyncConfig()
        assert config.enabled is True
        assert config.export_debounce == 5.0
