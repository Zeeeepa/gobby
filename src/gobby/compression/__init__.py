"""
Compression module for LLMLingua-2 prompt compression.

Provides text compression at retrieval/injection time for session handoffs,
memories, and context resolution. Stores verbose content, compresses when
injecting into LLM context.

Public API:
    - CompressionConfig: Pydantic config model for compression settings
    - TextCompressor: LLMLingua-2 wrapper with caching and fallback
"""

from gobby.compression.config import CompressionConfig

__all__ = [
    "CompressionConfig",
]
