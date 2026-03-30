"""Tests for Qdrant installer and unified Docker Compose template."""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# docker-compose.services.yml tests
# ---------------------------------------------------------------------------


class TestDockerComposeServices:
    """Tests for the unified docker-compose.services.yml file."""

    def test_compose_file_exists(self) -> None:
        """docker-compose.services.yml exists in data directory."""
        from gobby.cli.installers.qdrant import _COMPOSE_SRC

        assert _COMPOSE_SRC.exists(), f"Expected {_COMPOSE_SRC} to exist"

    def test_compose_file_is_valid_yaml(self) -> None:
        """docker-compose.services.yml is valid YAML."""
        from gobby.cli.installers.qdrant import _COMPOSE_SRC

        data = yaml.safe_load(_COMPOSE_SRC.read_text())
        assert isinstance(data, dict)

    def test_compose_has_qdrant_service(self) -> None:
        """Compose file defines a qdrant service."""
        from gobby.cli.installers.qdrant import _COMPOSE_SRC

        data = yaml.safe_load(_COMPOSE_SRC.read_text())
        assert "qdrant" in data["services"]

    def test_compose_has_neo4j_service(self) -> None:
        """Compose file defines a neo4j service."""
        from gobby.cli.installers.qdrant import _COMPOSE_SRC

        data = yaml.safe_load(_COMPOSE_SRC.read_text())
        assert "neo4j" in data["services"]

    def test_qdrant_ports(self) -> None:
        """Qdrant service exposes HTTP and gRPC ports."""
        from gobby.cli.installers.qdrant import _COMPOSE_SRC

        data = yaml.safe_load(_COMPOSE_SRC.read_text())
        ports = data["services"]["qdrant"]["ports"]
        port_strs = [str(p) for p in ports]
        assert any("6333" in p for p in port_strs)
        assert any("6334" in p for p in port_strs)

    def test_qdrant_has_healthcheck(self) -> None:
        """Qdrant service has a healthcheck."""
        from gobby.cli.installers.qdrant import _COMPOSE_SRC

        data = yaml.safe_load(_COMPOSE_SRC.read_text())
        assert "healthcheck" in data["services"]["qdrant"]

    def test_qdrant_healthcheck_uses_healthz(self) -> None:
        """Qdrant healthcheck uses /healthz endpoint."""
        from gobby.cli.installers.qdrant import _COMPOSE_SRC

        data = yaml.safe_load(_COMPOSE_SRC.read_text())
        test_cmd = data["services"]["qdrant"]["healthcheck"]["test"]
        assert any("healthz" in str(t) for t in test_cmd)

    def test_qdrant_uses_bind_mount(self) -> None:
        """Qdrant uses bind mount for storage (not Docker volume)."""
        from gobby.cli.installers.qdrant import _COMPOSE_SRC

        data = yaml.safe_load(_COMPOSE_SRC.read_text())
        volumes = data["services"]["qdrant"]["volumes"]
        assert any("./qdrant:/qdrant/storage" in str(v) for v in volumes)

    def test_qdrant_has_profiles(self) -> None:
        """Qdrant service has docker compose profiles."""
        from gobby.cli.installers.qdrant import _COMPOSE_SRC

        data = yaml.safe_load(_COMPOSE_SRC.read_text())
        profiles = data["services"]["qdrant"]["profiles"]
        assert "qdrant" in profiles
        assert "all" in profiles

    def test_neo4j_has_profiles(self) -> None:
        """Neo4j service has docker compose profiles."""
        from gobby.cli.installers.qdrant import _COMPOSE_SRC

        data = yaml.safe_load(_COMPOSE_SRC.read_text())
        profiles = data["services"]["neo4j"]["profiles"]
        assert "neo4j" in profiles
        assert "all" in profiles

    def test_compose_has_neo4j_volume(self) -> None:
        """Compose file defines gobby_neo4j_data volume."""
        from gobby.cli.installers.qdrant import _COMPOSE_SRC

        data = yaml.safe_load(_COMPOSE_SRC.read_text())
        assert "gobby_neo4j_data" in data.get("volumes", {})

    def test_qdrant_restart_policy(self) -> None:
        """Qdrant service has unless-stopped restart policy."""
        from gobby.cli.installers.qdrant import _COMPOSE_SRC

        data = yaml.safe_load(_COMPOSE_SRC.read_text())
        assert data["services"]["qdrant"]["restart"] == "unless-stopped"


# ---------------------------------------------------------------------------
# Installer function tests
# ---------------------------------------------------------------------------


class TestInstallQdrant:
    """Tests for install_qdrant function."""

    def test_install_qdrant_no_docker(self, tmp_path: Path) -> None:
        """install_qdrant returns error when Docker is not available."""
        from gobby.cli.installers.qdrant import install_qdrant

        with patch.object(shutil, "which", return_value=None):
            result = install_qdrant(gobby_home=tmp_path)

        assert result["success"] is False
        assert "Docker not found" in result["error"]

    def test_install_creates_compose_file(self, tmp_path: Path) -> None:
        """install_qdrant copies compose template to services directory."""
        from gobby.cli.installers.qdrant import _ensure_unified_compose

        services_dir = tmp_path / "services"
        services_dir.mkdir()
        compose_file = _ensure_unified_compose(services_dir)

        assert compose_file.exists()
        assert compose_file.name == "docker-compose.yml"
        data = yaml.safe_load(compose_file.read_text())
        assert "qdrant" in data["services"]

    def test_install_creates_qdrant_storage_dir(self, tmp_path: Path) -> None:
        """install_qdrant creates qdrant storage directory for bind mount."""
        from gobby.cli.installers.qdrant import install_qdrant

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch.object(shutil, "which", return_value="/usr/bin/docker"),
            patch("gobby.cli.installers.qdrant.subprocess.run", return_value=mock_result),
            patch("gobby.cli.installers.qdrant._wait_for_health", return_value=True),
            patch("gobby.cli.installers.qdrant._update_config"),
        ):
            result = install_qdrant(gobby_home=tmp_path)

        assert result["success"] is True
        assert (tmp_path / "services" / "qdrant").is_dir()

    def test_install_returns_url(self, tmp_path: Path) -> None:
        """install_qdrant returns the configured URL on success."""
        from gobby.cli.installers.qdrant import install_qdrant

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch.object(shutil, "which", return_value="/usr/bin/docker"),
            patch("gobby.cli.installers.qdrant.subprocess.run", return_value=mock_result),
            patch("gobby.cli.installers.qdrant._wait_for_health", return_value=True),
            patch("gobby.cli.installers.qdrant._update_config"),
        ):
            result = install_qdrant(gobby_home=tmp_path, port=6333)

        assert result["qdrant_url"] == "http://localhost:6333"

    def test_install_health_check_failure(self, tmp_path: Path) -> None:
        """install_qdrant returns error when health check fails."""
        from gobby.cli.installers.qdrant import install_qdrant

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch.object(shutil, "which", return_value="/usr/bin/docker"),
            patch("gobby.cli.installers.qdrant.subprocess.run", return_value=mock_result),
            patch("gobby.cli.installers.qdrant._wait_for_health", return_value=False),
        ):
            result = install_qdrant(gobby_home=tmp_path)

        assert result["success"] is False
        assert "Health check failed" in result["error"]


# ---------------------------------------------------------------------------
# Uninstaller tests
# ---------------------------------------------------------------------------


class TestUninstallQdrant:
    """Tests for uninstall_qdrant function."""

    def test_uninstall_without_data(self, tmp_path: Path) -> None:
        """uninstall_qdrant succeeds without removing data."""
        from gobby.cli.installers.qdrant import uninstall_qdrant

        # Create compose file
        services_dir = tmp_path / "services"
        services_dir.mkdir()
        compose = services_dir / "docker-compose.yml"
        compose.write_text("services:\n  qdrant:\n    image: qdrant/qdrant\n")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("gobby.cli.installers.qdrant.subprocess.run", return_value=mock_result),
            patch("gobby.cli.installers.qdrant._update_config"),
        ):
            result = uninstall_qdrant(gobby_home=tmp_path)

        assert result["success"] is True
        assert result["data_removed"] is False

    def test_uninstall_with_data_removal(self, tmp_path: Path) -> None:
        """uninstall_qdrant removes storage directory when requested."""
        from gobby.cli.installers.qdrant import uninstall_qdrant

        services_dir = tmp_path / "services"
        qdrant_dir = services_dir / "qdrant"
        qdrant_dir.mkdir(parents=True)
        (qdrant_dir / "test_data").write_text("data")
        compose = services_dir / "docker-compose.yml"
        compose.write_text("services:\n  qdrant:\n    image: qdrant/qdrant\n")

        mock_result = MagicMock()
        mock_result.returncode = 0

        with (
            patch("gobby.cli.installers.qdrant.subprocess.run", return_value=mock_result),
            patch("gobby.cli.installers.qdrant._update_config"),
        ):
            result = uninstall_qdrant(gobby_home=tmp_path, remove_data=True)

        assert result["success"] is True
        assert result["data_removed"] is True
        assert not qdrant_dir.exists()


# ---------------------------------------------------------------------------
# Health check tests
# ---------------------------------------------------------------------------


class TestQdrantHealthCheck:
    """Tests for Qdrant health check."""

    @pytest.mark.asyncio
    async def test_is_qdrant_healthy_none_url(self) -> None:
        """Returns False for None URL."""
        from gobby.cli.services import is_qdrant_healthy

        assert await is_qdrant_healthy(None) is False

    @pytest.mark.asyncio
    async def test_is_qdrant_installed_no_files(self, tmp_path: Path) -> None:
        """Returns False when no compose file exists."""
        from gobby.cli.services import is_qdrant_installed

        assert is_qdrant_installed(gobby_home=tmp_path) is False

    def test_is_qdrant_installed_with_files(self, tmp_path: Path) -> None:
        """Returns True when compose file and qdrant dir exist."""
        from gobby.cli.services import is_qdrant_installed

        services = tmp_path / "services"
        (services / "qdrant").mkdir(parents=True)
        (services / "docker-compose.yml").write_text("services: {}")

        assert is_qdrant_installed(gobby_home=tmp_path) is True


# ---------------------------------------------------------------------------
# Config model tests
# ---------------------------------------------------------------------------


class TestConfigModels:
    """Tests for new DatabasesConfig and EmbeddingsConfig models."""

    def test_databases_config_defaults(self) -> None:
        """DatabasesConfig has sensible defaults."""
        from gobby.config.persistence import DatabasesConfig

        config = DatabasesConfig()
        assert config.qdrant.url is None
        assert config.qdrant.port == 6333
        assert config.neo4j.url == "http://localhost:8474"
        assert config.neo4j.database == "neo4j"

    def test_embeddings_config_defaults(self) -> None:
        """EmbeddingsConfig has sensible defaults."""
        from gobby.config.persistence import EmbeddingsConfig

        config = EmbeddingsConfig()
        assert config.model == "local/nomic-embed-text-v1.5"
        assert config.dim == 768

    def test_qdrant_config_mutual_exclusivity(self) -> None:
        """QdrantConfig rejects both path and url set."""
        from gobby.config.persistence import QdrantConfig

        with pytest.raises(ValueError, match="mutually exclusive"):
            QdrantConfig(path="/some/path", url="http://localhost:6333")

    def test_daemon_config_has_databases(self) -> None:
        """DaemonConfig includes databases and embeddings."""
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()
        assert hasattr(config, "databases")
        assert hasattr(config, "embeddings")
        assert config.databases.qdrant.port == 6333
        assert config.embeddings.dim == 768

    def test_memory_config_deprecated_fields_still_work(self) -> None:
        """MemoryConfig deprecated fields still load for backwards compat."""
        from gobby.config.persistence import MemoryConfig

        config = MemoryConfig(
            qdrant_url="http://localhost:6333",
            embedding_model="local/nomic-embed-text-v1.5",
        )
        assert config.qdrant_url == "http://localhost:6333"
        assert config.embedding_model == "local/nomic-embed-text-v1.5"
