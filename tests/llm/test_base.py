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

    async def describe_image(
        self,
        image_path: str,
        context: str | None = None,
    ) -> str:
        return f"Description of image at {image_path}"


class IncompleteProviderMissingDescribeImage(LLMProvider):
    """Provider missing describe_image - should fail to instantiate."""

    @property
    def provider_name(self) -> str:
        return "incomplete_provider"

    async def generate_summary(
        self, context: dict[str, Any], prompt_template: str | None = None
    ) -> str:
        return "summary"

    async def synthesize_title(
        self, user_prompt: str, prompt_template: str | None = None
    ) -> str | None:
        return "title"

    async def generate_text(
        self,
        prompt: str,
        system_prompt: str | None = None,
        model: str | None = None,
    ) -> str:
        return "text"


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


class TestDescribeImageAbstractMethod:
    """TDD tests for describe_image abstract method on LLMProvider."""

    def test_describe_image_is_abstract_method(self):
        """Test that describe_image is defined as an abstract method on LLMProvider."""
        # Verify that describe_image exists on the ABC
        assert hasattr(LLMProvider, "describe_image"), (
            "LLMProvider should have describe_image method"
        )
        # Check it's marked as abstract
        assert getattr(LLMProvider.describe_image, "__isabstractmethod__", False), (
            "describe_image should be an abstract method"
        )

    def test_cannot_instantiate_without_describe_image(self):
        """Test that LLMProvider subclass must implement describe_image."""
        # IncompleteProviderMissingDescribeImage doesn't implement describe_image
        # Should raise TypeError when trying to instantiate
        with pytest.raises(TypeError, match="describe_image"):
            IncompleteProviderMissingDescribeImage()

    @pytest.mark.asyncio
    async def test_describe_image_with_path_only(self):
        """Test describe_image can be called with just image_path."""
        provider = ConcreteProvider()
        result = await provider.describe_image("/path/to/image.png")
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_describe_image_with_context(self):
        """Test describe_image can be called with optional context."""
        provider = ConcreteProvider()
        result = await provider.describe_image(
            "/path/to/image.png", context="This is a screenshot of the application settings page"
        )
        assert isinstance(result, str)
        assert len(result) > 0

    @pytest.mark.asyncio
    async def test_describe_image_returns_string(self):
        """Test describe_image returns a string suitable for memory storage."""
        provider = ConcreteProvider()
        result = await provider.describe_image("/test/image.jpg")
        # Should return a string (the description)
        assert isinstance(result, str)

    def test_describe_image_signature(self):
        """Test describe_image has correct method signature."""
        import inspect

        # Get the signature of describe_image from LLMProvider
        sig = inspect.signature(LLMProvider.describe_image)
        params = list(sig.parameters.keys())

        # Should have self, image_path, and context parameters
        assert "self" in params, "describe_image should have self parameter"
        assert "image_path" in params, "describe_image should have image_path parameter"
        assert "context" in params, "describe_image should have context parameter"

        # context should have a default of None
        context_param = sig.parameters["context"]
        assert context_param.default is None, "context should default to None"
