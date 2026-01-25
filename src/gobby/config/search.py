"""Search configuration for Gobby daemon.

Provides configuration for the unified search layer with embedding
support and TF-IDF fallback.

Example usage in config.yaml:
    search:
      mode: auto  # tfidf, embedding, auto, hybrid
      embedding_model: text-embedding-3-small
      tfidf_weight: 0.4
      embedding_weight: 0.6
      notify_on_fallback: true

For Ollama (local embeddings):
    search:
      mode: auto
      embedding_model: openai/nomic-embed-text
      embedding_api_base: http://localhost:11434/v1
"""

from pydantic import BaseModel, Field

from gobby.search.models import SearchMode


class SearchConfig(BaseModel):
    """Configuration for unified search with fallback.

    This config controls how UnifiedSearcher behaves, including:
    - Which search mode to use (tfidf, embedding, auto, hybrid)
    - Which embedding model to use (LiteLLM format)
    - Weights for hybrid mode
    - Whether to notify on fallback

    Supported modes:
    - tfidf: TF-IDF only (always works, no API needed)
    - embedding: Embedding-based search only (fails if unavailable)
    - auto: Try embedding, fallback to TF-IDF if unavailable
    - hybrid: Combine both with weighted scores

    LiteLLM model format examples:
    - OpenAI: text-embedding-3-small (needs OPENAI_API_KEY)
    - Ollama: openai/nomic-embed-text (with embedding_api_base)
    - Azure: azure/azure-embedding-model
    - Vertex AI: vertex_ai/text-embedding-004
    - Gemini: gemini/text-embedding-004 (needs GEMINI_API_KEY)
    - Mistral: mistral/mistral-embed (needs MISTRAL_API_KEY)
    """

    mode: str = Field(
        default="auto",
        description="Search mode: tfidf, embedding, auto, hybrid",
    )
    embedding_model: str = Field(
        default="text-embedding-3-small",
        description="LiteLLM model string (e.g., text-embedding-3-small, openai/nomic-embed-text)",
    )
    embedding_api_base: str | None = Field(
        default=None,
        description="API base URL for Ollama/custom endpoints (e.g., http://localhost:11434/v1)",
    )
    embedding_api_key: str | None = Field(
        default=None,
        description="API key for embedding provider (uses env var if not set)",
    )
    tfidf_weight: float = Field(
        default=0.4,
        ge=0.0,
        le=1.0,
        description="Weight for TF-IDF scores in hybrid mode",
    )
    embedding_weight: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Weight for embedding scores in hybrid mode",
    )
    notify_on_fallback: bool = Field(
        default=True,
        description="Log warning when falling back to TF-IDF",
    )

    def get_normalized_weights(self) -> tuple[float, float]:
        """Get normalized weights that sum to 1.0.

        Returns:
            Tuple of (tfidf_weight, embedding_weight) normalized to sum to 1.0
        """
        total = self.tfidf_weight + self.embedding_weight
        if total == 0:
            # Default to equal weights if both are 0
            return (0.5, 0.5)
        return (self.tfidf_weight / total, self.embedding_weight / total)

    def get_mode_enum(self) -> SearchMode:
        """Get the SearchMode enum instance for the configured mode.

        Returns:
            SearchMode enum corresponding to the mode string value

        Raises:
            ValueError: If the configured mode is not a valid SearchMode
        """
        try:
            return SearchMode(self.mode)
        except ValueError as e:
            valid_modes = [m.value for m in SearchMode]
            raise ValueError(
                f"Invalid search mode '{self.mode}'. Valid modes are: {', '.join(valid_modes)}"
            ) from e
