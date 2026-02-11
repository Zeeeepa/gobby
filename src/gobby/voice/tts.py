"""Text-to-speech service using ElevenLabs streaming WebSocket API.

Manages a persistent WebSocket connection to ElevenLabs for low-latency
streaming TTS. Sends text chunks and receives audio chunks in real-time.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gobby.config.voice import VoiceConfig

logger = logging.getLogger(__name__)


@dataclass
class TTSAudioChunk:
    """A chunk of TTS audio data."""

    audio_base64: str
    is_final: bool


class ElevenLabsTTS:
    """Streaming TTS via ElevenLabs WebSocket API."""

    def __init__(self, config: VoiceConfig) -> None:
        self._config = config
        self._ws: object | None = None
        self._keepalive_task: asyncio.Task[None] | None = None
        self._connected = False

    async def connect(self) -> None:
        """Open WebSocket connection to ElevenLabs."""
        if self._connected:
            return

        try:
            import websockets

            voice_id = self._config.elevenlabs_voice_id
            model_id = self._config.elevenlabs_model_id
            url = (
                f"wss://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
                f"/stream-input?model_id={model_id}"
            )

            self._ws = await websockets.connect(url)  # type: ignore[assignment]

            # Send BOS (beginning of stream) message
            bos_message = {
                "text": " ",
                "voice_settings": {
                    "stability": 0.5,
                    "similarity_boost": 0.75,
                },
                "xi_api_key": self._config.elevenlabs_api_key,
                "output_format": self._config.audio_format,
                "chunk_length_schedule": [120, 160, 250, 290],
            }
            await self._ws.send(json.dumps(bos_message))  # type: ignore[union-attr]
            self._connected = True

            # Start keepalive to prevent 20s timeout
            self._keepalive_task = asyncio.create_task(self._keepalive_loop())

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
                        await self._ws.send(json.dumps({"text": " "}))  # type: ignore[union-attr]
                    except Exception:
                        break
        except asyncio.CancelledError:
            pass

    async def synthesize_stream(self, text: str) -> AsyncIterator[TTSAudioChunk]:
        """Send text and yield audio chunks as they arrive.

        Args:
            text: Text to synthesize.

        Yields:
            TTSAudioChunk with base64-encoded audio data.
        """
        if not self._connected or not self._ws:
            await self.connect()

        try:
            await self._ws.send(json.dumps({"text": text + " "}))  # type: ignore[union-attr]

            # Read audio chunks until we get alignment or silence
            while True:
                try:
                    response = await asyncio.wait_for(
                        self._ws.recv(),  # type: ignore[union-attr]
                        timeout=10.0,
                    )
                    data = json.loads(response)

                    if data.get("audio"):
                        yield TTSAudioChunk(
                            audio_base64=data["audio"],
                            is_final=False,
                        )

                    # Check if this is the last chunk for this text
                    if data.get("isFinal"):
                        break

                    # If we get alignment data without audio, the chunk is done
                    if "normalizedAlignment" in data and not data.get("audio"):
                        break

                except TimeoutError:
                    logger.debug("TTS receive timeout, text chunk likely complete")
                    break

        except Exception as e:
            logger.error(f"TTS synthesis error: {e}")
            self._connected = False
            raise

    async def flush(self) -> AsyncIterator[TTSAudioChunk]:
        """Send EOS and yield remaining audio chunks.

        Yields:
            Remaining TTSAudioChunk data.
        """
        if not self._connected or not self._ws:
            return

        try:
            # Send EOS (end of stream)
            await self._ws.send(json.dumps({"text": ""}))  # type: ignore[union-attr]

            while True:
                try:
                    response = await asyncio.wait_for(
                        self._ws.recv(),  # type: ignore[union-attr]
                        timeout=5.0,
                    )
                    data = json.loads(response)

                    if data.get("audio"):
                        yield TTSAudioChunk(
                            audio_base64=data["audio"],
                            is_final=data.get("isFinal", False),
                        )

                    if data.get("isFinal"):
                        break

                except TimeoutError:
                    break

        except Exception as e:
            logger.debug(f"TTS flush error (may be normal on disconnect): {e}")

    async def disconnect(self) -> None:
        """Close the WebSocket connection."""
        self._connected = False

        if self._keepalive_task and not self._keepalive_task.done():
            self._keepalive_task.cancel()
            try:
                await self._keepalive_task
            except asyncio.CancelledError:
                pass
            self._keepalive_task = None

        if self._ws:
            try:
                await self._ws.close()  # type: ignore[union-attr]
            except Exception:
                pass
            self._ws = None

        logger.debug("ElevenLabs TTS disconnected")

    @property
    def is_available(self) -> bool:
        """Check if ElevenLabs API key is configured."""
        return bool(self._config.elevenlabs_api_key)
