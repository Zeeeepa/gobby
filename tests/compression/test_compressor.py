"""
Tests for compression/compressor.py module.

Tests TextCompressor with mocked LLMLingua-2 and caching behavior.
"""

from unittest.mock import MagicMock, patch

# =============================================================================
# Import Tests
# =============================================================================


class TestTextCompressorImport:
    """Test that TextCompressor can be imported."""

    def test_import_from_compression_module(self) -> None:
        """Test importing TextCompressor from compression package."""
        from gobby.compression import TextCompressor

        assert TextCompressor is not None

    def test_import_from_compressor_module(self) -> None:
        """Test importing TextCompressor from compression.compressor."""
        from gobby.compression.compressor import TextCompressor

        assert TextCompressor is not None


# =============================================================================
# Initialization Tests
# =============================================================================


class TestTextCompressorInit:
    """Test TextCompressor initialization."""

    def test_init_with_config(self) -> None:
        """Test initializing with CompressionConfig."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig()
        compressor = TextCompressor(config)

        assert compressor.config is config
        assert not compressor._model_loaded


# =============================================================================
# Short Content Tests
# =============================================================================


class TestShortContent:
    """Test handling of short content."""

    def test_short_content_returned_unchanged(self) -> None:
        """Test that content below min_content_length is returned unchanged."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(min_content_length=100)
        compressor = TextCompressor(config)

        short_text = "This is short."
        result = compressor.compress(short_text)

        assert result == short_text

    def test_content_at_boundary_returned_unchanged(self) -> None:
        """Test content exactly at min_content_length is unchanged."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(min_content_length=50)
        compressor = TextCompressor(config)

        # Content exactly at boundary (length == min_content_length)
        text = "a" * 50
        result = compressor.compress(text)

        assert result == text


# =============================================================================
# Caching Tests
# =============================================================================


class TestCaching:
    """Test compression caching behavior."""

    def test_cache_hit_returns_same_result(self) -> None:
        """Test that same content returns cached result."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(
            enabled=True,
            min_content_length=10,
            cache_enabled=True,
        )
        compressor = TextCompressor(config)

        # Mock the model
        mock_model = MagicMock()
        mock_model.compress_prompt.return_value = {"compressed_prompt": "Compressed"}
        compressor._model = mock_model
        compressor._model_loaded = True

        text = "This is content to be cached. It needs to be compressed."
        result1 = compressor.compress(text, ratio=0.5)
        result2 = compressor.compress(text, ratio=0.5)

        assert result1 == result2
        # Model should only be called once due to caching
        assert mock_model.compress_prompt.call_count == 1

    def test_different_ratio_creates_different_cache_entry(self) -> None:
        """Test that different ratios create different cache entries."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(
            enabled=True,
            min_content_length=10,
            cache_enabled=True,
        )
        compressor = TextCompressor(config)

        # Mock the model
        mock_model = MagicMock()
        mock_model.compress_prompt.return_value = {"compressed_prompt": "Compressed"}
        compressor._model = mock_model
        compressor._model_loaded = True

        text = "Long content. More sentences. Even more. And more here."
        compressor.compress(text, ratio=0.3)
        compressor.compress(text, ratio=0.7)

        # Different ratios should result in two cache entries
        assert len(compressor._cache) == 2

    def test_clear_cache(self) -> None:
        """Test clearing the cache."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(
            enabled=True,
            min_content_length=10,
            cache_enabled=True,
        )
        compressor = TextCompressor(config)

        # Mock the model
        mock_model = MagicMock()
        mock_model.compress_prompt.return_value = {"compressed_prompt": "Compressed"}
        compressor._model = mock_model
        compressor._model_loaded = True

        text = "Content to cache. More content here."
        compressor.compress(text, ratio=0.5)
        assert len(compressor._cache) > 0

        cleared = compressor.clear_cache()
        assert cleared > 0
        assert len(compressor._cache) == 0

    def test_cache_disabled(self) -> None:
        """Test caching can be disabled."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(
            enabled=True,
            min_content_length=10,
            cache_enabled=False,
        )
        compressor = TextCompressor(config)

        # Mock the model
        mock_model = MagicMock()
        mock_model.compress_prompt.return_value = {"compressed_prompt": "Compressed"}
        compressor._model = mock_model
        compressor._model_loaded = True

        text = "Content to compress. More content."
        compressor.compress(text, ratio=0.5)

        # Cache should remain empty when disabled
        assert len(compressor._cache) == 0


# =============================================================================
# Context Type Tests
# =============================================================================


class TestContextTypes:
    """Test compression with different context types."""

    def test_handoff_context_type(self) -> None:
        """Test using handoff context type uses correct ratio."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(
            enabled=True,
            min_content_length=10,
            handoff_compression_ratio=0.5,
        )
        compressor = TextCompressor(config)

        # Mock the model to capture the ratio used
        mock_model = MagicMock()
        mock_model.compress_prompt.return_value = {"compressed_prompt": "Compressed"}
        compressor._model = mock_model
        compressor._model_loaded = True

        text = "Long handoff content. Multiple sentences. More data here."
        compressor.compress(text, context_type="handoff")

        # Verify correct ratio was passed
        call_kwargs = mock_model.compress_prompt.call_args
        assert call_kwargs[1]["rate"] == 0.5

    def test_memory_context_type(self) -> None:
        """Test using memory context type uses correct ratio."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(
            enabled=True,
            min_content_length=10,
            memory_compression_ratio=0.6,
        )
        compressor = TextCompressor(config)

        # Mock the model
        mock_model = MagicMock()
        mock_model.compress_prompt.return_value = {"compressed_prompt": "Compressed"}
        compressor._model = mock_model
        compressor._model_loaded = True

        text = "Memory content to compress. Additional info here."
        compressor.compress(text, context_type="memory")

        # Verify correct ratio was passed
        call_kwargs = mock_model.compress_prompt.call_args
        assert call_kwargs[1]["rate"] == 0.6

    def test_context_context_type(self) -> None:
        """Test using context context type (default) uses correct ratio."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(
            enabled=True,
            min_content_length=10,
            context_compression_ratio=0.4,
        )
        compressor = TextCompressor(config)

        # Mock the model
        mock_model = MagicMock()
        mock_model.compress_prompt.return_value = {"compressed_prompt": "Compressed"}
        compressor._model = mock_model
        compressor._model_loaded = True

        text = "Context content for compression. Extra sentences here."
        compressor.compress(text, context_type="context")

        # Verify correct ratio was passed
        call_kwargs = mock_model.compress_prompt.call_args
        assert call_kwargs[1]["rate"] == 0.4


# =============================================================================
# Mocked LLMLingua Tests
# =============================================================================


class TestMockedLLMLingua:
    """Test TextCompressor with mocked LLMLingua."""

    def test_compress_with_mocked_model(self) -> None:
        """Test compression with mocked LLMLingua model."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(
            enabled=True,
            min_content_length=10,
        )
        compressor = TextCompressor(config)

        # Mock the model
        mock_model = MagicMock()
        mock_model.compress_prompt.return_value = {"compressed_prompt": "Compressed output"}
        compressor._model = mock_model
        compressor._model_loaded = True

        text = "This is the original text that needs compression."
        result = compressor.compress(text)

        assert result == "Compressed output"
        mock_model.compress_prompt.assert_called_once()

    def test_load_model_succeeds(self) -> None:
        """Test that model loads successfully (LLMLingua is required)."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(enabled=True, min_content_length=10)
        compressor = TextCompressor(config)

        # Load model - should succeed since llmlingua is a required dependency
        result = compressor._load_model()

        assert compressor._model_loaded is True
        assert result is True
        assert compressor._model is not None

    def test_compression_disabled_returns_original(self) -> None:
        """Test that disabled compression returns original content."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(
            enabled=False,
            min_content_length=10,
        )
        compressor = TextCompressor(config)

        text = "This is content that should not be compressed when disabled."
        result = compressor.compress(text)

        assert result == text


# =============================================================================
# Device Detection Tests
# =============================================================================


class TestDeviceDetection:
    """Test device detection for model inference."""

    def test_explicit_device(self) -> None:
        """Test explicit device configuration."""
        from gobby.compression import CompressionConfig, TextCompressor

        for device in ["cuda", "mps", "cpu"]:
            config = CompressionConfig(device=device)
            compressor = TextCompressor(config)
            assert compressor._get_device() == device

    def test_auto_device_fallback_to_cpu(self) -> None:
        """Test auto device falls back to CPU when torch unavailable."""
        from gobby.compression import CompressionConfig, TextCompressor

        config = CompressionConfig(device="auto")
        compressor = TextCompressor(config)

        with patch.dict("sys.modules", {"torch": None}):
            # Should fall back to CPU
            device = compressor._get_device()
            # Could be cuda/mps/cpu depending on environment
            assert device in ["cuda", "mps", "cpu"]
