"""EmbeddingProvider abstraction for semantic skill search.

This module provides a Protocol-based abstraction for embedding providers,
with an OpenAI implementation that uses text-embedding-3-small by default.

The abstraction allows:
- Swapping embedding providers without changing search code
- Graceful fallback to TF-IDF when embeddings are unavailable
- Batch embedding for efficiency

Example usage:
    ```python
    from gobby.skills.embeddings import get_embedding_provider, is_embedding_available

    if is_embedding_available():
        provider = get_embedding_provider()
        embedding = await provider.embed("search query")
    else:
        # Fall back to TF-IDF search
        pass
    ```
"""

from __future__ import annotations

import logging
import os
from typing import Protocol, runtime_checkable

logger = logging.getLogger(__name__)

# Default model and dimensions
DEFAULT_MODEL = "text-embedding-3-small"
DEFAULT_DIMENSION = 1536


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Protocol for embedding providers.

    Defines the interface for generating text embeddings that can be used
    for semantic similarity search.

    Attributes:
        dimension: The dimension of embedding vectors produced by this provider.

    Methods:
        embed: Generate embedding for a single text.
        embed_batch: Generate embeddings for multiple texts.
    """

    @property
    def dimension(self) -> int:
        """Return the dimension of embedding vectors."""
        ...

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as list of floats.

        Raises:
            RuntimeError: If embedding generation fails.
        """
        ...

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        More efficient than calling embed() multiple times as it batches
        the API request.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.

        Raises:
            RuntimeError: If embedding generation fails.
        """
        ...


class OpenAIEmbeddingProvider:
    """OpenAI embedding provider using text-embedding-3-small.

    Uses LiteLLM under the hood for API compatibility and automatic retries.

    Args:
        model: Model name (default: text-embedding-3-small).
        dimension: Embedding dimension (default: 1536 for text-embedding-3-small).
        api_key: OpenAI API key. If not provided, reads from OPENAI_API_KEY env var.

    Example:
        ```python
        provider = OpenAIEmbeddingProvider(api_key="sk-...")
        embedding = await provider.embed("Hello, world!")
        ```
    """

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        dimension: int = DEFAULT_DIMENSION,
        api_key: str | None = None,
    ):
        """Initialize the OpenAI embedding provider."""
        self._model = model
        self._dimension = dimension
        self._api_key = api_key

    @property
    def dimension(self) -> int:
        """Return the dimension of embedding vectors."""
        return self._dimension

    @property
    def model(self) -> str:
        """Return the model name."""
        return self._model

    def _get_api_key(self) -> str:
        """Get API key from instance or environment.

        Returns:
            API key string.

        Raises:
            RuntimeError: If no API key is available.
        """
        api_key = self._api_key or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OPENAI_API_KEY not configured. Set it in environment or pass api_key to provider."
            )
        return api_key

    async def embed(self, text: str) -> list[float]:
        """Generate embedding for a single text.

        Args:
            text: Text to embed.

        Returns:
            Embedding vector as list of floats.

        Raises:
            RuntimeError: If embedding generation fails or API key not configured.
        """
        import litellm

        api_key = self._get_api_key()

        try:
            response = await litellm.aembedding(
                model=self._model,
                input=[text],
                api_key=api_key,
            )
            embedding: list[float] = response.data[0]["embedding"]
            logger.debug(f"Generated embedding with {len(embedding)} dimensions")
            return embedding
        except Exception as e:
            logger.error(f"Failed to generate embedding: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    async def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts.

        Args:
            texts: List of texts to embed.

        Returns:
            List of embedding vectors.

        Raises:
            RuntimeError: If embedding generation fails or API key not configured.
        """
        import litellm

        if not texts:
            return []

        api_key = self._get_api_key()

        try:
            response = await litellm.aembedding(
                model=self._model,
                input=texts,
                api_key=api_key,
            )
            embeddings: list[list[float]] = [item["embedding"] for item in response.data]
            logger.debug(f"Generated {len(embeddings)} embeddings in batch")
            return embeddings
        except Exception as e:
            logger.error(f"Failed to generate batch embeddings: {e}")
            raise RuntimeError(f"Batch embedding generation failed: {e}") from e


def get_embedding_provider(
    api_key: str | None = None,
    model: str = DEFAULT_MODEL,
    dimension: int = DEFAULT_DIMENSION,
) -> OpenAIEmbeddingProvider | None:
    """Get an embedding provider if one is available.

    This function provides graceful fallback - returns None if no API key
    is configured, allowing callers to fall back to TF-IDF search.

    Args:
        api_key: Optional explicit API key.
        model: Model name (default: text-embedding-3-small).
        dimension: Embedding dimension (default: 1536).

    Returns:
        OpenAIEmbeddingProvider if configured, None otherwise.

    Example:
        ```python
        provider = get_embedding_provider()
        if provider:
            embedding = await provider.embed("query")
        else:
            # Fall back to TF-IDF
            pass
        ```
    """
    # Check for API key
    effective_key = api_key or os.environ.get("OPENAI_API_KEY")
    if not effective_key:
        logger.debug("No OpenAI API key available, embeddings disabled")
        return None

    return OpenAIEmbeddingProvider(
        model=model,
        dimension=dimension,
        api_key=effective_key,
    )


def is_embedding_available(api_key: str | None = None) -> bool:
    """Check if embedding functionality is available.

    Args:
        api_key: Optional explicit API key to check.

    Returns:
        True if embeddings can be generated, False otherwise.
    """
    effective_key = api_key or os.environ.get("OPENAI_API_KEY")
    return effective_key is not None and len(effective_key) > 0
