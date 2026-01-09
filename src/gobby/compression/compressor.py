"""
Text compressor module using LLMLingua-2.

Provides semantic text compression at retrieval/injection time with lazy model
loading, hash-based caching, and graceful fallback to smart truncation.
"""

from __future__ import annotations

import hashlib
import logging
import time
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from gobby.compression.config import CompressionConfig

logger = logging.getLogger(__name__)

__all__ = [
    "TextCompressor",
]

ContextType = Literal["handoff", "memory", "context"]


class TextCompressor:
    """
    LLMLingua-2 text compressor with caching and fallback.

    Compresses text content while preserving semantic meaning using the
    LLMLingua-2 model. Features lazy model loading to avoid startup overhead,
    hash-based caching for repeated compressions, and graceful fallback to
    smart truncation when LLMLingua is unavailable.

    Example:
        config = CompressionConfig(enabled=True)
        compressor = TextCompressor(config)
        compressed = compressor.compress(long_text, context_type="handoff")
    """

    def __init__(self, config: CompressionConfig) -> None:
        """
        Initialize the compressor with configuration.

        Args:
            config: CompressionConfig with compression settings
        """
        self._config = config
        self._model: Any = None
        self._model_loaded = False
        self._cache: dict[str, tuple[str, float]] = {}  # hash -> (result, timestamp)

    @property
    def config(self) -> CompressionConfig:
        """Get the compression configuration."""
        return self._config

    @property
    def is_available(self) -> bool:
        """Check if LLMLingua-2 is available for import."""
        if not self._config.enabled:
            return False
        try:
            import llmlingua  # noqa: F401

            return True
        except ImportError:
            return False

    def _get_device(self) -> str:
        """Determine the best available device for inference."""
        if self._config.device != "auto":
            return self._config.device

        try:
            import torch

            if torch.cuda.is_available():
                return "cuda"
            elif torch.backends.mps.is_available():
                return "mps"
        except ImportError:
            pass
        return "cpu"

    def _load_model(self) -> bool:
        """
        Lazily load the LLMLingua-2 model.

        Returns:
            True if model loaded successfully, False otherwise
        """
        if self._model_loaded:
            return self._model is not None

        self._model_loaded = True

        if not self._config.enabled:
            logger.debug("Compression disabled in config")
            return False

        try:
            from llmlingua import PromptCompressor

            device = self._get_device()
            logger.info(f"Loading LLMLingua-2 model on {device}...")

            self._model = PromptCompressor(
                model_name=self._config.model,
                device_map=device,
            )
            logger.info("LLMLingua-2 model loaded successfully")
            return True

        except ImportError:
            logger.warning(
                "LLMLingua not installed. Install with: uv pip install gobby[compression]"
            )
            return False
        except Exception as e:
            logger.error(f"Failed to load LLMLingua-2 model: {e}")
            return False

    def _get_ratio_for_context(self, context_type: ContextType) -> float:
        """Get the compression ratio for a specific context type."""
        ratios = {
            "handoff": self._config.handoff_compression_ratio,
            "memory": self._config.memory_compression_ratio,
            "context": self._config.context_compression_ratio,
        }
        return ratios.get(context_type, 0.5)

    def _cache_key(self, content: str, ratio: float) -> str:
        """Generate a cache key for content and ratio combination."""
        key_material = f"{content}:{ratio}"
        return hashlib.sha256(key_material.encode()).hexdigest()[:16]

    def _get_cached(self, key: str) -> str | None:
        """Get cached result if valid, cleaning expired entries."""
        if not self._config.cache_enabled:
            return None

        now = time.time()

        # Clean expired entries
        expired = [
            k for k, (_, ts) in self._cache.items() if now - ts > self._config.cache_ttl_seconds
        ]
        for k in expired:
            del self._cache[k]

        # Return cached result if exists
        if key in self._cache:
            result, _ = self._cache[key]
            return result
        return None

    def _set_cached(self, key: str, result: str) -> None:
        """Cache a compression result."""
        if self._config.cache_enabled:
            self._cache[key] = (result, time.time())

    def _fallback_truncate(self, content: str, ratio: float) -> str:
        """
        Smart truncation fallback when LLMLingua unavailable.

        Preserves content structure by truncating at sentence boundaries
        when possible.

        Args:
            content: Text to truncate
            ratio: Target ratio (0.0-1.0, lower = more compression)

        Returns:
            Truncated text
        """
        target_length = int(len(content) * ratio)
        if target_length >= len(content):
            return content

        # Try to truncate at sentence boundary
        truncated = content[:target_length]
        for sep in [". ", ".\n", "! ", "!\n", "? ", "?\n"]:
            last_sep = truncated.rfind(sep)
            if last_sep > target_length * 0.7:  # Don't truncate too aggressively
                return truncated[: last_sep + 1].strip()

        # Fall back to word boundary
        last_space = truncated.rfind(" ")
        if last_space > target_length * 0.8:
            return truncated[:last_space].strip() + "..."

        return truncated.strip() + "..."

    def compress(
        self,
        content: str,
        context_type: ContextType = "context",
        ratio: float | None = None,
    ) -> str:
        """
        Compress text content using LLMLingua-2.

        Args:
            content: Text content to compress
            context_type: Type of context for ratio selection (handoff, memory, context)
            ratio: Override compression ratio (0.0-1.0, lower = more compression)

        Returns:
            Compressed text, or original/truncated text on failure
        """
        # Skip short content
        if len(content) < self._config.min_content_length:
            return content

        # Determine compression ratio
        effective_ratio = ratio if ratio is not None else self._get_ratio_for_context(context_type)

        # Check cache
        cache_key = self._cache_key(content, effective_ratio)
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for compression (key={cache_key[:8]})")
            return cached

        # Try LLMLingua compression
        if self._load_model() and self._model is not None:
            try:
                result = self._model.compress_prompt(
                    content,
                    rate=effective_ratio,
                    force_tokens=[".", "!", "?", "\n"],  # Preserve sentence structure
                )
                compressed = result.get("compressed_prompt", content)
                self._set_cached(cache_key, compressed)
                logger.debug(
                    f"Compressed {len(content)} -> {len(compressed)} chars "
                    f"({len(compressed) / len(content):.1%})"
                )
                return compressed
            except Exception as e:
                logger.warning(f"LLMLingua compression failed: {e}")
                if not self._config.fallback_on_error:
                    return content

        # Fallback to smart truncation
        if self._config.fallback_on_error:
            logger.debug("Using fallback truncation")
            truncated = self._fallback_truncate(content, effective_ratio)
            self._set_cached(cache_key, truncated)
            return truncated

        return content

    def clear_cache(self) -> int:
        """
        Clear the compression cache.

        Returns:
            Number of entries cleared
        """
        count = len(self._cache)
        self._cache.clear()
        return count
