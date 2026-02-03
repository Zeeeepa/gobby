"""Tests for ConductorConfig in gobby.config.app module.

Tests for the conductor configuration section which handles token budget
settings for agent spawning decisions.
"""

import pytest

pytestmark = pytest.mark.unit


class TestConductorConfigDefaults:
    """Tests for ConductorConfig default values."""

    def test_conductor_config_defaults(self) -> None:
        """ConductorConfig has correct default values."""
        from gobby.config.app import ConductorConfig

        config = ConductorConfig()

        assert config.daily_budget_usd == 50.0
        assert config.warning_threshold == 0.8
        assert config.throttle_threshold == 0.9
        assert config.tracking_window_days == 7

    def test_conductor_config_unlimited_budget(self) -> None:
        """ConductorConfig with 0 daily_budget_usd means unlimited."""
        from gobby.config.app import ConductorConfig

        config = ConductorConfig(daily_budget_usd=0.0)

        assert config.daily_budget_usd == 0.0

    def test_conductor_config_custom_values(self) -> None:
        """ConductorConfig accepts custom values."""
        from gobby.config.app import ConductorConfig

        config = ConductorConfig(
            daily_budget_usd=100.0,
            warning_threshold=0.7,
            throttle_threshold=0.85,
            tracking_window_days=14,
        )

        assert config.daily_budget_usd == 100.0
        assert config.warning_threshold == 0.7
        assert config.throttle_threshold == 0.85
        assert config.tracking_window_days == 14


class TestConductorConfigValidation:
    """Tests for ConductorConfig validation."""

    def test_warning_threshold_must_be_between_0_and_1(self) -> None:
        """warning_threshold must be between 0 and 1."""
        from pydantic import ValidationError

        from gobby.config.app import ConductorConfig

        with pytest.raises(ValidationError):
            ConductorConfig(warning_threshold=1.5)

        with pytest.raises(ValidationError):
            ConductorConfig(warning_threshold=-0.1)

    def test_throttle_threshold_must_be_between_0_and_1(self) -> None:
        """throttle_threshold must be between 0 and 1."""
        from pydantic import ValidationError

        from gobby.config.app import ConductorConfig

        with pytest.raises(ValidationError):
            ConductorConfig(throttle_threshold=1.5)

        with pytest.raises(ValidationError):
            ConductorConfig(throttle_threshold=-0.1)

    def test_daily_budget_cannot_be_negative(self) -> None:
        """daily_budget_usd cannot be negative."""
        from pydantic import ValidationError

        from gobby.config.app import ConductorConfig

        with pytest.raises(ValidationError):
            ConductorConfig(daily_budget_usd=-10.0)

    def test_tracking_window_days_must_be_positive(self) -> None:
        """tracking_window_days must be positive."""
        from pydantic import ValidationError

        from gobby.config.app import ConductorConfig

        with pytest.raises(ValidationError):
            ConductorConfig(tracking_window_days=0)

        with pytest.raises(ValidationError):
            ConductorConfig(tracking_window_days=-1)


class TestDaemonConfigConductorSection:
    """Tests for conductor section in DaemonConfig."""

    def test_daemon_config_has_conductor_section(self) -> None:
        """DaemonConfig includes conductor section."""
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()

        assert hasattr(config, "conductor")
        assert config.conductor is not None

    def test_daemon_config_conductor_defaults(self) -> None:
        """DaemonConfig conductor section has correct defaults."""
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()

        assert config.conductor.daily_budget_usd == 50.0
        assert config.conductor.warning_threshold == 0.8
        assert config.conductor.throttle_threshold == 0.9
        assert config.conductor.tracking_window_days == 7

    def test_daemon_config_from_dict_with_conductor(self) -> None:
        """DaemonConfig parses conductor section from dict."""
        from gobby.config.app import DaemonConfig

        config_dict = {
            "conductor": {
                "daily_budget_usd": 25.0,
                "warning_threshold": 0.75,
                "throttle_threshold": 0.95,
                "tracking_window_days": 30,
            }
        }

        config = DaemonConfig(**config_dict)

        assert config.conductor.daily_budget_usd == 25.0
        assert config.conductor.warning_threshold == 0.75
        assert config.conductor.throttle_threshold == 0.95
        assert config.conductor.tracking_window_days == 30

    def test_daemon_config_partial_conductor_override(self) -> None:
        """DaemonConfig allows partial conductor overrides."""
        from gobby.config.app import DaemonConfig

        config_dict = {
            "conductor": {
                "daily_budget_usd": 100.0,
            }
        }

        config = DaemonConfig(**config_dict)

        assert config.conductor.daily_budget_usd == 100.0
        assert config.conductor.warning_threshold == 0.8  # default
        assert config.conductor.throttle_threshold == 0.9  # default
        assert config.conductor.tracking_window_days == 7  # default
