"""
LLM providers configuration module.

Contains LLM-related Pydantic config models:
- LLMProviderConfig: Single provider config (models, auth_mode)
- LLMProvidersConfig: Multi-provider config (claude, codex, gemini, litellm)

Extracted from app.py using Strangler Fig pattern for code decomposition.
"""

from typing import Literal

from pydantic import BaseModel, Field

__all__ = ["LLMProviderConfig", "LLMProvidersConfig"]


class LLMProviderConfig(BaseModel):
    """Configuration for a single LLM provider."""

    models: str = Field(
        description="Comma-separated list of available models for this provider",
    )
    auth_mode: Literal["subscription", "api_key", "adc"] = Field(
        default="subscription",
        description="Authentication mode: 'subscription' (CLI-based), 'api_key' (BYOK), 'adc' (Google ADC)",
    )

    def get_models_list(self) -> list[str]:
        """Return models as a list."""
        return [m.strip() for m in self.models.split(",") if m.strip()]


class LLMProvidersConfig(BaseModel):
    """
    Configuration for multiple LLM providers.

    Example YAML:
    ```yaml
    llm_providers:
      json_strict: true  # Strict JSON validation for LLM responses (default)
      claude:
        models: claude-haiku-4-5,claude-sonnet-4-5,claude-opus-4-5
      codex:
        models: gpt-4o-mini,gpt-5-mini,gpt-5
        auth_mode: subscription
      gemini:
        models: gemini-2.0-flash,gemini-2.5-pro
        auth_mode: adc
      litellm:
        models: gpt-4o-mini,mistral-large
        auth_mode: api_key
      api_keys:
        OPENAI_API_KEY: sk-...
        MISTRAL_API_KEY: ...
    ```
    """

    json_strict: bool = Field(
        default=True,
        description="Strict JSON validation for LLM responses. "
        "When True (default), type mismatches raise errors. "
        "When False, allows coercion (e.g., '5' -> 5). "
        "Can be overridden per-workflow via llm_json_strict variable.",
    )
    claude: LLMProviderConfig | None = Field(
        default=None,
        description="Claude provider configuration",
    )
    codex: LLMProviderConfig | None = Field(
        default=None,
        description="Codex (OpenAI) provider configuration",
    )
    gemini: LLMProviderConfig | None = Field(
        default=None,
        description="Gemini provider configuration",
    )
    litellm: LLMProviderConfig | None = Field(
        default=None,
        description="LiteLLM provider configuration",
    )
    api_keys: dict[str, str] = Field(
        default_factory=dict,
        description="API keys for BYOK providers (key name -> key value)",
    )

    def get_enabled_providers(self) -> list[str]:
        """Return list of enabled provider names."""
        providers = []
        if self.claude:
            providers.append("claude")
        if self.codex:
            providers.append("codex")
        if self.gemini:
            providers.append("gemini")
        if self.litellm:
            providers.append("litellm")
        return providers
