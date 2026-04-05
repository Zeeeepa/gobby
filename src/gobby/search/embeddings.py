"""Embedding generation via OpenAI-compatible API.

Uses the ``openai`` package (already a dependency) which works with any
OpenAI-compatible endpoint: OpenAI cloud, Ollama, LM Studio, etc.

| Provider   | Model                          | Config                                    |
|------------|-------------------------------|-------------------------------------------|
| Ollama     | nomic-embed-text              | api_base=http://localhost:11434/v1        |
| LM Studio  | nomic-embed-text              | api_base=http://localhost:1234/v1         |
| OpenAI     | text-embedding-3-small        | OPENAI_API_KEY                            |

Example usage:
    from gobby.search.embeddings import generate_embeddings, is_embedding_available

    if is_embedding_available("nomic-embed-text", api_base="http://localhost:1234/v1"):
        embeddings = await generate_embeddings(
            texts=["hello world", "foo bar"],
            model="nomic-embed-text",
            api_base="http://localhost:1234/v1",
        )
"""

from __future__ import annotations

import asyncio
import logging
import os
import random

logger = logging.getLogger(__name__)

# Default retry settings for rate-limited requests
_DEFAULT_MAX_RETRIES = 5
_DEFAULT_BASE_DELAY = 1.0  # seconds
_DEFAULT_MAX_DELAY = 60.0  # seconds


async def generate_embeddings(
    texts: list[str],
    model: str = "nomic-embed-text",
    api_base: str | None = None,
    api_key: str | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    base_delay: float = _DEFAULT_BASE_DELAY,
    is_query: bool = False,
) -> list[list[float]]:
    """Generate embeddings using an OpenAI-compatible API with exponential backoff.

    Works with any OpenAI-compatible endpoint (OpenAI cloud, Ollama, LM Studio).
    Rate limit errors are retried with exponential backoff; non-retryable errors
    (auth, model not found) fail immediately.

    Args:
        texts: List of texts to embed
        model: Model name (e.g., "nomic-embed-text", "text-embedding-3-small")
        api_base: API base URL for OpenAI-compatible endpoint (e.g., "http://localhost:1234/v1" for LM Studio)
        api_key: Optional API key (uses env var OPENAI_API_KEY if not set)
        max_retries: Maximum retry attempts for rate limit errors (default: 5)
        base_delay: Initial backoff delay in seconds (default: 1.0)
        is_query: Whether this is a query embedding (unused, kept for compat)

    Returns:
        List of embedding vectors (one per input text). Returns an empty
        list if the input texts list is empty.

    Raises:
        RuntimeError: If embedding generation fails
    """
    if not texts:
        return []

    from openai import AsyncOpenAI, AuthenticationError, NotFoundError, RateLimitError

    # Use "unused" as default key for local endpoints (Ollama doesn't need a key)
    effective_key = api_key or os.environ.get("OPENAI_API_KEY") or "unused"
    client = AsyncOpenAI(base_url=api_base, api_key=effective_key)

    last_error: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            response = await client.embeddings.create(model=model, input=texts)
            embeddings: list[list[float]] = [item.embedding for item in response.data]
            logger.debug(f"Generated {len(embeddings)} embeddings ({model})")
            return embeddings
        except AuthenticationError as e:
            logger.error(f"Embedding authentication failed: {e}")
            raise RuntimeError(f"Authentication failed: {e}") from e
        except NotFoundError as e:
            logger.error(f"Embedding model not found: {e}")
            raise RuntimeError(f"Model not found: {e}") from e
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
            logger.error(f"Failed to generate embeddings: {e}")
            raise RuntimeError(f"Embedding generation failed: {e}") from e

    logger.error(f"Rate limit exceeded after {max_retries + 1} attempts: {last_error}")
    raise RuntimeError(
        f"Rate limit exceeded after {max_retries + 1} attempts: {last_error}"
    ) from last_error


async def generate_embedding(
    text: str,
    model: str = "nomic-embed-text",
    api_base: str | None = None,
    api_key: str | None = None,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    base_delay: float = _DEFAULT_BASE_DELAY,
    is_query: bool = False,
) -> list[float]:
    """Generate embedding for a single text.

    Convenience wrapper around generate_embeddings for single texts.

    Args:
        text: Text to embed
        model: Model name
        api_base: Optional API base URL
        api_key: Optional API key
        max_retries: Maximum retry attempts for rate limit errors
        base_delay: Initial backoff delay in seconds
        is_query: Whether this is a query embedding

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
        is_query=is_query,
    )
    if not embeddings:
        raise RuntimeError(
            f"Embedding API returned empty result for model={model}, "
            f"api_base={api_base}, api_key={'[set]' if api_key else '[not set]'}"
        )
    return embeddings[0]


def is_embedding_available(
    model: str = "nomic-embed-text",
    api_key: str | None = None,
    api_base: str | None = None,
) -> bool:
    """Check if embedding is available for the given model.

    If api_base is set (LM Studio, Ollama, custom endpoints), assumes available.
    Otherwise, requires an API key.

    Args:
        model: Model name
        api_key: Optional explicit API key
        api_base: Optional API base URL

    Returns:
        True if embeddings can be generated, False otherwise
    """
    # Local endpoints (Ollama, LM Studio) are assumed available
    if api_base:
        return True

    # Cloud models need an API key
    effective_key = api_key or os.environ.get("OPENAI_API_KEY")
    return effective_key is not None and len(effective_key) > 0
