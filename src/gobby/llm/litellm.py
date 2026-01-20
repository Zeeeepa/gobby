"""
LiteLLM implementation of LLMProvider.

LiteLLM provides a unified interface to many LLM providers (OpenAI, Anthropic,
Mistral, Cohere, etc.) through their APIs using BYOK (Bring Your Own Key).

This provider is useful when users want to use their own API keys for
multiple different providers without needing separate provider implementations.
"""

import json
import logging
from typing import Any

from gobby.config.app import DaemonConfig
from gobby.llm.base import AuthMode, LLMProvider

logger = logging.getLogger(__name__)


class LiteLLMProvider(LLMProvider):
    """
    LiteLLM implementation of LLMProvider.

    Uses API key-based authentication (BYOK) for multiple providers.
    API keys are read from:
    1. llm_providers.api_keys in config (e.g., OPENAI_API_KEY, MISTRAL_API_KEY)
    2. Environment variables as fallback

    Example config:
        llm_providers:
          litellm:
            models: gpt-4o-mini,mistral-large
            auth_mode: api_key
          api_keys:
            OPENAI_API_KEY: sk-...
            MISTRAL_API_KEY: ...
    """

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "litellm"

    @property
    def auth_mode(self) -> AuthMode:
        """LiteLLM uses API key authentication."""
        return "api_key"

    def __init__(self, config: DaemonConfig):
        """
        Initialize LiteLLMProvider.

        Args:
            config: Client configuration with optional api_keys in llm_providers.
        """
        self.config = config
        self.logger = logger
        self._litellm = None
        self._api_keys: dict[str, str] = {}

        # Load API keys from config
        if config.llm_providers and config.llm_providers.api_keys:
            self._api_keys = config.llm_providers.api_keys.copy()

        try:
            import litellm

            self._litellm = litellm

            # Set API keys in litellm's environment
            # LiteLLM reads from os.environ, so we set them there
            import os

            for key, value in self._api_keys.items():
                if value and key not in os.environ:
                    os.environ[key] = value
                    self.logger.debug(f"Set {key} from config")

            self.logger.debug("LiteLLM provider initialized")

        except ImportError:
            self.logger.error(
                "litellm package not found. Please install with `pip install litellm`."
            )
        except Exception as e:
            self.logger.error(f"Failed to initialize LiteLLM: {e}")

    def _get_model(self, task: str) -> str:
        """
        Get the model to use for a specific task.

        Args:
            task: Task type ("summary" or "title")

        Returns:
            Model name string
        """
        if task == "summary":
            if self.config.session_summary:
                return self.config.session_summary.model or "gpt-4o-mini"
            return "gpt-4o-mini"
        elif task == "title":
            if self.config.title_synthesis:
                return self.config.title_synthesis.model or "gpt-4o-mini"
            return "gpt-4o-mini"
        else:
            return "gpt-4o-mini"

    async def generate_summary(
        self, context: dict[str, Any], prompt_template: str | None = None
    ) -> str:
        """
        Generate session summary using LiteLLM.
        """
        if not self._litellm:
            return "Session summary unavailable (LiteLLM not initialized)"

        # Build formatted context for prompt template
        formatted_context = {
            "transcript_summary": context.get("transcript_summary", ""),
            "last_messages": json.dumps(context.get("last_messages", []), indent=2),
            "git_status": context.get("git_status", ""),
            "file_changes": context.get("file_changes", ""),
            **{
                k: v
                for k, v in context.items()
                if k not in ["transcript_summary", "last_messages", "git_status", "file_changes"]
            },
        }

        # Build prompt - prompt_template is required
        if not prompt_template:
            raise ValueError(
                "prompt_template is required for generate_summary. "
                "Configure 'session_summary.prompt' in ~/.gobby/config.yaml"
            )
        prompt = prompt_template.format(**formatted_context)

        try:
            # Use LiteLLM's async completion
            response = await self._litellm.acompletion(
                model=self._get_model("summary"),
                messages=[
                    {
                        "role": "system",
                        "content": "You are a session summary generator. Create comprehensive, actionable summaries.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4000,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            self.logger.error(f"Failed to generate summary with LiteLLM: {e}")
            return f"Session summary generation failed: {e}"

    async def synthesize_title(
        self, user_prompt: str, prompt_template: str | None = None
    ) -> str | None:
        """
        Synthesize session title using LiteLLM.
        """
        if not self._litellm:
            return None

        # Build prompt - prompt_template is required
        if not prompt_template:
            raise ValueError(
                "prompt_template is required for synthesize_title. "
                "Configure 'title_synthesis.prompt' in ~/.gobby/config.yaml"
            )
        prompt = prompt_template.format(user_prompt=user_prompt)

        try:
            response = await self._litellm.acompletion(
                model=self._get_model("title"),
                messages=[
                    {
                        "role": "system",
                        "content": "You are a session title generator. Create concise, descriptive titles.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=50,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            self.logger.error(f"Failed to synthesize title with LiteLLM: {e}")
            return None

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> str:
        """
        Generate text using LiteLLM.
        """
        if not self._litellm:
            return "Generation unavailable (LiteLLM not initialized)"

        try:
            response = await self._litellm.acompletion(
                model=model or "gpt-4o-mini",
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt or "You are a helpful assistant.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4000,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            self.logger.error(f"Failed to generate text with LiteLLM: {e}")
            return f"Generation failed: {e}"

    async def describe_image(
        self,
        image_path: str,
        context: str | None = None,
    ) -> str:
        """
        Generate a text description of an image using LiteLLM's vision support.

        Args:
            image_path: Path to the image file to describe
            context: Optional context to guide the description

        Returns:
            Text description of the image
        """
        import base64
        import mimetypes
        from pathlib import Path

        if not self._litellm:
            return "Image description unavailable (LiteLLM not initialized)"

        # Validate image exists
        path = Path(image_path)
        if not path.exists():
            return f"Image not found: {image_path}"

        # Read and encode image
        try:
            image_data = path.read_bytes()
            image_base64 = base64.standard_b64encode(image_data).decode("utf-8")
        except Exception as e:
            self.logger.error(f"Failed to read image {image_path}: {e}")
            return f"Failed to read image: {e}"

        # Determine media type
        mime_type, _ = mimetypes.guess_type(str(path))
        if mime_type not in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
            mime_type = "image/png"

        # Build prompt
        prompt = "Please describe this image in detail, focusing on the key visual elements and any text visible."
        if context:
            prompt = f"{context}\n\n{prompt}"

        try:
            # Use LiteLLM's vision support (works with gpt-4o, claude-3, etc.)
            response = await self._litellm.acompletion(
                model="gpt-4o-mini",  # Default to a vision-capable model
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:{mime_type};base64,{image_base64}"},
                            },
                        ],
                    }
                ],
                max_tokens=1000,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            self.logger.error(f"Failed to describe image with LiteLLM: {e}")
            return f"Image description failed: {e}"
