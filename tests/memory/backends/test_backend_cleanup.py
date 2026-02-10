"""Tests verifying deprecated backends have been removed.

Part of Memory V4: cleaning up deprecated backends after mem0 integration.
"""

import pytest


class TestSQLiteBackendRemoved:
    """Verify the SQLite backend wrapper has been removed from the factory."""

    def test_get_backend_rejects_sqlite(self) -> None:
        """get_backend('sqlite') should raise ValueError."""
        from gobby.memory.backends import get_backend

        with pytest.raises(ValueError, match="Unknown backend type"):
            get_backend("sqlite", database=None)

    def test_sqlite_backend_not_importable(self) -> None:
        """The SQLiteBackend class should no longer exist in backends."""
        with pytest.raises(ImportError):
            from gobby.memory.backends.sqlite import SQLiteBackend  # noqa: F401

    def test_supported_backends_exclude_sqlite(self) -> None:
        """The error message from get_backend should not list sqlite."""
        from gobby.memory.backends import get_backend

        with pytest.raises(ValueError, match="Supported types") as exc_info:
            get_backend("nonexistent_backend")
        assert "sqlite" not in str(exc_info.value)


class TestSQLiteConfigAlias:
    """Verify 'sqlite' is accepted as backwards-compat alias for 'local'."""

    def test_backend_validator_accepts_sqlite_as_local(self) -> None:
        """'sqlite' should be accepted and mapped to 'local'."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(backend="sqlite")
        assert config.backend == "local"


class TestMem0BackendRemoved:
    """Verify the old Mem0Backend (mem0ai-based) has been removed from the factory."""

    def test_get_backend_rejects_mem0(self) -> None:
        """get_backend('mem0') should raise ValueError."""
        from gobby.memory.backends import get_backend

        with pytest.raises(ValueError, match="Unknown backend type"):
            get_backend("mem0", api_key="test-key")

    def test_mem0_backend_not_importable(self) -> None:
        """The Mem0Backend class should no longer exist in backends."""
        with pytest.raises(ImportError):
            from gobby.memory.backends.mem0 import Mem0Backend  # noqa: F401

    def test_supported_backends_exclude_mem0(self) -> None:
        """The error message from get_backend should not list mem0."""
        from gobby.memory.backends import get_backend

        with pytest.raises(ValueError, match="Supported types") as exc_info:
            get_backend("nonexistent_backend")
        assert "mem0" not in str(exc_info.value)


class TestMem0ConfigRemoved:
    """Verify old Mem0Config is removed from persistence config."""

    def test_mem0_config_not_importable(self) -> None:
        """Mem0Config should no longer be importable from persistence."""
        with pytest.raises(ImportError):
            from gobby.config.persistence import Mem0Config  # noqa: F401

    def test_memory_config_no_mem0_field(self) -> None:
        """MemoryConfig should not have a 'mem0' field (old Mem0Config)."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig()
        assert not hasattr(config, "mem0")

    def test_backend_validator_rejects_mem0(self) -> None:
        """'mem0' should not be a valid backend option."""
        from pydantic import ValidationError

        from gobby.config.persistence import MemoryConfig

        with pytest.raises(ValidationError):
            MemoryConfig(backend="mem0")

    def test_mem0_config_not_in_exports(self) -> None:
        """Mem0Config should not be in __all__."""
        from gobby.config import persistence

        assert "Mem0Config" not in persistence.__all__


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
