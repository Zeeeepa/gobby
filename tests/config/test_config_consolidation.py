"""Tests for config consolidation and telemetry cleanup."""

import pytest

from gobby.config.app import DaemonConfig

pytestmark = pytest.mark.unit


def test_old_logging_config_silently_ignored() -> None:
    """DaemonConfig uses extra='ignore', so stale keys from DB are dropped silently."""
    # extra='ignore' was set in c70d6299 to allow startup when DB has
    # removed keys (logging, title_synthesis, rules, ui_settings).
    cfg = DaemonConfig(logging={"level": "debug"})
    assert not hasattr(cfg, "logging")
