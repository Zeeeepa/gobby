"""Speech-to-text service using faster-whisper (local Whisper inference).

Lazy-loads the model on first transcription to avoid slowing daemon boot.
All inference runs in a thread pool since it's CPU-bound.
"""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.config.voice import VoiceConfig

logger = logging.getLogger(__name__)


class WhisperSTT:
    """Local speech-to-text using faster-whisper."""

    def __init__(self, config: VoiceConfig) -> None:
        self._config = config
        self._model: object | None = None
        self._loading = False
        self._load_lock = asyncio.Lock()

    async def _ensure_model(self) -> object:
        """Lazy-load the Whisper model (thread-safe, async)."""
        if self._model is not None:
            return self._model

        async with self._load_lock:
            # Double-check after acquiring lock
            if self._model is not None:
                return self._model

            logger.info(
                f"Loading Whisper model: {self._config.whisper_model_size} "
                f"(device={self._config.whisper_device}, "
                f"compute_type={self._config.whisper_compute_type})"
            )

            def _load() -> object:
                from faster_whisper import WhisperModel

                return WhisperModel(
                    self._config.whisper_model_size,
                    device=self._config.whisper_device,
                    compute_type=self._config.whisper_compute_type,
                )

            self._model = await asyncio.to_thread(_load)
            logger.info("Whisper model loaded successfully")
            return self._model

    async def transcribe(self, audio_bytes: bytes, mime_type: str = "audio/webm") -> str:
        """Transcribe audio bytes to text.

        Args:
            audio_bytes: Raw audio data (WebM/Opus, WAV, etc.)
            mime_type: MIME type of the audio data.

        Returns:
            Transcribed text string.
        """
        model = await self._ensure_model()

        # Determine file extension from mime type
        ext_map = {
            "audio/webm": ".webm",
            "audio/webm;codecs=opus": ".webm",
            "audio/wav": ".wav",
            "audio/mp3": ".mp3",
            "audio/mpeg": ".mp3",
            "audio/ogg": ".ogg",
            "audio/mp4": ".m4a",
        }
        ext = ext_map.get(mime_type.split(";")[0].strip(), ".webm")

        def _transcribe() -> str:
            # Write to temp file for faster-whisper
            with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as f:
                f.write(audio_bytes)
                tmp_path = Path(f.name)

            try:
                segments, info = model.transcribe(  # type: ignore[union-attr]
                    str(tmp_path),
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 500},
                )
                text = " ".join(seg.text.strip() for seg in segments)
                logger.debug(
                    f"Transcribed {len(audio_bytes)} bytes "
                    f"({info.duration:.1f}s) -> {len(text)} chars"
                )
                return text
            finally:
                tmp_path.unlink(missing_ok=True)

        return await asyncio.to_thread(_transcribe)

    @property
    def is_available(self) -> bool:
        """Check if faster-whisper is installed."""
        try:
            import faster_whisper  # noqa: F401

            return True
        except ImportError:
            return False
