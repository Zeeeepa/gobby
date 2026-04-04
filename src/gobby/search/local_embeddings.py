"""Local embedding generation using llama-cpp-python.

Provides in-process embedding generation via nomic-embed-text-v1.5 GGUF,
eliminating the need for external API keys or network calls.

The model auto-downloads from HuggingFace on first use (~139MB Q8_0 GGUF)
and runs at ~5-10ms per embedding with Metal/CUDA auto-detection.

Output: 768 dimensions (nomic-embed-text-v1.5).
"""

from __future__ import annotations

import asyncio
import logging
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from llama_cpp import Llama

logger = logging.getLogger(__name__)

# Module-level callback reference — must survive GC for the lifetime of the
# process, because llama.cpp holds a raw C pointer to this function.
_ggml_log_filter_cb: object | None = None
_ggml_log_filter_lock = threading.Lock()


def _install_ggml_log_filter() -> None:
    """Install a GGML log callback that filters known harmless spam.

    GGML emits "init: embeddings required but some input tokens were not
    marked as outputs -> overriding" at ERROR level during embedding context
    creation. These are harmless (GGML auto-fixes the token flags) but
    produce hundreds of lines of log spam. llama-cpp-python's default
    callback prints ERROR-level messages even with verbose=False.

    The callback is installed once and kept permanently — it must outlive
    any async GGML/Metal threads that fire after the Llama constructor
    returns. Storing it at module level prevents GC from invalidating the
    ctypes function pointer.
    """
    global _ggml_log_filter_cb
    if _ggml_log_filter_cb is not None:
        return  # Already installed

    with _ggml_log_filter_lock:
        # Double-check after acquiring lock
        if _ggml_log_filter_cb is not None:
            return

        import ctypes

        import llama_cpp

        def _py_callback(
            level: int,
            text: bytes,
            user_data: ctypes.c_void_p,
        ) -> None:
            msg = text.decode("utf-8", errors="replace")
            if "not marked as outputs" in msg:
                return
            if "not supported" in msg:
                return
            # Pass through non-spam messages at ERROR level (matching default
            # verbose=False behavior: only ERROR and above).
            if level >= 3 and msg.strip():  # 3 = GGML_LOG_LEVEL_ERROR
                print(msg, end="", flush=True, file=sys.stderr)

        _filtered_callback = llama_cpp.llama_log_callback(_py_callback)
        _ggml_log_filter_cb = _filtered_callback  # prevent GC
        llama_cpp.llama_log_set(_filtered_callback, ctypes.c_void_p(0))


# Model registry: local/ prefix → HuggingFace download info
_MODEL_REGISTRY: dict[str, dict[str, str]] = {
    "nomic-embed-text-v1.5": {
        "filename": "nomic-embed-text-v1.5.Q8_0.gguf",
        "url": "https://huggingface.co/nomic-ai/nomic-embed-text-v1.5-GGUF/resolve/main/nomic-embed-text-v1.5.Q8_0.gguf",
        "dim": "768",
    },
}

# Default model directory
_DEFAULT_MODEL_DIR = Path.home() / ".gobby" / "models"


def get_default_model_path(model_name: str = "nomic-embed-text-v1.5") -> Path:
    """Get the default path for a local embedding model.

    Args:
        model_name: Short model name (without local/ prefix)

    Returns:
        Path to the GGUF model file
    """
    info = _MODEL_REGISTRY.get(model_name)
    if not info:
        return _DEFAULT_MODEL_DIR / f"{model_name}.gguf"
    return _DEFAULT_MODEL_DIR / info["filename"]


def is_local_model(model: str) -> bool:
    """Check if a model string refers to a local embedding model.

    Args:
        model: Model identifier (e.g., "local/nomic-embed-text-v1.5")

    Returns:
        True if model uses the local/ prefix
    """
    return model.startswith("local/")


def get_model_dim(model: str) -> int:
    """Get the embedding dimension for a local model.

    Args:
        model: Model identifier with local/ prefix

    Returns:
        Embedding dimension (e.g., 768 for nomic)
    """
    name = model.removeprefix("local/")
    info = _MODEL_REGISTRY.get(name)
    return int(info["dim"]) if info else 768


def list_downloaded_models() -> list[dict[str, str]]:
    """List all downloaded models in the models directory.

    Returns:
        List of dicts with name, filename, path, size info
    """
    models: list[dict[str, str]] = []
    if not _DEFAULT_MODEL_DIR.exists():
        return models
    for path in sorted(_DEFAULT_MODEL_DIR.glob("*.gguf")):
        size_mb = path.stat().st_size / (1024 * 1024)
        models.append(
            {
                "name": path.stem,
                "filename": path.name,
                "path": str(path),
                "size": f"{size_mb:.1f} MB",
            }
        )
    return models


class LocalEmbeddingModel:
    """Singleton in-process embedding model using llama-cpp-python.

    Lazily loads the model on first use. Thread-safe via asyncio.Lock.
    The model is shared across all consumers (memory, search, code index, MCP tool search).
    """

    _instance: LocalEmbeddingModel | None = None
    _lock: asyncio.Lock = asyncio.Lock()

    def __init__(self, model_path: Path) -> None:
        self._model_path = model_path
        self._llama: Llama | None = None
        self._inference_lock = threading.Lock()

    @classmethod
    async def get_instance(cls, model_name: str = "nomic-embed-text-v1.5") -> LocalEmbeddingModel:
        """Get or create the singleton instance.

        Args:
            model_name: Short model name (without local/ prefix)

        Returns:
            Shared LocalEmbeddingModel instance
        """
        async with cls._lock:
            if cls._instance is None:
                model_path = get_default_model_path(model_name)
                cls._instance = cls(model_path)
            return cls._instance

    @classmethod
    def reset(cls) -> None:
        """Reset the singleton (for testing)."""
        if cls._instance and cls._instance._llama:
            del cls._instance._llama
        cls._instance = None

    async def _ensure_loaded(self) -> None:
        """Ensure the model is downloaded and loaded."""
        if self._llama is not None:
            return

        # Download if missing
        if not self._model_path.exists():
            await self._download_model()

        # Load model in a thread to avoid blocking the event loop
        self._llama = await asyncio.to_thread(self._load_model)

    def _load_model(self) -> Llama:
        """Load the GGUF model (runs in thread)."""
        try:
            from llama_cpp import Llama
        except ImportError as e:
            raise RuntimeError(
                "llama-cpp-python not installed. Run: uv sync --extra local-embeddings"
            ) from e

        logger.info(f"Loading local embedding model: {self._model_path.name}")

        _install_ggml_log_filter()

        model = Llama(
            model_path=str(self._model_path),
            embedding=True,
            n_ctx=2048,
            n_gpu_layers=-1,  # Auto-detect Metal/CUDA
            verbose=False,
        )

        logger.info(f"Local embedding model loaded: {self._model_path.name}")
        return model

    async def _download_model(self) -> None:
        """Download the model from HuggingFace."""
        import httpx

        # Find URL from registry
        model_name = self._model_path.stem.replace(".Q8_0", "")
        info = _MODEL_REGISTRY.get(model_name)
        if not info:
            raise RuntimeError(
                f"Unknown local model: {model_name}. Available: {', '.join(_MODEL_REGISTRY.keys())}"
            )

        url = info["url"]
        self._model_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._model_path.with_suffix(".tmp")

        logger.info(f"Downloading embedding model: {info['filename']}")
        logger.info(f"  From: {url}")
        logger.info(f"  To: {self._model_path}")

        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=300.0) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    total = int(response.headers.get("content-length", 0))
                    downloaded = 0
                    last_pct = -1

                    with open(tmp_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=1024 * 1024):
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total > 0:
                                pct = (downloaded * 100) // total
                                # Log every 10%
                                if pct // 10 > last_pct // 10:
                                    last_pct = pct
                                    logger.info(
                                        f"  Download progress: {pct}% "
                                        f"({downloaded / 1024 / 1024:.1f} MB / "
                                        f"{total / 1024 / 1024:.1f} MB)"
                                    )

            # Atomic rename
            tmp_path.rename(self._model_path)
            size_mb = self._model_path.stat().st_size / (1024 * 1024)
            logger.info(f"Download complete: {info['filename']} ({size_mb:.1f} MB)")

        except Exception:
            # Clean up partial download
            if tmp_path.exists():
                tmp_path.unlink()
            raise

    async def embed(
        self,
        texts: list[str],
        is_query: bool = False,
    ) -> list[list[float]]:
        """Generate embeddings for a list of texts.

        nomic-embed-text-v1.5 requires task prefixes:
        - "search_document: " for documents being indexed
        - "search_query: " for search queries

        Args:
            texts: List of texts to embed
            is_query: If True, prepend "search_query: " prefix;
                      otherwise prepend "search_document: "

        Returns:
            List of embedding vectors (768 dimensions each)
        """
        if not texts:
            return []

        await self._ensure_loaded()
        assert self._llama is not None  # noqa: S101

        prefix = "search_query: " if is_query else "search_document: "
        prefixed_texts = [f"{prefix}{t}" for t in texts]

        # Run in thread to avoid blocking the event loop
        embeddings = await asyncio.to_thread(self._embed_sync, prefixed_texts)
        return embeddings

    def _embed_sync(self, texts: list[str]) -> list[list[float]]:
        """Synchronous embedding (runs in thread).

        Protected by threading.Lock because llama-cpp-python is not
        thread-safe — concurrent calls to llama_decode segfault.
        """
        assert self._llama is not None  # noqa: S101
        with self._inference_lock:
            results: list[list[float]] = []
            for text in texts:
                output = self._llama.embed(text)
                # llama-cpp-python returns list[float] for single input
                if isinstance(output[0], float):
                    results.append(output)
                else:
                    results.append(output[0])
            return results


async def generate_embeddings_local(
    texts: list[str],
    model: str = "local/nomic-embed-text-v1.5",
    is_query: bool = False,
) -> list[list[float]]:
    """Generate embeddings using the local model.

    Args:
        texts: List of texts to embed
        model: Model identifier with local/ prefix
        is_query: Whether the texts are search queries (vs documents)

    Returns:
        List of embedding vectors
    """
    if not texts:
        return []

    model_name = model.removeprefix("local/")
    instance = await LocalEmbeddingModel.get_instance(model_name)
    return await instance.embed(texts, is_query=is_query)


async def generate_embedding_local(
    text: str,
    model: str = "local/nomic-embed-text-v1.5",
    is_query: bool = False,
) -> list[float]:
    """Generate embedding for a single text using the local model.

    Args:
        text: Text to embed
        model: Model identifier with local/ prefix
        is_query: Whether the text is a search query (vs document)

    Returns:
        Embedding vector
    """
    results = await generate_embeddings_local([text], model=model, is_query=is_query)
    if not results:
        raise RuntimeError(f"Local embedding model returned empty result for model={model}")
    return results[0]


async def download_model(model_name: str = "nomic-embed-text-v1.5") -> Path:
    """Download a model (for use by CLI).

    Args:
        model_name: Short model name (without local/ prefix)

    Returns:
        Path to the downloaded model file

    Raises:
        RuntimeError: If model name is unknown
    """
    model_path = get_default_model_path(model_name)
    if model_path.exists():
        size_mb = model_path.stat().st_size / (1024 * 1024)
        logger.info(f"Model already downloaded: {model_path} ({size_mb:.1f} MB)")
        return model_path

    instance = LocalEmbeddingModel(model_path)
    await instance._download_model()
    return model_path


def remove_model(model_name: str) -> bool:
    """Remove a downloaded model.

    Args:
        model_name: Short model name or filename stem

    Returns:
        True if removed, False if not found
    """
    # Try direct match first
    model_path = get_default_model_path(model_name)
    if model_path.exists():
        model_path.unlink()
        logger.info(f"Removed model: {model_path}")
        # Reset singleton if it was using this model
        LocalEmbeddingModel.reset()
        return True

    # Try as filename stem
    candidate = _DEFAULT_MODEL_DIR / f"{model_name}.gguf"
    if candidate.exists():
        candidate.unlink()
        logger.info(f"Removed model: {candidate}")
        LocalEmbeddingModel.reset()
        return True

    return False
