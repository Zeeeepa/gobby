import pytest
from pydantic import ValidationError

from gobby.config.skills import HubConfig

pytestmark = pytest.mark.unit

class TestHubConfig:
    def test_hub_config_valid_clawdhub(self) -> None:
        """Test that 'clawdhub' is a valid type."""
        config = HubConfig(type="clawdhub")
        assert config.type == "clawdhub"

    def test_hub_config_valid_skillhub(self) -> None:
        """Test that 'skillhub' is a valid type."""
        config = HubConfig(type="skillhub")
        assert config.type == "skillhub"

    def test_hub_config_valid_github_collection(self) -> None:
        """Test that 'github-collection' is a valid type."""
        config = HubConfig(type="github-collection")
        assert config.type == "github-collection"

    def test_hub_config_invalid_type(self) -> None:
        """Test that invalid types raise ValidationError."""
        with pytest.raises(ValidationError) as excinfo:
            HubConfig(type="invalid-type")
        # Pydantic's error message for Literal validation failure
        assert "Input should be 'clawdhub', 'skillhub' or 'github-collection'" in str(excinfo.value)

    def test_hub_config_optional_fields(self) -> None:
        """Test that optional fields are correctly set."""
        config = HubConfig(
            type="skillhub",
            base_url="https://example.com",
            repo="user/repo",
            branch="main",
            auth_key_name="MY_KEY",
        )
        assert config.base_url == "https://example.com"
        assert config.repo == "user/repo"
        assert config.branch == "main"
        assert config.auth_key_name == "MY_KEY"

    def test_hub_config_defaults(self) -> None:
        """Test that optional fields default to None."""
        config = HubConfig(type="skillhub")
        assert config.base_url is None
        assert config.repo is None
        assert config.branch is None
        assert config.auth_key_name is None

    def test_hub_config_required_type(self) -> None:
        """Test that 'type' is required."""
        with pytest.raises(ValidationError) as excinfo:
            HubConfig()
        assert "Field required" in str(excinfo.value)
