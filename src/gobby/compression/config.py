"""
Compression configuration module.

Contains Pydantic config model for LLMLingua-2 compression settings including
compression ratios, model selection, device configuration, and caching options.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

__all__ = [
    "CompressionConfig",
]


DeviceType = Literal["auto", "cuda", "mps", "cpu"]


class CompressionConfig(BaseModel):
    """LLMLingua-2 compression configuration."""

    enabled: bool = Field(
        default=False,
        description="Enable LLMLingua-2 prompt compression",
    )
    model: str = Field(
        default="microsoft/llmlingua-2-bert-base-multilingual-cased-meetingbank",
        description="HuggingFace model ID for LLMLingua-2 compression",
    )
    device: DeviceType = Field(
        default="auto",
        description="Device for model inference (auto, cuda, mps, cpu)",
    )
    cache_enabled: bool = Field(
        default=True,
        description="Enable hash-based caching of compressed content",
    )
    cache_ttl_seconds: int = Field(
        default=3600,
        description="Time-to-live for cached compressions in seconds",
    )
    handoff_compression_ratio: float = Field(
        default=0.5,
        description="Target compression ratio for session handoffs (0.0-1.0)",
    )
    memory_compression_ratio: float = Field(
        default=0.6,
        description="Target compression ratio for memory injection (0.0-1.0)",
    )
    context_compression_ratio: float = Field(
        default=0.4,
        description="Target compression ratio for context resolution (0.0-1.0)",
    )
    min_content_length: int = Field(
        default=500,
        description="Minimum content length (chars) to trigger compression",
    )
    fallback_on_error: bool = Field(
        default=True,
        description="Fall back to smart truncation if LLMLingua fails",
    )

    @field_validator("cache_ttl_seconds", "min_content_length")
    @classmethod
    def validate_positive(cls, v: int) -> int:
        """Validate value is non-negative."""
        if v < 0:
            raise ValueError("Value must be non-negative")
        return v

    @field_validator(
        "handoff_compression_ratio",
        "memory_compression_ratio",
        "context_compression_ratio",
    )
    @classmethod
    def validate_ratio(cls, v: float) -> float:
        """Validate compression ratio is between 0.0 and 1.0."""
        if not (0.0 <= v <= 1.0):
            raise ValueError("Compression ratio must be between 0.0 and 1.0")
        return v
