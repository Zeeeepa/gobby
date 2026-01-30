"""
Tests for config/logging.py module.

RED PHASE: Tests initially import from logging.py (should fail),
then will pass once LoggingSettings is extracted from app.py.
"""

import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit

class TestLoggingSettingsImport:
    """Test that LoggingSettings can be imported from the logging module."""

    def test_import_from_logging_module(self) -> None:
        """Test importing LoggingSettings from config.logging (RED phase target)."""
        # This import should fail until logging.py is populated
        from gobby.config.logging import LoggingSettings

        assert LoggingSettings is not None


class TestLoggingSettingsDefaults:
    """Test LoggingSettings default values."""

    def test_default_instantiation(self) -> None:
        """Test LoggingSettings creates with all defaults."""
        from gobby.config.logging import LoggingSettings

        settings = LoggingSettings()
        assert settings.level == "info"
        assert settings.format == "text"

    def test_default_log_paths(self) -> None:
        """Test default log file paths."""
        from gobby.config.logging import LoggingSettings

        settings = LoggingSettings()
        assert settings.client == "~/.gobby/logs/gobby.log"
        assert settings.client_error == "~/.gobby/logs/gobby-error.log"
        assert settings.hook_manager == "~/.gobby/logs/hook-manager.log"
        assert settings.mcp_server == "~/.gobby/logs/mcp-server.log"
        assert settings.mcp_client == "~/.gobby/logs/mcp-client.log"

    def test_default_rotation_settings(self) -> None:
        """Test default log rotation settings."""
        from gobby.config.logging import LoggingSettings

        settings = LoggingSettings()
        assert settings.max_size_mb == 10
        assert settings.backup_count == 5


class TestLoggingSettingsCustomValues:
    """Test LoggingSettings with custom values."""

    def test_custom_level(self) -> None:
        """Test setting custom log level."""
        from gobby.config.logging import LoggingSettings

        settings = LoggingSettings(level="debug")
        assert settings.level == "debug"

        settings = LoggingSettings(level="warning")
        assert settings.level == "warning"

        settings = LoggingSettings(level="error")
        assert settings.level == "error"

    def test_custom_format(self) -> None:
        """Test setting custom log format."""
        from gobby.config.logging import LoggingSettings

        settings = LoggingSettings(format="json")
        assert settings.format == "json"

    def test_custom_log_paths(self) -> None:
        """Test setting custom log file paths."""
        from gobby.config.logging import LoggingSettings

        settings = LoggingSettings(
            client="/var/log/gobby/main.log",
            client_error="/var/log/gobby/error.log",
            hook_manager="/var/log/gobby/hooks.log",
        )
        assert settings.client == "/var/log/gobby/main.log"
        assert settings.client_error == "/var/log/gobby/error.log"
        assert settings.hook_manager == "/var/log/gobby/hooks.log"

    def test_custom_rotation_settings(self) -> None:
        """Test setting custom log rotation settings."""
        from gobby.config.logging import LoggingSettings

        settings = LoggingSettings(max_size_mb=50, backup_count=10)
        assert settings.max_size_mb == 50
        assert settings.backup_count == 10


class TestLoggingSettingsValidation:
    """Test LoggingSettings validation."""

    def test_invalid_level(self) -> None:
        """Test that invalid log level raises ValidationError."""
        from gobby.config.logging import LoggingSettings

        with pytest.raises(ValidationError):
            LoggingSettings(level="invalid")  # type: ignore

    def test_invalid_format(self) -> None:
        """Test that invalid log format raises ValidationError."""
        from gobby.config.logging import LoggingSettings

        with pytest.raises(ValidationError):
            LoggingSettings(format="invalid")  # type: ignore

    def test_max_size_mb_must_be_positive(self) -> None:
        """Test that max_size_mb must be positive."""
        from gobby.config.logging import LoggingSettings

        with pytest.raises(ValidationError) as exc_info:
            LoggingSettings(max_size_mb=0)
        assert "must be positive" in str(exc_info.value).lower()

        with pytest.raises(ValidationError) as exc_info:
            LoggingSettings(max_size_mb=-1)
        assert "must be positive" in str(exc_info.value).lower()

    def test_backup_count_must_be_positive(self) -> None:
        """Test that backup_count must be positive."""
        from gobby.config.logging import LoggingSettings

        with pytest.raises(ValidationError) as exc_info:
            LoggingSettings(backup_count=0)
        assert "must be positive" in str(exc_info.value).lower()

        with pytest.raises(ValidationError) as exc_info:
            LoggingSettings(backup_count=-5)
        assert "must be positive" in str(exc_info.value).lower()


class TestLoggingSettingsFromAppPy:
    """Verify that tests pass when importing from app.py (reference implementation)."""

    def test_import_from_app_py(self) -> None:
        """Test importing LoggingSettings from app.py works (baseline)."""
        from gobby.config.logging import LoggingSettings

        settings = LoggingSettings()
        assert settings.level == "info"
        assert settings.format == "text"
        assert settings.max_size_mb == 10
        assert settings.backup_count == 5

    def test_validation_via_app_py(self) -> None:
        """Test validation works when imported from app.py."""
        from gobby.config.logging import LoggingSettings

        with pytest.raises(ValidationError):
            LoggingSettings(max_size_mb=0)

        with pytest.raises(ValidationError):
            LoggingSettings(backup_count=-1)
