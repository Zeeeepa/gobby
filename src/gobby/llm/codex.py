"""
Codex (OpenAI) implementation of LLMProvider.

Codex CLI supports both subscription-based (ChatGPT) and API key authentication.
After OAuth login, the CLI stores an OpenAI API key in ~/.codex/auth.json,
which can be used with the standard OpenAI Python SDK.

Auth priority:
1. ~/.codex/auth.json (subscription mode)
2. OPENAI_API_KEY environment variable (BYOK mode)
"""

import json
import logging
import os
from pathlib import Path
from typing import Any, Literal, cast

from gobby.config.app import DaemonConfig
from gobby.llm.base import AuthMode, LLMProvider

logger = logging.getLogger(__name__)


class CodexProvider(LLMProvider):
    """
    Codex (OpenAI) implementation of LLMProvider.

    Supports two authentication modes:
    - subscription: Read API key from ~/.codex/auth.json (after `codex login`)
    - api_key: Use OPENAI_API_KEY environment variable (BYOK)
    """

    @property
    def provider_name(self) -> str:
        """Return provider name."""
        return "codex"

    @property
    def auth_mode(self) -> AuthMode:
        """Return the authentication mode for this provider."""
        return self._auth_mode

    def __init__(
        self,
        config: DaemonConfig,
        auth_mode: Literal["subscription", "api_key"] | None = None,
    ):
        """
        Initialize CodexProvider.

        Args:
            config: Client configuration.
            auth_mode: Override auth mode. If None, reads from config.llm_providers.codex.auth_mode
                      or auto-detects based on available credentials.
        """
        self.config = config
        self.logger = logger
        self._client = None

        # Determine auth mode from config or parameter
        self._auth_mode: AuthMode = "subscription"  # Default
        if auth_mode:
            self._auth_mode = auth_mode
        elif config.llm_providers and config.llm_providers.codex:
            self._auth_mode = config.llm_providers.codex.auth_mode

        # Get API key based on auth mode
        api_key = self._get_api_key()

        if not api_key:
            self.logger.warning(
                "No Codex API key found. "
                "Run 'codex login' for subscription mode or set OPENAI_API_KEY for BYOK."
            )
            return

        try:
            from openai import AsyncOpenAI

            self._client = AsyncOpenAI(api_key=api_key)
            self.logger.debug(f"Codex provider initialized (auth_mode: {self._auth_mode})")

        except ImportError:
            self.logger.error("OpenAI package not found. Please install with `pip install openai`.")
        except Exception as e:
            self.logger.error(f"Failed to initialize Codex client: {e}")

    def _get_api_key(self) -> str | None:
        """
        Get API key based on auth mode.

        For subscription mode, reads from ~/.codex/auth.json.
        For api_key mode, reads from OPENAI_API_KEY environment variable.

        Returns:
            API key string or None if not found
        """
        if self._auth_mode == "subscription":
            # Try to read from Codex auth.json
            auth_path = Path.home() / ".codex" / "auth.json"
            if auth_path.exists():
                try:
                    with open(auth_path) as f:
                        auth_data = json.load(f)
                    api_key = auth_data.get("OPENAI_API_KEY")
                    if api_key:
                        self.logger.debug("Loaded API key from ~/.codex/auth.json")
                        return cast(str | None, api_key)
                except Exception as e:
                    self.logger.warning(f"Failed to read ~/.codex/auth.json: {e}")

            # Subscription mode but no auth.json - suggest login
            self.logger.warning(
                "Codex subscription mode but ~/.codex/auth.json not found. "
                "Run 'codex login' to authenticate."
            )
            return None
        else:
            # API key mode - read from environment
            env_api_key: str | None = os.environ.get("OPENAI_API_KEY")
            if env_api_key:
                self.logger.debug("Using OPENAI_API_KEY from environment")
            return env_api_key

    def _get_model(self, task: str) -> str:
        """
        Get the model to use for a specific task.

        Args:
            task: Task type ("summary" or "title")

        Returns:
            Model name string
        """
        if task == "summary":
            return self.config.session_summary.model or "gpt-4o"
        elif task == "title":
            return self.config.title_synthesis.model or "gpt-4o-mini"
        else:
            return "gpt-4o"

    async def generate_summary(
        self, context: dict[str, Any], prompt_template: str | None = None
    ) -> str:
        """
        Generate session summary using Codex/OpenAI.
        """
        if not self._client:
            return "Session summary unavailable (Codex client not initialized)"

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
            response = await self._client.chat.completions.create(
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
            self.logger.error(f"Failed to generate summary with Codex: {e}")
            return f"Session summary generation failed: {e}"

    async def synthesize_title(
        self, user_prompt: str, prompt_template: str | None = None
    ) -> str | None:
        """
        Synthesize session title using Codex/OpenAI.
        """
        if not self._client:
            return None

        # Build prompt - prompt_template is required
        if not prompt_template:
            raise ValueError(
                "prompt_template is required for synthesize_title. "
                "Configure 'title_synthesis.prompt' in ~/.gobby/config.yaml"
            )
        prompt = prompt_template.format(user_prompt=user_prompt)

        try:
            response = await self._client.chat.completions.create(
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
            self.logger.error(f"Failed to synthesize title with Codex: {e}")
            return None

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> str:
        """
        Generate text using Codex/OpenAI.
        """
        if not self._client:
            return "Generation unavailable (Codex client not initialized)"

        try:
            response = await self._client.chat.completions.create(
                model=model or "gpt-4o",
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
            self.logger.error(f"Failed to generate text with Codex: {e}")
            return f"Generation failed: {e}"

    async def describe_image(
        self,
        image_path: str,
        context: str | None = None,
    ) -> str:
        """
        Generate a text description of an image using OpenAI's vision capabilities.

        Uses GPT-4o for vision tasks.

        Args:
            image_path: Path to the image file
            context: Optional context to guide the description

        Returns:
            Text description of the image
        """
        import base64
        import mimetypes

        if not self._client:
            return "Image description unavailable (Codex client not initialized)"

        path = Path(image_path)
        if not path.exists():
            return f"Image not found: {image_path}"

        try:
            # Read and encode image
            image_data = path.read_bytes()
            image_base64 = base64.standard_b64encode(image_data).decode("utf-8")

            # Determine MIME type
            mime_type, _ = mimetypes.guess_type(str(path))
            if mime_type not in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
                mime_type = "image/png"  # Default to PNG

            # Build prompt
            prompt = (
                "Please describe this image in detail, focusing on key visual elements, "
                "any text visible, and the overall context or meaning."
            )
            if context:
                prompt = f"{context}\n\n{prompt}"

            # Use GPT-4o for vision
            response = await self._client.chat.completions.create(
                model="gpt-4o",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:{mime_type};base64,{image_base64}",
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
                max_tokens=1024,
            )

            return response.choices[0].message.content or "No description generated"

        except Exception as e:
            self.logger.error(f"Failed to describe image with Codex: {e}")
            return f"Image description failed: {e}"
