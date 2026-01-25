"""LiteLLM-based embedding generation.

This module provides a unified interface for generating embeddings using
LiteLLM, which supports multiple providers through a single API:

| Provider   | Model Format                    | Config                          |
|------------|--------------------------------|--------------------------------|
| OpenAI     | text-embedding-3-small         | OPENAI_API_KEY                  |
| Ollama     | openai/nomic-embed-text        | api_base=http://localhost:11434/v1 |
| Azure      | azure/azure-embedding-model    | api_base, api_key, api_version  |
| Vertex AI  | vertex_ai/text-embedding-004   | GCP credentials                 |
| Gemini     | gemini/text-embedding-004      | GEMINI_API_KEY                  |
| Mistral    | mistral/mistral-embed          | MISTRAL_API_KEY                 |

Example usage:
    from gobby.search.embeddings import generate_embeddings, is_embedding_available

    if is_embedding_available("text-embedding-3-small"):
        embeddings = await generate_embeddings(
            texts=["hello world", "foo bar"],
            model="text-embedding-3-small"
        )
"""

from __future__ import annotations

import logging
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.search.models import SearchConfig

logger = logging.getLogger(__name__)


async def generate_embeddings(
    texts: list[str],
    model: str = "text-embedding-3-small",
    api_base: str | None = None,
    api_key: str | None = None,
) -> list[list[float]]:
    """Generate embeddings using LiteLLM.

    Supports OpenAI, Ollama, Azure, Gemini, Mistral and other providers
    through LiteLLM's unified API.

    Args:
        texts: List of texts to embed
        model: LiteLLM model string (e.g., "text-embedding-3-small",
               "openai/nomic-embed-text" for Ollama)
        api_base: Optional API base URL for custom endpoints (e.g., Ollama)
        api_key: Optional API key (uses environment variable if not set)

    Returns:
        List of embedding vectors (one per input text). Returns an empty
        list if the input texts list is empty.

    Raises:
        RuntimeError: If LiteLLM is not installed or embedding fails
    """
    if not texts:
        return []

    try:
        import litellm
        from litellm.exceptions import (
            AuthenticationError,
            ContextWindowExceededError,
            NotFoundError,
            RateLimitError,
        )
    except ImportError as e:
        raise RuntimeError("litellm package not installed. Run: uv add litellm") from e

    # Build kwargs for LiteLLM
    kwargs: dict[str, str | list[str]] = {
        "model": model,
        "input": texts,
    }

    if api_key:
        kwargs["api_key"] = api_key

    if api_base:
        kwargs["api_base"] = api_base

    try:
        response = await litellm.aembedding(**kwargs)
        embeddings: list[list[float]] = [item["embedding"] for item in response.data]
        logger.debug(f"Generated {len(embeddings)} embeddings via LiteLLM ({model})")
        return embeddings
    except AuthenticationError as e:
        logger.error(f"LiteLLM authentication failed: {e}")
        raise RuntimeError(f"Authentication failed: {e}") from e
    except NotFoundError as e:
        logger.error(f"LiteLLM model not found: {e}")
        raise RuntimeError(f"Model not found: {e}") from e
    except RateLimitError as e:
        logger.error(f"LiteLLM rate limit exceeded: {e}")
        raise RuntimeError(f"Rate limit exceeded: {e}") from e
    except ContextWindowExceededError as e:
        logger.error(f"LiteLLM context window exceeded: {e}")
        raise RuntimeError(f"Context window exceeded: {e}") from e
    except Exception as e:
        logger.error(f"Failed to generate embeddings with LiteLLM: {e}")
        raise RuntimeError(f"Embedding generation failed: {e}") from e


async def generate_embedding(
    text: str,
    model: str = "text-embedding-3-small",
    api_base: str | None = None,
    api_key: str | None = None,
) -> list[float]:
    """Generate embedding for a single text.

    Convenience wrapper around generate_embeddings for single texts.

    Args:
        text: Text to embed
        model: LiteLLM model string
        api_base: Optional API base URL
        api_key: Optional API key

    Returns:
        Embedding vector as list of floats

    Raises:
        RuntimeError: If embedding generation fails
    """
    embeddings = await generate_embeddings(
        texts=[text],
        model=model,
        api_base=api_base,
        api_key=api_key,
    )
    if not embeddings:
        raise RuntimeError(
            f"Embedding API returned empty result for model={model}, "
            f"api_base={api_base}, api_key={'[set]' if api_key else '[not set]'}"
        )
    return embeddings[0]


def is_embedding_available(
    model: str = "text-embedding-3-small",
    api_key: str | None = None,
    api_base: str | None = None,
) -> bool:
    """Check if embedding is available for the given model.

    For local models (Ollama), assumes availability if api_base is set.
    For cloud models, requires an API key.

    Args:
        model: LiteLLM model string
        api_key: Optional explicit API key
        api_base: Optional API base URL

    Returns:
        True if embeddings can be generated, False otherwise
    """
    # Local models with api_base (Ollama, custom endpoints) are assumed available
    if api_base:
        return True

    # Check for Ollama-style models that use local endpoints
    if model.startswith("ollama/"):
        # Native Ollama models - assume available locally
        # In practice, we'll catch connection errors at runtime
        return True

    # openai/ prefix models require OpenAI API key
    if model.startswith("openai/"):
        effective_key = api_key or os.environ.get("OPENAI_API_KEY")
        return effective_key is not None and len(effective_key) > 0

    # Cloud models need API key
    effective_key = api_key

    # Check environment variables based on model prefix
    if not effective_key:
        if model.startswith("gemini/"):
            effective_key = os.environ.get("GEMINI_API_KEY")
        elif model.startswith("mistral/"):
            effective_key = os.environ.get("MISTRAL_API_KEY")
        elif model.startswith("azure/"):
            effective_key = os.environ.get("AZURE_API_KEY")
        elif model.startswith("vertex_ai/"):
            # Vertex AI uses GCP credentials, check for project
            effective_key = os.environ.get("VERTEXAI_PROJECT")
        else:
            # Default to OpenAI
            effective_key = os.environ.get("OPENAI_API_KEY")

    return effective_key is not None and len(effective_key) > 0


def is_embedding_available_for_config(config: SearchConfig) -> bool:
    """Check if embedding is available for a SearchConfig.

    Convenience wrapper that extracts config values.

    Args:
        config: SearchConfig to check

    Returns:
        True if embeddings can be generated, False otherwise
    """
    return is_embedding_available(
        model=config.embedding_model,
        api_key=config.embedding_api_key,
        api_base=config.embedding_api_base,
    )


async def generate_embeddings_for_config(
    texts: list[str],
    config: SearchConfig,
) -> list[list[float]]:
    """Generate embeddings using a SearchConfig.

    Convenience wrapper that extracts config values.

    Args:
        texts: List of texts to embed
        config: SearchConfig with model and API settings

    Returns:
        List of embedding vectors
    """
    return await generate_embeddings(
        texts=texts,
        model=config.embedding_model,
        api_base=config.embedding_api_base,
        api_key=config.embedding_api_key,
    )
