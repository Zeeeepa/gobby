"""Tests for config consolidation and telemetry cleanup."""

import pytest
from pydantic import ValidationError
from gobby.config.app import DaemonConfig

pytestmark = pytest.mark.unit

def test_old_logging_config_raises_validation_error() -> None:
    """Old configs with 'logging:' key must fail loudly with ValidationError."""
    # This should fail after we remove 'logging' field from DaemonConfig
    # AND set extra='forbid'
    with pytest.raises(ValidationError):
        DaemonConfig(logging={"level": "debug"})
