"""WebSocket voice chat handling.

VoiceMixin provides STT/TTS integration for WebSocketServer.
Voice layers on top of the existing chat pipeline — transcribed audio
becomes a normal chat_message, and streamed text responses are
optionally synthesized to speech.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from typing import TYPE_CHECKING, Any

from websockets.exceptions import ConnectionClosed, ConnectionClosedError

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from gobby.config.voice import VoiceConfig


class VoiceMixin:
    """Mixin providing voice chat methods for WebSocketServer.

    Requires on the host class:
    - ``self.daemon_config`` with a ``.voice`` attribute
    - ``self._handle_chat_message(ws, data)`` (from ChatMixin)
    - ``self.clients: dict[Any, dict[str, Any]]``
    """

    # Declare expected attributes for type checking
    clients: dict[Any, dict[str, Any]]

    if TYPE_CHECKING:

        async def _handle_chat_message(self, websocket: Any, data: dict[str, Any]) -> None: ...

    def _init_voice(self) -> None:
        """Initialize voice subsystem state. Called from __init__."""
        # Per-conversation voice mode tracking
        self._voice_enabled: dict[str, bool] = {}

        # Lazy singletons
        self._whisper_stt: Any = None
        self._tts_sessions: dict[str, Any] = {}

        # Sentence buffer per conversation
        self._sentence_buffers: dict[str, Any] = {}

    def _get_voice_config(self) -> VoiceConfig | None:
        """Get voice config from daemon_config if available."""
        config = getattr(self, "daemon_config", None)
        if config and hasattr(config, "voice"):
            return config.voice
        return None

    def _get_stt(self) -> Any:
        """Get or create the WhisperSTT singleton."""
        if self._whisper_stt is not None:
            return self._whisper_stt

        voice_config = self._get_voice_config()
        if not voice_config or not voice_config.enabled:
            return None

        from gobby.voice.stt import WhisperSTT

        self._whisper_stt = WhisperSTT(voice_config)
        return self._whisper_stt

    def _get_tts(self, conversation_id: str) -> Any:
        """Get or create a per-conversation ElevenLabsTTS instance."""
        if conversation_id in self._tts_sessions:
            return self._tts_sessions[conversation_id]

        voice_config = self._get_voice_config()
        if not voice_config or not voice_config.enabled or not voice_config.elevenlabs_api_key:
            return None

        from gobby.voice.tts import ElevenLabsTTS

        tts = ElevenLabsTTS(voice_config)
        self._tts_sessions[conversation_id] = tts
        return tts

    def _get_sentence_buffer(self, conversation_id: str) -> Any:
        """Get or create a per-conversation SentenceBuffer."""
        if conversation_id not in self._sentence_buffers:
            from gobby.voice.sentence_buffer import SentenceBuffer

            self._sentence_buffers[conversation_id] = SentenceBuffer()
        return self._sentence_buffers[conversation_id]

    async def _handle_voice_audio(self, websocket: Any, data: dict[str, Any]) -> None:
        """Handle incoming voice audio from client.

        Transcribes audio via Whisper, sends transcription back,
        then forwards as a normal chat_message.

        Message format:
        {
            "type": "voice_audio",
            "conversation_id": "stable-id",
            "audio_data": "<base64-encoded-audio>",
            "mime_type": "audio/webm;codecs=opus",
            "request_id": "client-uuid"
        }
        """
        conversation_id = data.get("conversation_id", "")
        audio_data_b64 = data.get("audio_data", "")
        mime_type = data.get("mime_type", "audio/webm")
        request_id = data.get("request_id", "")

        if not audio_data_b64:
            await websocket.send(
                json.dumps(
                    {
                        "type": "voice_status",
                        "conversation_id": conversation_id,
                        "status": "error",
                        "error": "No audio data provided",
                    }
                )
            )
            return

        stt = self._get_stt()
        if not stt:
            await websocket.send(
                json.dumps(
                    {
                        "type": "voice_status",
                        "conversation_id": conversation_id,
                        "status": "error",
                        "error": "STT not available (voice not enabled or faster-whisper not installed)",
                    }
                )
            )
            return

        # Send transcribing status
        await websocket.send(
            json.dumps(
                {
                    "type": "voice_status",
                    "conversation_id": conversation_id,
                    "request_id": request_id,
                    "status": "transcribing",
                }
            )
        )

        try:
            start = time.monotonic()
            audio_bytes = base64.b64decode(audio_data_b64)
            text = await stt.transcribe(audio_bytes, mime_type)
            duration_ms = int((time.monotonic() - start) * 1000)

            if not text.strip():
                await websocket.send(
                    json.dumps(
                        {
                            "type": "voice_status",
                            "conversation_id": conversation_id,
                            "request_id": request_id,
                            "status": "empty",
                        }
                    )
                )
                return

            # Send transcription result
            await websocket.send(
                json.dumps(
                    {
                        "type": "voice_transcription",
                        "conversation_id": conversation_id,
                        "request_id": request_id,
                        "text": text,
                        "duration_ms": duration_ms,
                    }
                )
            )

            # Auto-submit as chat message through existing pipeline
            chat_data = {
                "type": "chat_message",
                "content": text,
                "conversation_id": conversation_id,
                "request_id": request_id,
            }
            await self._handle_chat_message(websocket, chat_data)

        except Exception as e:
            logger.error(f"Voice transcription error: {e}", exc_info=True)
            try:
                await websocket.send(
                    json.dumps(
                        {
                            "type": "voice_status",
                            "conversation_id": conversation_id,
                            "request_id": request_id,
                            "status": "error",
                            "error": str(e),
                        }
                    )
                )
            except (ConnectionClosed, ConnectionClosedError):
                pass

    async def _handle_voice_mode_toggle(self, websocket: Any, data: dict[str, Any]) -> None:
        """Handle voice mode enable/disable.

        Message format:
        {
            "type": "voice_mode_toggle",
            "conversation_id": "stable-id",
            "enabled": true
        }
        """
        conversation_id = data.get("conversation_id", "")
        enabled = data.get("enabled", False)

        self._voice_enabled[conversation_id] = enabled

        if not enabled:
            # Cleanup TTS session
            tts = self._tts_sessions.pop(conversation_id, None)
            if tts:
                await tts.disconnect()
            self._sentence_buffers.pop(conversation_id, None)

        await websocket.send(
            json.dumps(
                {
                    "type": "voice_status",
                    "conversation_id": conversation_id,
                    "status": "voice_mode_on" if enabled else "voice_mode_off",
                }
            )
        )

        logger.debug(f"Voice mode {'enabled' if enabled else 'disabled'} for {conversation_id[:8]}")

    async def _voice_tts_hook(
        self,
        websocket: Any,
        conversation_id: str,
        request_id: str,
        text_chunk: str,
    ) -> None:
        """Called from ChatMixin during TextChunk streaming to feed TTS.

        Buffers text into sentences and sends complete sentences to ElevenLabs.
        """
        if not self._voice_enabled.get(conversation_id):
            return

        tts = self._get_tts(conversation_id)
        if not tts or not tts.is_available:
            return

        buf = self._get_sentence_buffer(conversation_id)
        sentences = buf.add(text_chunk)

        for sentence in sentences:
            try:
                async for chunk in tts.synthesize_stream(sentence):
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "voice_audio_chunk",
                                "conversation_id": conversation_id,
                                "request_id": request_id,
                                "audio_data": chunk.audio_base64,
                                "is_final": False,
                                "format": self._get_voice_config().audio_format if self._get_voice_config() else "mp3_44100_128",
                            }
                        )
                    )
            except (ConnectionClosed, ConnectionClosedError):
                return
            except Exception as e:
                logger.error(f"TTS stream error: {e}")

    async def _voice_tts_flush(
        self,
        websocket: Any,
        conversation_id: str,
        request_id: str,
    ) -> None:
        """Called from ChatMixin on DoneEvent to flush remaining TTS audio."""
        if not self._voice_enabled.get(conversation_id):
            return

        tts = self._get_tts(conversation_id)
        if not tts or not tts.is_available:
            return

        buf = self._get_sentence_buffer(conversation_id)
        remaining = buf.flush()

        try:
            # Send any remaining buffered text
            if remaining:
                async for chunk in tts.synthesize_stream(remaining):
                    await websocket.send(
                        json.dumps(
                            {
                                "type": "voice_audio_chunk",
                                "conversation_id": conversation_id,
                                "request_id": request_id,
                                "audio_data": chunk.audio_base64,
                                "is_final": False,
                                "format": self._get_voice_config().audio_format if self._get_voice_config() else "mp3_44100_128",
                            }
                        )
                    )

            # Flush TTS connection
            async for chunk in tts.flush():
                await websocket.send(
                    json.dumps(
                        {
                            "type": "voice_audio_chunk",
                            "conversation_id": conversation_id,
                            "request_id": request_id,
                            "audio_data": chunk.audio_base64,
                            "is_final": chunk.is_final,
                            "format": self._get_voice_config().audio_format if self._get_voice_config() else "mp3_44100_128",
                        }
                    )
                )

            # Send final marker
            await websocket.send(
                json.dumps(
                    {
                        "type": "voice_audio_chunk",
                        "conversation_id": conversation_id,
                        "request_id": request_id,
                        "audio_data": "",
                        "is_final": True,
                        "format": self._get_voice_config().audio_format if self._get_voice_config() else "mp3_44100_128",
                    }
                )
            )

        except (ConnectionClosed, ConnectionClosedError):
            pass
        except Exception as e:
            logger.error(f"TTS flush error: {e}")

    async def _cleanup_voice(self) -> None:
        """Disconnect all TTS sessions. Called from stop()."""
        for conv_id, tts in list(self._tts_sessions.items()):
            try:
                await tts.disconnect()
            except Exception as e:
                logger.debug(f"Error disconnecting TTS for {conv_id[:8]}: {e}")

        self._tts_sessions.clear()
        self._voice_enabled.clear()
        self._sentence_buffers.clear()
        logger.debug("Voice subsystem cleaned up")
