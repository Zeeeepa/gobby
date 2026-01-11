"""
Text compressor module using LLMLingua-2.

Provides semantic text compression at retrieval/injection time with lazy model
loading and hash-based caching.
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
    LLMLingua-2 text compressor with caching.

    Compresses text content while preserving semantic meaning using the
    LLMLingua-2 model. Features lazy model loading to avoid startup overhead
    and hash-based caching for repeated compressions.

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

        from llmlingua import PromptCompressor

        device = self._get_device()
        logger.info(f"Loading LLMLingua-2 model on {device}...")

        self._model = PromptCompressor(
            model_name=self._config.model,
            device_map=device,
        )
        logger.info("LLMLingua-2 model loaded successfully")
        return True

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
            Compressed text, or original if compression disabled or content too short
        """
        # Skip short content
        if len(content) < self._config.min_content_length:
            return content

        # Skip if compression disabled
        if not self._load_model():
            return content

        # Determine compression ratio
        effective_ratio = ratio if ratio is not None else self._get_ratio_for_context(context_type)

        # Check cache
        cache_key = self._cache_key(content, effective_ratio)
        cached = self._get_cached(cache_key)
        if cached is not None:
            logger.debug(f"Cache hit for compression (key={cache_key[:8]})")
            return cached

        # Compress with LLMLingua
        try:
            result = self._model.compress_prompt(
                content,
                rate=effective_ratio,
                force_tokens=[".", "!", "?", "\n"],  # Preserve sentence structure
            )
        except TypeError as e:
            # LLMLingua-2 passes past_key_values to BERT models which don't support it
            # in transformers 4.43+. See: https://github.com/microsoft/LLMLingua/issues/232
            if "past_key_values" in str(e):
                logger.warning(
                    "LLMLingua compression failed due to transformers compatibility issue "
                    "(past_key_values not supported by BERT models in transformers 4.43+). "
                    "Returning uncompressed content. See: https://github.com/microsoft/LLMLingua/issues/232"
                )
                return content
            raise
        compressed: str = result.get("compressed_prompt", content)
        self._set_cached(cache_key, compressed)
        logger.debug(
            f"Compressed {len(content)} -> {len(compressed)} chars "
            f"({len(compressed) / len(content):.1%})"
        )
        return compressed

    def clear_cache(self) -> int:
        """
        Clear the compression cache.

        Returns:
            Number of entries cleared
        """
        count = len(self._cache)
        self._cache.clear()
        return count
