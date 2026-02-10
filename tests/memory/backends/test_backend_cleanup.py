"""Tests verifying deprecated OpenMemory backend has been removed.

Part of Memory V4: cleaning up deprecated backends after mem0 integration
replaced the self-hosted OpenMemory approach.
"""

import pytest


class TestOpenMemoryBackendRemoved:
    """Verify the OpenMemory backend file and factory entry are removed."""

    def test_get_backend_rejects_openmemory(self) -> None:
        """get_backend('openmemory') should raise ValueError."""
        from gobby.memory.backends import get_backend

        with pytest.raises(ValueError, match="Unknown backend type"):
            get_backend("openmemory", base_url="http://localhost:8080")

    def test_openmemory_module_not_importable(self) -> None:
        """The openmemory backend module should no longer exist."""
        with pytest.raises(ImportError):
            from gobby.memory.backends.openmemory import OpenMemoryBackend  # noqa: F401

    def test_supported_backends_exclude_openmemory(self) -> None:
        """The error message from get_backend should not list openmemory."""
        from gobby.memory.backends import get_backend

        with pytest.raises(ValueError, match="Supported types") as exc_info:
            get_backend("nonexistent_backend")
        assert "openmemory" not in str(exc_info.value)


class TestOpenMemoryConfigRemoved:
    """Verify OpenMemoryConfig is removed from persistence config."""

    def test_openmemory_config_not_importable(self) -> None:
        """OpenMemoryConfig should no longer be importable from persistence."""
        with pytest.raises(ImportError):
            from gobby.config.persistence import OpenMemoryConfig  # noqa: F401

    def test_memory_config_no_openmemory_field(self) -> None:
        """MemoryConfig should not have an 'openmemory' field."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert not hasattr(config, "openmemory")

    def test_backend_validator_rejects_openmemory(self) -> None:
        """'openmemory' should not be a valid backend option."""
        from pydantic import ValidationError

        from gobby.config.persistence import MemoryConfig

        with pytest.raises(ValidationError):
            MemoryConfig(backend="openmemory")

    def test_openmemory_not_in_exports(self) -> None:
        """OpenMemoryConfig should not be in __all__."""
        from gobby.config import persistence

        assert "OpenMemoryConfig" not in persistence.__all__
