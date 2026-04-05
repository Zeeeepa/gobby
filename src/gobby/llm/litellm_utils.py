"""
LiteLLM utility functions for model resolution and provider environment setup.

Extracted from litellm_executor.py — these utilities are used by the live
LLM providers (claude.py, gemini.py) for model alias resolution and
provider-specific environment configuration.
"""

import logging
import os
from typing import Literal

logger = logging.getLogger(__name__)

ProviderType = Literal["claude", "gemini", "codex", "openai", "litellm"]
AuthModeType = Literal["api_key", "adc"]

# Shorthand aliases for Claude models — single source of truth for resolution
MODEL_ALIASES: dict[str, str] = {
    "opus": "claude-opus-4-6",
    "sonnet": "claude-sonnet-4-6",
    "haiku": "claude-haiku-4-5",
}


def resolve_model_alias(model: str) -> str:
    """Resolve a shorthand model alias to a full model ID.

    Used at the LiteLLM boundary where full model IDs are required.
    The Claude Agent SDK handles shorthand natively, so this is only
    needed for LiteLLM calls.

    Args:
        model: Model name, either shorthand ("opus") or full ("claude-opus-4-6").

    Returns:
        Full model ID suitable for LiteLLM.
    """
    return MODEL_ALIASES.get(model, model)


def get_litellm_model(
    model: str,
    provider: ProviderType | None = None,
    auth_mode: AuthModeType | None = None,
) -> str:
    """
    Map provider/model/auth_mode to LiteLLM model string format.

    LiteLLM uses prefixes to route to the correct provider:
    - anthropic/model-name -> Anthropic API
    - gemini/model-name -> Google AI Studio (API key)
    - vertex_ai/model-name -> Google Vertex AI (ADC)
    - No prefix -> OpenAI (default)

    Args:
        model: The model name (e.g., "claude-sonnet-4-6", "gemini-2.0-flash")
        provider: The provider type (claude, gemini, codex, openai)
        auth_mode: The authentication mode (api_key, adc)

    Returns:
        LiteLLM-formatted model string with appropriate prefix.

    Examples:
        >>> get_litellm_model("claude-sonnet-4-6", provider="claude")
        "anthropic/claude-sonnet-4-6"
        >>> get_litellm_model("gemini-2.0-flash", provider="gemini", auth_mode="api_key")
        "gemini/gemini-2.0-flash"
        >>> get_litellm_model("gemini-2.0-flash", provider="gemini", auth_mode="adc")
        "vertex_ai/gemini-2.0-flash"
        >>> get_litellm_model("gpt-4o", provider="codex")
        "gpt-4o"
    """
    # Resolve shorthand aliases (opus -> claude-opus-4-6, etc.)
    model = resolve_model_alias(model)

    # If model already has a prefix, assume it's already formatted
    if "/" in model:
        return model

    if provider == "claude":
        return f"anthropic/{model}"
    elif provider == "gemini":
        if auth_mode == "adc":
            # ADC uses Vertex AI endpoint
            return f"vertex_ai/{model}"
        # API key uses Gemini API endpoint
        return f"gemini/{model}"
    elif provider in ("codex", "openai"):
        # OpenAI models don't need a prefix
        return model
    else:
        # Default: return as-is (OpenAI-compatible or already prefixed)
        return model


def setup_provider_env(
    provider: ProviderType | None = None,
    auth_mode: AuthModeType | None = None,
) -> None:
    """
    Set up environment variables needed for specific provider/auth_mode combinations.

    For Gemini ADC mode via Vertex AI, this ensures VERTEXAI_PROJECT and
    VERTEXAI_LOCATION are set from common Google Cloud environment variables.

    Args:
        provider: The provider type
        auth_mode: The authentication mode
    """
    if provider == "gemini" and auth_mode == "adc":
        # Vertex AI needs project and location
        # Check if already set, otherwise try common GCP env vars
        if "VERTEXAI_PROJECT" not in os.environ:
            project = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get("GCLOUD_PROJECT")
            if project:
                os.environ["VERTEXAI_PROJECT"] = project
                logger.debug(f"Set VERTEXAI_PROJECT from GCP env: {project}")

        if "VERTEXAI_LOCATION" not in os.environ:
            location = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")
            os.environ["VERTEXAI_LOCATION"] = location
            logger.debug(f"Set VERTEXAI_LOCATION: {location}")
