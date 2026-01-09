"""
Tests for compression/config.py module.

Tests CompressionConfig default values, validation, and serialization.
"""

import pytest
from pydantic import ValidationError

# =============================================================================
# Import Tests
# =============================================================================


class TestCompressionConfigImport:
    """Test that CompressionConfig can be imported."""

    def test_import_from_compression_module(self) -> None:
        """Test importing CompressionConfig from compression package."""
        from gobby.compression import CompressionConfig

        assert CompressionConfig is not None

    def test_import_from_config_module(self) -> None:
        """Test importing CompressionConfig from compression.config."""
        from gobby.compression.config import CompressionConfig

        assert CompressionConfig is not None


# =============================================================================
# Default Values Tests
# =============================================================================


class TestCompressionConfigDefaults:
    """Test CompressionConfig default values."""

    def test_default_instantiation(self) -> None:
        """Test CompressionConfig creates with all defaults."""
        from gobby.compression.config import CompressionConfig

        config = CompressionConfig()
        assert config.enabled is False
        assert config.model == "microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank"
        assert config.device == "auto"
        assert config.cache_enabled is True
        assert config.cache_ttl_seconds == 3600
        assert config.handoff_compression_ratio == 0.5
        assert config.memory_compression_ratio == 0.6
        assert config.context_compression_ratio == 0.4
        assert config.min_content_length == 500
        assert config.fallback_on_error is True

    def test_enabled_override(self) -> None:
        """Test enabling compression."""
        from gobby.compression.config import CompressionConfig

        config = CompressionConfig(enabled=True)
        assert config.enabled is True

    def test_custom_model(self) -> None:
        """Test custom model configuration."""
        from gobby.compression.config import CompressionConfig

        config = CompressionConfig(model="custom/model")
        assert config.model == "custom/model"

    def test_device_options(self) -> None:
        """Test device configuration options."""
        from gobby.compression.config import CompressionConfig

        for device in ["auto", "cuda", "mps", "cpu"]:
            config = CompressionConfig(device=device)
            assert config.device == device


# =============================================================================
# Validation Tests
# =============================================================================


class TestCompressionConfigValidation:
    """Test CompressionConfig validation."""

    def test_negative_cache_ttl_rejected(self) -> None:
        """Test that negative cache TTL is rejected."""
        from gobby.compression.config import CompressionConfig

        with pytest.raises(ValidationError) as exc_info:
            CompressionConfig(cache_ttl_seconds=-1)
        assert "must be non-negative" in str(exc_info.value)

    def test_negative_min_content_length_rejected(self) -> None:
        """Test that negative min_content_length is rejected."""
        from gobby.compression.config import CompressionConfig

        with pytest.raises(ValidationError) as exc_info:
            CompressionConfig(min_content_length=-100)
        assert "must be non-negative" in str(exc_info.value)

    def test_compression_ratio_below_zero_rejected(self) -> None:
        """Test that compression ratio below 0 is rejected."""
        from gobby.compression.config import CompressionConfig

        with pytest.raises(ValidationError) as exc_info:
            CompressionConfig(handoff_compression_ratio=-0.1)
        assert "between 0.0 and 1.0" in str(exc_info.value)

    def test_compression_ratio_above_one_rejected(self) -> None:
        """Test that compression ratio above 1 is rejected."""
        from gobby.compression.config import CompressionConfig

        with pytest.raises(ValidationError) as exc_info:
            CompressionConfig(memory_compression_ratio=1.5)
        assert "between 0.0 and 1.0" in str(exc_info.value)

    def test_valid_compression_ratios(self) -> None:
        """Test valid compression ratio values."""
        from gobby.compression.config import CompressionConfig

        config = CompressionConfig(
            handoff_compression_ratio=0.0,
            memory_compression_ratio=0.5,
            context_compression_ratio=1.0,
        )
        assert config.handoff_compression_ratio == 0.0
        assert config.memory_compression_ratio == 0.5
        assert config.context_compression_ratio == 1.0

    def test_invalid_device_rejected(self) -> None:
        """Test that invalid device value is rejected."""
        from gobby.compression.config import CompressionConfig

        with pytest.raises(ValidationError):
            CompressionConfig(device="invalid")


# =============================================================================
# Serialization Tests
# =============================================================================


class TestCompressionConfigSerialization:
    """Test CompressionConfig serialization."""

    def test_model_dump(self) -> None:
        """Test serialization to dict."""
        from gobby.compression.config import CompressionConfig

        config = CompressionConfig(enabled=True, cache_ttl_seconds=7200)
        data = config.model_dump()

        assert data["enabled"] is True
        assert data["cache_ttl_seconds"] == 7200
        assert "model" in data
        assert "device" in data

    def test_model_dump_json(self) -> None:
        """Test serialization to JSON string."""
        from gobby.compression.config import CompressionConfig

        config = CompressionConfig()
        json_str = config.model_dump_json()

        assert isinstance(json_str, str)
        assert "enabled" in json_str
        assert "model" in json_str

    def test_round_trip(self) -> None:
        """Test serialization and deserialization round trip."""
        from gobby.compression.config import CompressionConfig

        original = CompressionConfig(
            enabled=True,
            model="custom/model",
            device="cuda",
            cache_ttl_seconds=1800,
            handoff_compression_ratio=0.3,
        )
        data = original.model_dump()
        restored = CompressionConfig(**data)

        assert restored.enabled == original.enabled
        assert restored.model == original.model
        assert restored.device == original.device
        assert restored.cache_ttl_seconds == original.cache_ttl_seconds
        assert restored.handoff_compression_ratio == original.handoff_compression_ratio
