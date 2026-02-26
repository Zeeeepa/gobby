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

import asyncio
import logging
import os
import random
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.search.models import SearchConfig

logger = logging.getLogger(__name__)

# Default retry settings for rate-limited requests
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_BASE_DELAY = 1.0  # seconds
_DEFAULT_MAX_DELAY = 60.0  # seconds


async def generate_embeddings(
    texts: list[str],
    model: str = "text-embedding-3-small",
    api_base: str | None = None,
    api_key: str | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    base_delay: float = _DEFAULT_BASE_DELAY,
) -> list[list[float]]:
    """Generate embeddings using LiteLLM with exponential backoff.

    Supports OpenAI, Ollama, Azure, Gemini, Mistral and other providers
    through LiteLLM's unified API. Rate limit errors are retried with
    exponential backoff; non-retryable errors (auth, model not found,
    context window) fail immediately.

    Args:
        texts: List of texts to embed
        model: LiteLLM model string (e.g., "text-embedding-3-small",
               "openai/nomic-embed-text" for Ollama)
        api_base: Optional API base URL for custom endpoints (e.g., Ollama)
        api_key: Optional API key (uses environment variable if not set)
        max_retries: Maximum retry attempts for rate limit errors (default: 5)
        base_delay: Initial backoff delay in seconds (default: 1.0)

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
    kwargs: dict[str, str | int | list[str]] = {
        "model": model,
        "input": texts,
        "num_retries": 0,  # Disable LiteLLM's internal retries; we handle backoff
    }

    if api_key:
        kwargs["api_key"] = api_key

    if api_base:
        kwargs["api_base"] = api_base

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
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
        except ContextWindowExceededError as e:
            logger.error(f"LiteLLM context window exceeded: {e}")
            raise RuntimeError(f"Context window exceeded: {e}") from e
        except RateLimitError as e:
            last_error = e
            if attempt == max_retries:
                break
            delay = min(base_delay * (2**attempt), _DEFAULT_MAX_DELAY) * random.uniform(0.8, 1.2)  # nosec B311
            logger.warning(
                f"Rate limited (attempt {attempt + 1}/{max_retries + 1}), retrying in {delay:.1f}s"
            )
            await asyncio.sleep(delay)
        except Exception as e:
            logger.error(f"Failed to generate embeddings with LiteLLM: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    logger.error(f"LiteLLM rate limit exceeded after {max_retries + 1} attempts: {last_error}")
    raise RuntimeError(
        f"Rate limit exceeded after {max_retries + 1} attempts: {last_error}"
    ) from last_error


async def generate_embedding(
    text: str,
    model: str = "text-embedding-3-small",
    api_base: str | None = None,
    api_key: str | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    base_delay: float = _DEFAULT_BASE_DELAY,
) -> list[float]:
    """Generate embedding for a single text.

    Convenience wrapper around generate_embeddings for single texts.

    Args:
        text: Text to embed
        model: LiteLLM model string
        api_base: Optional API base URL
        api_key: Optional API key
        max_retries: Maximum retry attempts for rate limit errors
        base_delay: Initial backoff delay in seconds

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
        max_retries=max_retries,
        base_delay=base_delay,
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
