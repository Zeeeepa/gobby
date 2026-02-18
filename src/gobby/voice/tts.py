"""Text-to-speech service using ElevenLabs streaming WebSocket API.

Decoupled send/receive architecture: text is sent without blocking,
and a background listener task forwards audio chunks via callback.
This prevents TTS from blocking the LLM text streaming pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from websockets.asyncio.client import ClientConnection

    from gobby.config.voice import VoiceConfig

logger = logging.getLogger(__name__)


@dataclass
class TTSAudioChunk:
    """A chunk of TTS audio data."""

    audio_base64: str
    is_final: bool


class ElevenLabsTTS:
    """Streaming TTS via ElevenLabs WebSocket API.

    Uses a non-blocking architecture:
    - send_text() fires text to ElevenLabs without waiting for audio
    - A background listener reads audio chunks and forwards via callback
    - send_flush() triggers generation of remaining buffered text
    """

    def __init__(self, config: VoiceConfig) -> None:
        self._config = config
        self._ws: ClientConnection | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._listener_task: asyncio.Task[None] | None = None
        self._connected = False

    async def connect(
        self,
        on_audio: Callable[[TTSAudioChunk], Awaitable[None]],
    ) -> None:
        """Open WebSocket connection and start background audio listener.

        Args:
            on_audio: Async callback invoked for each audio chunk received.
        """
        if self._connected:
            return

        try:
            import websockets

            voice_id = self._config.elevenlabs_voice_id
            model_id = self._config.elevenlabs_model_id
            api_key = self._config.elevenlabs_api_key
            url = (
                f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                f"/stream-input?model_id={model_id}"
                f"&optimize_streaming_latency=3"
            )

            self._ws = await websockets.connect(
                url,
                additional_headers={"xi-api-key": api_key},
            )

            # Send BOS (beginning of stream) message
            bos_message = {
                "text": " ",
                "voice_settings": {
                    "stability": self._config.elevenlabs_stability,
                    "similarity_boost": self._config.elevenlabs_similarity_boost,
                    "style": self._config.elevenlabs_style,
                    "speed": self._config.elevenlabs_speed,
                },
                "xi_api_key": self._config.elevenlabs_api_key,
                "output_format": self._config.audio_format,
                "generation_config": {
                    "chunk_length_schedule": [50, 120, 160, 250],
                },
            }
            await self._ws.send(json.dumps(bos_message))
            self._connected = True

            # Start background tasks
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())
            self._listener_task = asyncio.create_task(self._audio_listener(on_audio))

            logger.debug("ElevenLabs TTS WebSocket connected")

        except ImportError:
            logger.error("websockets package required for ElevenLabs TTS")
            raise
        except Exception as e:
            logger.error(f"Failed to connect to ElevenLabs: {e}")
            self._connected = False
            raise

    async def _keepalive_loop(self) -> None:
        """Send empty text every 15s to keep the connection alive."""
        try:
            while self._connected and self._ws:
                await asyncio.sleep(15)
                if self._connected and self._ws:
                    try:
                        await self._ws.send(json.dumps({"text": " "}))
                    except Exception:
                        break
        except asyncio.CancelledError:
            pass

    async def _audio_listener(
        self,
        on_audio: Callable[[TTSAudioChunk], Awaitable[None]],
    ) -> None:
        """Background task: read audio from ElevenLabs and forward via callback."""
        try:
            while self._connected and self._ws:
                try:
                    response = await self._ws.recv()
                    data = json.loads(response)

                    if data.get("audio"):
                        await on_audio(
                            TTSAudioChunk(
                                audio_base64=data["audio"],
                                is_final=data.get("isFinal", False),
                            )
                        )
                    elif data.get("isFinal"):
                        await on_audio(TTSAudioChunk(audio_base64="", is_final=True))

                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if self._connected:
                        logger.error(f"TTS listener error: {e}")
                    break
        except asyncio.CancelledError:
            pass

    async def send_text(self, text: str) -> None:
        """Send text for synthesis. Non-blocking -- audio arrives via listener.

        Uses try_trigger_generation to start audio generation immediately
        rather than waiting for the chunk_length_schedule buffer to fill.
        """
        if not self._connected or not self._ws:
            self._logger.debug(
                f"send_text skipped: connected={self._connected}, ws={self._ws is not None}"
            )
            return

        await self._ws.send(
            json.dumps(
                {
                    "text": text + " ",
                    "try_trigger_generation": True,
                }
            )
        )

    async def send_flush(self) -> None:
        """Flush remaining buffered text at end of conversation turn.

        Triggers immediate audio generation of all buffered text
        while keeping the connection alive for future turns.
        """
        if not self._connected or not self._ws:
            return

        await self._ws.send(json.dumps({"text": "", "flush": True}))

    async def disconnect(self) -> None:
        """Close the WebSocket connection and stop background tasks."""
        self._connected = False

        for task in (self._listener_task, self._keepalive_task):
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        self._listener_task = None
        self._keepalive_task = None

        if self._ws:
            try:
                # Send EOS before closing
                await self._ws.send(json.dumps({"text": ""}))
                await self._ws.close()
            except Exception as e:
                logger.debug(f"Error closing TTS WebSocket: {e}")
            self._ws = None

        logger.debug("ElevenLabs TTS disconnected")

    @property
    def is_available(self) -> bool:
        """Check if ElevenLabs API key is configured."""
        return bool(self._config.elevenlabs_api_key)
