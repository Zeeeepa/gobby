"""Tests for LLM provider base class."""

from typing import Any

import pytest

from gobby.llm.base import LLMProvider


class ConcreteProvider(LLMProvider):
    """Concrete implementation for testing abstract base class."""

    @property
    def provider_name(self) -> str:
        return "test_provider"

    async def generate_summary(
        self, context: dict[str, Any], prompt_template: str | None = None
    ) -> str:
        return "test summary"

    async def synthesize_title(
        self, user_prompt: str, prompt_template: str | None = None
    ) -> str | None:
        return "test title"

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> str:
        return "test text"


class TestLLMProvider:
    """Tests for LLMProvider abstract base class."""

    def test_default_auth_mode_is_subscription(self):
        """Test that default auth_mode returns 'subscription'."""
        provider = ConcreteProvider()
        assert provider.auth_mode == "subscription"

    def test_provider_name(self):
        """Test that provider_name is implemented correctly."""
        provider = ConcreteProvider()
        assert provider.provider_name == "test_provider"

    @pytest.mark.asyncio
    async def test_generate_summary(self):
        """Test generate_summary method."""
        provider = ConcreteProvider()
        result = await provider.generate_summary({})
        assert result == "test summary"

    @pytest.mark.asyncio
    async def test_synthesize_title(self):
        """Test synthesize_title method."""
        provider = ConcreteProvider()
        result = await provider.synthesize_title("test prompt")
        assert result == "test title"

    @pytest.mark.asyncio
    async def test_generate_text(self):
        """Test generate_text method."""
        provider = ConcreteProvider()
        result = await provider.generate_text("test prompt")
        assert result == "test text"
