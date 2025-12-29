import pytest
from pydantic import ValidationError

from gobby.config.app import SkillSyncConfig


def test_skill_sync_config_defaults() -> None:
    """Test default values for SkillSyncConfig."""
    config = SkillSyncConfig()
    assert config.enabled is True
    assert config.stealth is False
    assert config.export_debounce == 5.0


def test_skill_sync_config_validation() -> None:
    """Test validation for SkillSyncConfig."""
    # Test valid config
    config = SkillSyncConfig(export_debounce=1.0)
    assert config.export_debounce == 1.0

    # Test invalid export_debounce (negative)
    with pytest.raises(ValidationError) as excinfo:
        SkillSyncConfig(export_debounce=-1.0)
    assert "Value must be non-negative" in str(excinfo.value)

    # Test invalid export_debounce (zero is valid as it's non-negative)
    config = SkillSyncConfig(export_debounce=0.0)
    assert config.export_debounce == 0.0
