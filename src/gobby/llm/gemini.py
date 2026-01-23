"""
Gemini implementation of LLMProvider using LiteLLM.

Routes all calls through LiteLLM for unified cost tracking:
- api_key mode: Uses gemini/model-name prefix
- adc mode: Uses vertex_ai/model-name prefix (requires VERTEXAI_PROJECT, VERTEXAI_LOCATION)

This provider replaces direct google-generativeai SDK usage with LiteLLM routing.
"""

import json
import logging
from typing import Any, Literal

from gobby.config.app import DaemonConfig
from gobby.llm.base import AuthMode, LLMProvider
from gobby.llm.litellm_executor import get_litellm_model, setup_provider_env

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """
    Gemini implementation of LLMProvider using LiteLLM for unified cost tracking.

    All calls are routed through LiteLLM:
    - api_key mode: Uses gemini/model-name prefix (requires GEMINI_API_KEY)
    - adc mode: Uses vertex_ai/model-name prefix (requires VERTEXAI_PROJECT, VERTEXAI_LOCATION)
    """

    def __init__(
        self,
        config: DaemonConfig,
        auth_mode: Literal["api_key", "adc"] | None = None,
    ):
        """
        Initialize GeminiProvider with LiteLLM routing.

        Args:
            config: Client configuration.
            auth_mode: Override auth mode. If None, reads from config.llm_providers.gemini.auth_mode
                      or falls back to "api_key".
        """
        self.config = config
        self.logger = logger
        self._litellm = None

        # Determine auth mode from config or parameter
        self._auth_mode: AuthMode = "api_key"  # Default
        if auth_mode:
            self._auth_mode = auth_mode
        elif config.llm_providers and config.llm_providers.gemini:
            self._auth_mode = config.llm_providers.gemini.auth_mode

        # Set up environment for provider/auth_mode
        setup_provider_env("gemini", self._auth_mode)  # type: ignore[arg-type]

        try:
            import litellm

            self._litellm = litellm
            self.logger.debug(
                f"GeminiProvider initialized with LiteLLM (auth_mode={self._auth_mode})"
            )

        except ImportError:
            self.logger.error(
                "litellm package not found. Please install with `pip install litellm`."
            )

    def _get_model(self, base_model: str) -> str:
        """Get the LiteLLM-formatted model name with appropriate prefix."""
        return get_litellm_model(base_model, "gemini", self._auth_mode)  # type: ignore[arg-type]

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "gemini"

    @property
    def auth_mode(self) -> AuthMode:
        """Return the authentication mode for this provider."""
        return self._auth_mode

    async def generate_summary(
        self, context: dict[str, Any], prompt_template: str | None = None
    ) -> str:
        """
        Generate session summary using Gemini via LiteLLM.
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
            model_name = self.config.session_summary.model or "gemini-1.5-pro"
            litellm_model = self._get_model(model_name)

            response = await self._litellm.acompletion(
                model=litellm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a session summary generator. Create comprehensive, actionable summaries.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4000,
                timeout=120,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            self.logger.error(f"Failed to generate summary with Gemini via LiteLLM: {e}")
            return f"Session summary generation failed: {e}"

    async def synthesize_title(
        self, user_prompt: str, prompt_template: str | None = None
    ) -> str | None:
        """
        Synthesize session title using Gemini via LiteLLM.
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
            model_name = self.config.title_synthesis.model or "gemini-1.5-flash"
            litellm_model = self._get_model(model_name)

            response = await self._litellm.acompletion(
                model=litellm_model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a session title generator. Create concise, descriptive titles.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=50,
                timeout=30,
            )
            return (response.choices[0].message.content or "").strip()
        except Exception as e:
            self.logger.error(f"Failed to synthesize title with Gemini via LiteLLM: {e}")
            return None

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> str:
        """
        Generate text using Gemini via LiteLLM.
        """
        if not self._litellm:
            return "Generation unavailable (LiteLLM not initialized)"

        model_name = model or "gemini-1.5-flash"
        litellm_model = self._get_model(model_name)

        try:
            response = await self._litellm.acompletion(
                model=litellm_model,
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt or "You are a helpful assistant.",
                    },
                    {"role": "user", "content": prompt},
                ],
                max_tokens=4000,
                timeout=120,
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            self.logger.error(f"Failed to generate text with Gemini via LiteLLM: {e}")
            return f"Generation failed: {e}"

    async def describe_image(
        self,
        image_path: str,
        context: str | None = None,
    ) -> str:
        """
        Generate a text description of an image using Gemini's vision via LiteLLM.

        Args:
            image_path: Path to the image file
            context: Optional context to guide the description

        Returns:
            Text description of the image
        """
        import base64
        import mimetypes
        from pathlib import Path

        if not self._litellm:
            return "Image description unavailable (LiteLLM not initialized)"

        path = Path(image_path)
        if not path.exists():
            return f"Image not found: {image_path}"

        try:
            # Read and encode image
            image_data = path.read_bytes()
            image_base64 = base64.standard_b64encode(image_data).decode("utf-8")

            # Determine media type
            mime_type, _ = mimetypes.guess_type(str(path))
            if mime_type not in [
                "image/jpeg",
                "image/png",
                "image/webp",
                "image/heic",
                "image/heif",
            ]:
                mime_type = "image/png"

            # Build prompt
            prompt = (
                "Please describe this image in detail, focusing on key visual elements, "
                "any text visible, and the overall context or meaning."
            )
            if context:
                prompt = f"{context}\n\n{prompt}"

            # Use gemini-1.5-flash via LiteLLM for efficient vision tasks
            litellm_model = self._get_model("gemini-1.5-flash")

            response = await self._litellm.acompletion(
                model=litellm_model,
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
                timeout=60,
            )

            return response.choices[0].message.content or "No description generated"

        except Exception as e:
            self.logger.error(f"Failed to describe image with Gemini via LiteLLM: {e}")
            return f"Image description failed: {e}"
