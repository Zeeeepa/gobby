"""Tests for HubManager."""

import pytest

from gobby.config.skills import HubConfig
from gobby.skills.hubs.base import HubProvider, HubSkillDetails, HubSkillInfo
from gobby.skills.hubs.manager import HubManager

pytestmark = pytest.mark.unit


class MockProvider(HubProvider):
    """Mock provider for testing."""

    @property
    def provider_type(self) -> str:
        return "mock"

    async def discover(self) -> dict:
        return {"api_base": self.base_url}

    async def search(self, query: str, limit: int = 20) -> list[HubSkillInfo]:
        return []

    async def list_skills(self, limit: int = 50, offset: int = 0) -> list[HubSkillInfo]:
        return []

    async def get_skill_details(self, slug: str) -> HubSkillDetails | None:
        return None

    async def download_skill(
        self, slug: str, version: str | None = None, target_dir: str | None = None
    ) -> dict:
        return {"success": True}


class TestHubManager:
    """Tests for HubManager."""

    def test_init_with_empty_configs(self) -> None:
        """Test HubManager with no hub configs."""
        manager = HubManager(configs={})
        assert manager.list_hubs() == []

    def test_init_with_configs(self) -> None:
        """Test HubManager with hub configs."""
        configs = {
            "clawdhub": HubConfig(type="clawdhub", base_url="https://clawdhub.com"),
            "skillhub": HubConfig(type="skillhub", base_url="https://skillhub.dev"),
        }
        manager = HubManager(configs=configs)
        hubs = manager.list_hubs()
        assert len(hubs) == 2
        assert "clawdhub" in hubs
        assert "skillhub" in hubs

    def test_init_with_api_keys(self) -> None:
        """Test HubManager with API keys."""
        configs = {
            "skillhub": HubConfig(
                type="skillhub",
                base_url="https://skillhub.dev",
                auth_key_name="SKILLHUB_KEY",
            ),
        }
        api_keys = {"SKILLHUB_KEY": "secret123"}
        manager = HubManager(configs=configs, api_keys=api_keys)
        # API key should be accessible when creating providers
        assert manager._api_keys.get("SKILLHUB_KEY") == "secret123"

    def test_list_hubs_returns_hub_names(self) -> None:
        """Test list_hubs returns configured hub names."""
        configs = {
            "hub-a": HubConfig(type="clawdhub", base_url="https://a.com"),
            "hub-b": HubConfig(type="skillhub", base_url="https://b.com"),
            "hub-c": HubConfig(type="github-collection", repo="user/repo"),
        }
        manager = HubManager(configs=configs)
        hubs = manager.list_hubs()
        assert sorted(hubs) == ["hub-a", "hub-b", "hub-c"]

    def test_get_provider_unknown_hub_raises_keyerror(self) -> None:
        """Test get_provider raises KeyError for unknown hub."""
        manager = HubManager(configs={})
        with pytest.raises(KeyError, match="Unknown hub"):
            manager.get_provider("nonexistent")

    def test_get_provider_caches_instance(self) -> None:
        """Test get_provider caches and returns same instance."""
        configs = {
            "test-hub": HubConfig(type="clawdhub", base_url="https://test.com"),
        }
        manager = HubManager(configs=configs)

        # Register a mock provider factory for testing
        manager.register_provider_factory("clawdhub", MockProvider)

        provider1 = manager.get_provider("test-hub")
        provider2 = manager.get_provider("test-hub")
        assert provider1 is provider2

    def test_get_provider_creates_correct_type(self) -> None:
        """Test get_provider creates provider with correct config."""
        configs = {
            "my-hub": HubConfig(type="clawdhub", base_url="https://myhub.com"),
        }
        manager = HubManager(configs=configs)
        manager.register_provider_factory("clawdhub", MockProvider)

        provider = manager.get_provider("my-hub")
        assert provider.hub_name == "my-hub"
        assert provider.base_url == "https://myhub.com"

    def test_get_provider_with_auth_token(self) -> None:
        """Test get_provider passes auth token from api_keys."""
        configs = {
            "authed-hub": HubConfig(
                type="skillhub",
                base_url="https://hub.com",
                auth_key_name="MY_SECRET",
            ),
        }
        api_keys = {"MY_SECRET": "token123"}
        manager = HubManager(configs=configs, api_keys=api_keys)
        manager.register_provider_factory("skillhub", MockProvider)

        provider = manager.get_provider("authed-hub")
        assert provider.auth_token == "token123"

    def test_get_provider_missing_auth_key(self) -> None:
        """Test get_provider with missing auth key uses None."""
        configs = {
            "hub": HubConfig(
                type="skillhub",
                base_url="https://hub.com",
                auth_key_name="MISSING_KEY",
            ),
        }
        manager = HubManager(configs=configs, api_keys={})
        manager.register_provider_factory("skillhub", MockProvider)

        provider = manager.get_provider("hub")
        assert provider.auth_token is None

    def test_register_provider_factory(self) -> None:
        """Test registering a custom provider factory."""
        manager = HubManager(configs={})

        class CustomProvider(MockProvider):
            @property
            def provider_type(self) -> str:
                return "custom"

        manager.register_provider_factory("custom-type", CustomProvider)
        assert "custom-type" in manager._factories

    def test_has_hub(self) -> None:
        """Test has_hub checks if hub exists."""
        configs = {"existing": HubConfig(type="clawdhub", base_url="https://x.com")}
        manager = HubManager(configs=configs)

        assert manager.has_hub("existing") is True
        assert manager.has_hub("nonexistent") is False

    def test_get_config(self) -> None:
        """Test get_config returns hub configuration."""
        config = HubConfig(type="clawdhub", base_url="https://x.com")
        manager = HubManager(configs={"my-hub": config})

        retrieved = manager.get_config("my-hub")
        assert retrieved is config

    def test_get_config_unknown_raises_keyerror(self) -> None:
        """Test get_config raises KeyError for unknown hub."""
        manager = HubManager(configs={})
        with pytest.raises(KeyError):
            manager.get_config("unknown")
