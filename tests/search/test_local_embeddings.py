"""Tests for local embedding generation using llama-cpp-python."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gobby.search.local_embeddings import (
    _MODEL_REGISTRY,
    LocalEmbeddingModel,
    download_model,
    generate_embedding_local,
    generate_embeddings_local,
    get_default_model_path,
    get_model_dim,
    is_local_model,
    list_downloaded_models,
    remove_model,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Reset the LocalEmbeddingModel singleton between tests."""
    LocalEmbeddingModel.reset()
    yield
    LocalEmbeddingModel.reset()


class TestIsLocalModel:
    """Tests for is_local_model()."""

    def test_local_prefix_returns_true(self) -> None:
        assert is_local_model("local/nomic-embed-text-v1.5") is True

    def test_local_prefix_other_model(self) -> None:
        assert is_local_model("local/some-other-model") is True

    def test_non_local_returns_false(self) -> None:
        assert is_local_model("text-embedding-3-small") is False

    def test_openai_prefix_returns_false(self) -> None:
        assert is_local_model("openai/text-embedding-3-small") is False

    def test_ollama_prefix_returns_false(self) -> None:
        assert is_local_model("ollama/nomic-embed-text") is False


class TestGetDefaultModelPath:
    """Tests for get_default_model_path()."""

    def test_known_model_returns_correct_path(self) -> None:
        path = get_default_model_path("nomic-embed-text-v1.5")
        assert path.name == "nomic-embed-text-v1.5.Q8_0.gguf"
        assert str(path).endswith(".gobby/models/nomic-embed-text-v1.5.Q8_0.gguf")

    def test_unknown_model_returns_generic_path(self) -> None:
        path = get_default_model_path("unknown-model")
        assert path.name == "unknown-model.gguf"


class TestGetModelDim:
    """Tests for get_model_dim()."""

    def test_nomic_returns_768(self) -> None:
        assert get_model_dim("local/nomic-embed-text-v1.5") == 768

    def test_unknown_model_returns_default_768(self) -> None:
        assert get_model_dim("local/unknown") == 768


class TestModelRegistry:
    """Tests for the model registry."""

    def test_nomic_in_registry(self) -> None:
        assert "nomic-embed-text-v1.5" in _MODEL_REGISTRY

    def test_nomic_has_required_fields(self) -> None:
        info = _MODEL_REGISTRY["nomic-embed-text-v1.5"]
        assert "filename" in info
        assert "url" in info
        assert "dim" in info
        assert info["dim"] == "768"


class TestListDownloadedModels:
    """Tests for list_downloaded_models()."""

    def test_returns_empty_when_dir_missing(self, tmp_path: Path) -> None:
        with patch("gobby.search.local_embeddings._DEFAULT_MODEL_DIR", tmp_path / "nonexistent"):
            result = list_downloaded_models()
            assert result == []

    def test_finds_gguf_files(self, tmp_path: Path) -> None:
        (tmp_path / "model-a.gguf").write_bytes(b"x" * 1024)
        (tmp_path / "model-b.gguf").write_bytes(b"x" * 2048)
        (tmp_path / "not-a-model.txt").write_text("nope")

        with patch("gobby.search.local_embeddings._DEFAULT_MODEL_DIR", tmp_path):
            result = list_downloaded_models()
            assert len(result) == 2
            names = {m["name"] for m in result}
            assert "model-a" in names
            assert "model-b" in names


class TestLocalEmbeddingModelSingleton:
    """Tests for LocalEmbeddingModel singleton behavior."""

    @pytest.mark.asyncio
    async def test_get_instance_returns_same_object(self) -> None:
        instance1 = await LocalEmbeddingModel.get_instance("nomic-embed-text-v1.5")
        instance2 = await LocalEmbeddingModel.get_instance("nomic-embed-text-v1.5")
        assert instance1 is instance2

    def test_reset_clears_singleton(self) -> None:
        LocalEmbeddingModel._instance = LocalEmbeddingModel(Path("/fake"))
        assert LocalEmbeddingModel._instance is not None
        LocalEmbeddingModel.reset()
        assert LocalEmbeddingModel._instance is None


class TestLocalEmbeddingModelDownload:
    """Tests for model download logic."""

    @pytest.mark.asyncio
    async def test_download_streams_and_renames(self, tmp_path: Path) -> None:
        """Test that download writes to tmp then renames."""
        model_path = tmp_path / "test-model.Q8_0.gguf"
        instance = LocalEmbeddingModel(model_path)

        # Mock the registry to use our path
        mock_registry = {
            "test-model": {
                "filename": "test-model.Q8_0.gguf",
                "url": "https://example.com/model.gguf",
                "dim": "768",
            }
        }

        fake_content = b"fake-model-data" * 100

        # Create a mock async streaming response
        mock_response = AsyncMock()
        mock_response.headers = {"content-length": str(len(fake_content))}
        mock_response.raise_for_status = MagicMock()

        async def fake_aiter_bytes(chunk_size: int = 1024):
            yield fake_content

        mock_response.aiter_bytes = fake_aiter_bytes

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock()

        # stream() returns async context manager
        stream_ctx = AsyncMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        stream_ctx.__aexit__ = AsyncMock()
        mock_client.stream = MagicMock(return_value=stream_ctx)

        with (
            patch("gobby.search.local_embeddings._MODEL_REGISTRY", mock_registry),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            await instance._download_model()

        assert model_path.exists()
        assert model_path.read_bytes() == fake_content
        # tmp file should not exist
        assert not model_path.with_suffix(".tmp").exists()

    @pytest.mark.asyncio
    async def test_download_cleans_up_on_error(self, tmp_path: Path) -> None:
        """Test that partial downloads are cleaned up on error."""
        model_path = tmp_path / "fail-model.Q8_0.gguf"
        instance = LocalEmbeddingModel(model_path)

        mock_registry = {
            "fail-model": {
                "filename": "fail-model.Q8_0.gguf",
                "url": "https://example.com/model.gguf",
                "dim": "768",
            }
        }

        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)

        mock_response = AsyncMock()
        mock_response.raise_for_status = MagicMock(side_effect=Exception("HTTP 404"))

        stream_ctx = AsyncMock()
        stream_ctx.__aenter__ = AsyncMock(return_value=mock_response)
        stream_ctx.__aexit__ = AsyncMock(return_value=False)
        mock_client.stream = MagicMock(return_value=stream_ctx)

        with (
            patch("gobby.search.local_embeddings._MODEL_REGISTRY", mock_registry),
            patch("httpx.AsyncClient", return_value=mock_client),
        ):
            with pytest.raises(Exception, match="HTTP 404"):
                await instance._download_model()

        assert not model_path.exists()
        assert not model_path.with_suffix(".tmp").exists()


class TestLocalEmbeddingModelEmbed:
    """Tests for embedding generation."""

    @pytest.mark.asyncio
    async def test_embed_prepends_document_prefix(self, tmp_path: Path) -> None:
        """Test that document prefix is prepended for indexing."""
        model_path = tmp_path / "test.gguf"
        instance = LocalEmbeddingModel(model_path)

        mock_llama = MagicMock()
        mock_llama.embed.return_value = [0.1, 0.2, 0.3]
        instance._llama = mock_llama

        result = await instance.embed(["hello world"], is_query=False)

        mock_llama.embed.assert_called_once_with("search_document: hello world")
        assert result == [[0.1, 0.2, 0.3]]

    @pytest.mark.asyncio
    async def test_embed_prepends_query_prefix(self, tmp_path: Path) -> None:
        """Test that query prefix is prepended for search."""
        model_path = tmp_path / "test.gguf"
        instance = LocalEmbeddingModel(model_path)

        mock_llama = MagicMock()
        mock_llama.embed.return_value = [0.4, 0.5, 0.6]
        instance._llama = mock_llama

        result = await instance.embed(["search term"], is_query=True)

        mock_llama.embed.assert_called_once_with("search_query: search term")
        assert result == [[0.4, 0.5, 0.6]]

    @pytest.mark.asyncio
    async def test_embed_empty_list_returns_empty(self, tmp_path: Path) -> None:
        """Test that empty input returns empty output."""
        model_path = tmp_path / "test.gguf"
        instance = LocalEmbeddingModel(model_path)
        instance._llama = MagicMock()

        result = await instance.embed([])
        assert result == []

    @pytest.mark.asyncio
    async def test_embed_handles_nested_output(self, tmp_path: Path) -> None:
        """Test handling when llama_cpp returns nested list."""
        model_path = tmp_path / "test.gguf"
        instance = LocalEmbeddingModel(model_path)

        mock_llama = MagicMock()
        # Some versions return [[0.1, 0.2]] instead of [0.1, 0.2]
        mock_llama.embed.return_value = [[0.1, 0.2, 0.3]]
        instance._llama = mock_llama

        result = await instance.embed(["test"])
        assert result == [[0.1, 0.2, 0.3]]


class TestGenerateEmbeddingsLocal:
    """Tests for module-level convenience functions."""

    @pytest.mark.asyncio
    async def test_generate_embeddings_local_empty(self) -> None:
        result = await generate_embeddings_local([])
        assert result == []

    @pytest.mark.asyncio
    async def test_generate_embedding_local_delegates(self) -> None:
        with patch(
            "gobby.search.local_embeddings.LocalEmbeddingModel.get_instance",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_instance = AsyncMock()
            mock_instance.embed.return_value = [[0.1, 0.2, 0.3]]
            mock_get.return_value = mock_instance

            result = await generate_embedding_local("test text")
            assert result == [0.1, 0.2, 0.3]
            mock_instance.embed.assert_called_once_with(["test text"], is_query=False)

    @pytest.mark.asyncio
    async def test_generate_embedding_local_query_mode(self) -> None:
        with patch(
            "gobby.search.local_embeddings.LocalEmbeddingModel.get_instance",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_instance = AsyncMock()
            mock_instance.embed.return_value = [[0.7, 0.8, 0.9]]
            mock_get.return_value = mock_instance

            result = await generate_embedding_local("query", is_query=True)
            assert result == [0.7, 0.8, 0.9]
            mock_instance.embed.assert_called_once_with(["query"], is_query=True)

    @pytest.mark.asyncio
    async def test_generate_embedding_local_raises_on_empty_result(self) -> None:
        with patch(
            "gobby.search.local_embeddings.LocalEmbeddingModel.get_instance",
            new_callable=AsyncMock,
        ) as mock_get:
            mock_instance = AsyncMock()
            mock_instance.embed.return_value = []
            mock_get.return_value = mock_instance

            with pytest.raises(RuntimeError, match="empty result"):
                await generate_embedding_local("test")


class TestDownloadModel:
    """Tests for download_model convenience function."""

    @pytest.mark.asyncio
    async def test_already_downloaded(self, tmp_path: Path) -> None:
        model_path = tmp_path / "nomic-embed-text-v1.5.Q8_0.gguf"
        model_path.write_bytes(b"existing-model")

        with patch(
            "gobby.search.local_embeddings.get_default_model_path",
            return_value=model_path,
        ):
            result = await download_model("nomic-embed-text-v1.5")
            assert result == model_path


class TestRemoveModel:
    """Tests for remove_model function."""

    def test_remove_existing_model(self, tmp_path: Path) -> None:
        model_path = tmp_path / "nomic-embed-text-v1.5.Q8_0.gguf"
        model_path.write_bytes(b"model-data")

        with patch(
            "gobby.search.local_embeddings.get_default_model_path",
            return_value=model_path,
        ):
            assert remove_model("nomic-embed-text-v1.5") is True
            assert not model_path.exists()

    def test_remove_nonexistent_model(self, tmp_path: Path) -> None:
        with (
            patch(
                "gobby.search.local_embeddings.get_default_model_path",
                return_value=tmp_path / "nonexistent.gguf",
            ),
            patch(
                "gobby.search.local_embeddings._DEFAULT_MODEL_DIR",
                tmp_path,
            ),
        ):
            assert remove_model("nonexistent") is False
