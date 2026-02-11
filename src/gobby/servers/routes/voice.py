"""Voice API routes for testing and status."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, File, UploadFile

if TYPE_CHECKING:
    from gobby.servers.http import HTTPServer

logger = logging.getLogger(__name__)


def create_voice_router(server: HTTPServer) -> APIRouter:
    """Create voice API router.

    Args:
        server: HTTPServer instance for accessing services.

    Returns:
        Configured APIRouter.
    """
    router = APIRouter(prefix="/api/voice", tags=["voice"])

    @router.get("/status")
    async def voice_status() -> dict[str, Any]:
        """Check voice feature availability."""
        config = server.config
        if not config or not hasattr(config, "voice"):
            return {
                "enabled": False,
                "stt_available": False,
                "tts_available": False,
                "reason": "Voice config not found",
            }

        voice_config = config.voice

        # Check STT availability
        stt_available = False
        stt_reason = ""
        if voice_config.enabled:
            try:
                import faster_whisper  # noqa: F401

                stt_available = True
            except ImportError:
                stt_reason = "faster-whisper not installed (pip install faster-whisper)"
        else:
            stt_reason = "Voice not enabled in config"

        # Check TTS availability
        tts_available = bool(voice_config.elevenlabs_api_key)
        tts_reason = "" if tts_available else "No ElevenLabs API key configured"

        return {
            "enabled": voice_config.enabled,
            "stt_available": stt_available,
            "stt_reason": stt_reason,
            "tts_available": tts_available,
            "tts_reason": tts_reason,
            "whisper_model": voice_config.whisper_model_size,
            "tts_voice_id": voice_config.elevenlabs_voice_id,
            "audio_format": voice_config.audio_format,
        }

    @router.post("/transcribe")
    async def transcribe_audio(file: UploadFile = File(...)) -> dict[str, Any]:
        """One-shot audio transcription (for testing).

        Upload an audio file to get transcription text.
        """
        config = server.config
        if not config or not hasattr(config, "voice") or not config.voice.enabled:
            return {"error": "Voice not enabled", "text": ""}

        from gobby.voice.stt import WhisperSTT

        stt = WhisperSTT(config.voice)
        if not stt.is_available:
            return {
                "error": "faster-whisper not installed",
                "text": "",
            }

        audio_bytes = await file.read()
        content_type = file.content_type or "audio/webm"

        try:
            text = await stt.transcribe(audio_bytes, content_type)
            return {
                "text": text,
                "bytes": len(audio_bytes),
                "content_type": content_type,
            }
        except Exception as e:
            logger.error(f"Transcription error: {e}", exc_info=True)
            return {"error": str(e), "text": ""}

    return router
