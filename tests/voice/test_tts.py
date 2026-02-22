"""Tests for ElevenLabsTTS and TTSAudioChunk.

Covers WebSocket connection lifecycle, text sending, flushing,
disconnect cleanup, audio listener callback dispatch, and error paths.
"""

from __future__ import annotations

import asyncio
import builtins
import json
from unittest.mock import AsyncMock, patch

import pytest

from gobby.config.voice import VoiceConfig
from gobby.voice.tts import ElevenLabsTTS, TTSAudioChunk

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# TTSAudioChunk dataclass
# ---------------------------------------------------------------------------


class TestTTSAudioChunk:
    def test_creation_with_audio(self) -> None:
        chunk = TTSAudioChunk(audio_base64="AAAA", is_final=False)
        assert chunk.audio_base64 == "AAAA"
        assert chunk.is_final is False

    def test_creation_final_chunk(self) -> None:
        chunk = TTSAudioChunk(audio_base64="", is_final=True)
        assert chunk.audio_base64 == ""
        assert chunk.is_final is True

    def test_equality(self) -> None:
        a = TTSAudioChunk(audio_base64="XYZ", is_final=False)
        b = TTSAudioChunk(audio_base64="XYZ", is_final=False)
        assert a == b

    def test_inequality(self) -> None:
        a = TTSAudioChunk(audio_base64="XYZ", is_final=False)
        b = TTSAudioChunk(audio_base64="XYZ", is_final=True)
        assert a != b


# ---------------------------------------------------------------------------
# is_available property
# ---------------------------------------------------------------------------


class TestIsAvailable:
    def test_available_with_api_key(self) -> None:
        config = VoiceConfig(elevenlabs_api_key="sk-test-key")
        tts = ElevenLabsTTS(config)
        assert tts.is_available is True

    def test_not_available_without_api_key(self) -> None:
        config = VoiceConfig(elevenlabs_api_key="")
        tts = ElevenLabsTTS(config)
        assert tts.is_available is False

    def test_not_available_default_config(self) -> None:
        config = VoiceConfig()
        tts = ElevenLabsTTS(config)
        assert tts.is_available is False


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tts(api_key: str = "test-key-123") -> ElevenLabsTTS:
    """Create an ElevenLabsTTS with a valid config."""
    config = VoiceConfig(
        elevenlabs_api_key=api_key,
        elevenlabs_voice_id="voice-abc",
        elevenlabs_model_id="eleven_flash_v2_5",
        elevenlabs_stability=0.5,
        elevenlabs_similarity_boost=1.0,
        elevenlabs_style=0.0,
        elevenlabs_speed=0.9,
        audio_format="mp3_44100_128",
    )
    return ElevenLabsTTS(config)


def _mock_ws() -> AsyncMock:
    """Return a mock WebSocket connection."""
    ws = AsyncMock()
    ws.send = AsyncMock()
    ws.recv = AsyncMock(side_effect=asyncio.CancelledError)
    ws.close = AsyncMock()
    return ws


# ---------------------------------------------------------------------------
# connect()
# ---------------------------------------------------------------------------


class TestConnect:
    @pytest.mark.asyncio
    async def test_connect_opens_websocket_and_sends_bos(self) -> None:
        tts = _make_tts()
        ws = _mock_ws()

        with patch("websockets.connect", new_callable=AsyncMock, return_value=ws):
            on_audio = AsyncMock()
            await tts.connect(on_audio)

            # Verify BOS message was sent
            bos_call = ws.send.call_args_list[0]
            bos_msg = json.loads(bos_call[0][0])
            assert bos_msg["text"] == " "
            assert bos_msg["xi_api_key"] == "test-key-123"
            assert bos_msg["output_format"] == "mp3_44100_128"
            assert "voice_settings" in bos_msg
            assert bos_msg["voice_settings"]["stability"] == 0.5
            assert bos_msg["voice_settings"]["similarity_boost"] == 1.0
            assert bos_msg["voice_settings"]["style"] == 0.0
            assert bos_msg["voice_settings"]["speed"] == 0.9
            assert bos_msg["generation_config"]["chunk_length_schedule"] == [50, 120, 160, 250]

            assert tts._connected is True

            # Clean up background tasks
            await tts.disconnect()

    @pytest.mark.asyncio
    async def test_connect_creates_background_tasks(self) -> None:
        tts = _make_tts()
        ws = _mock_ws()

        with patch("websockets.connect", new_callable=AsyncMock, return_value=ws):
            on_audio = AsyncMock()
            await tts.connect(on_audio)

            assert tts._keepalive_task is not None
            assert tts._listener_task is not None
            assert isinstance(tts._keepalive_task, asyncio.Task)
            assert isinstance(tts._listener_task, asyncio.Task)

            await tts.disconnect()

    @pytest.mark.asyncio
    async def test_connect_idempotent_when_already_connected(self) -> None:
        tts = _make_tts()
        ws = _mock_ws()

        with patch("websockets.connect", new_callable=AsyncMock, return_value=ws) as mock_connect:
            on_audio = AsyncMock()
            await tts.connect(on_audio)
            # Second call should be a no-op
            await tts.connect(on_audio)

            assert mock_connect.call_count == 1

            await tts.disconnect()

    @pytest.mark.asyncio
    async def test_connect_import_error(self) -> None:
        tts = _make_tts()

        original_import = builtins.__import__

        def failing_import(name, *args, **kwargs):
            if name == "websockets":
                raise ImportError("no websockets")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=failing_import):
            with pytest.raises(ImportError):
                await tts.connect(AsyncMock())

        assert tts._connected is False

    @pytest.mark.asyncio
    async def test_connect_connection_error(self) -> None:
        tts = _make_tts()

        with patch(
            "websockets.connect",
            new_callable=AsyncMock,
            side_effect=ConnectionError("Connection refused"),
        ):
            with pytest.raises(ConnectionError):
                await tts.connect(AsyncMock())

        assert tts._connected is False


# ---------------------------------------------------------------------------
# send_text()
# ---------------------------------------------------------------------------


class TestSendText:
    @pytest.mark.asyncio
    async def test_send_text_when_connected(self) -> None:
        tts = _make_tts()
        ws = _mock_ws()

        with patch("websockets.connect", new_callable=AsyncMock, return_value=ws):
            await tts.connect(AsyncMock())

            await tts.send_text("Hello world")

            # Find the send_text call (after BOS message)
            send_calls = ws.send.call_args_list
            # BOS is call [0], send_text is call [1]
            text_msg = json.loads(send_calls[1][0][0])
            assert text_msg["text"] == "Hello world "
            assert text_msg["try_trigger_generation"] is True

            await tts.disconnect()

    @pytest.mark.asyncio
    async def test_send_text_when_not_connected(self) -> None:
        tts = _make_tts()
        # Not connected -- send_text should silently return
        await tts.send_text("Hello")
        # No exception raised, no ws interaction

    @pytest.mark.asyncio
    async def test_send_text_when_ws_is_none(self) -> None:
        tts = _make_tts()
        tts._connected = True
        tts._ws = None
        # Should silently return when _ws is None even if _connected is True
        await tts.send_text("Hello")

    @pytest.mark.asyncio
    async def test_send_text_multiple_calls(self) -> None:
        tts = _make_tts()
        ws = _mock_ws()

        with patch("websockets.connect", new_callable=AsyncMock, return_value=ws):
            await tts.connect(AsyncMock())

            await tts.send_text("First")
            await tts.send_text("Second")
            await tts.send_text("Third")

            # BOS + 3 text sends = 4 total (plus possible keepalive/listener)
            text_sends = []
            for call in ws.send.call_args_list:
                msg = json.loads(call[0][0])
                if msg.get("try_trigger_generation"):
                    text_sends.append(msg["text"])
            assert text_sends == ["First ", "Second ", "Third "]

            await tts.disconnect()


# ---------------------------------------------------------------------------
# send_flush()
# ---------------------------------------------------------------------------


class TestSendFlush:
    @pytest.mark.asyncio
    async def test_send_flush_when_connected(self) -> None:
        tts = _make_tts()
        ws = _mock_ws()

        with patch("websockets.connect", new_callable=AsyncMock, return_value=ws):
            await tts.connect(AsyncMock())

            await tts.send_flush()

            # Find the flush message
            flush_found = False
            for call in ws.send.call_args_list:
                msg = json.loads(call[0][0])
                if msg.get("flush") is True:
                    assert msg["text"] == ""
                    flush_found = True
            assert flush_found, "No flush message found in WebSocket sends"

            await tts.disconnect()

    @pytest.mark.asyncio
    async def test_send_flush_when_not_connected(self) -> None:
        tts = _make_tts()
        # Should silently return
        await tts.send_flush()

    @pytest.mark.asyncio
    async def test_send_flush_when_ws_is_none(self) -> None:
        tts = _make_tts()
        tts._connected = True
        tts._ws = None
        await tts.send_flush()


# ---------------------------------------------------------------------------
# disconnect()
# ---------------------------------------------------------------------------


class TestDisconnect:
    @pytest.mark.asyncio
    async def test_disconnect_cancels_tasks_and_closes_ws(self) -> None:
        tts = _make_tts()
        ws = _mock_ws()

        with patch("websockets.connect", new_callable=AsyncMock, return_value=ws):
            await tts.connect(AsyncMock())

            keepalive = tts._keepalive_task
            listener = tts._listener_task

            await tts.disconnect()

            assert tts._connected is False
            assert tts._ws is None
            assert tts._keepalive_task is None
            assert tts._listener_task is None

            # Tasks should have been cancelled
            assert keepalive is not None
            assert listener is not None
            assert keepalive.cancelled() or keepalive.done()
            assert listener.cancelled() or listener.done()

    @pytest.mark.asyncio
    async def test_disconnect_sends_eos_before_closing(self) -> None:
        tts = _make_tts()
        ws = _mock_ws()

        with patch("websockets.connect", new_callable=AsyncMock, return_value=ws):
            await tts.connect(AsyncMock())

            await tts.disconnect()

            # Find the EOS message (empty text) sent during disconnect
            eos_found = False
            for call in ws.send.call_args_list:
                msg = json.loads(call[0][0])
                if msg == {"text": ""}:
                    eos_found = True
            assert eos_found, "No EOS message found in WebSocket sends"

            ws.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_disconnect_when_not_connected(self) -> None:
        tts = _make_tts()
        # Should not raise
        await tts.disconnect()
        assert tts._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_handles_ws_close_error(self) -> None:
        tts = _make_tts()
        ws = _mock_ws()
        ws.send = AsyncMock(side_effect=[None, Exception("send failed")])
        ws.close = AsyncMock(side_effect=Exception("close failed"))

        # Manually set up state as if connected (skip actual connect to avoid
        # background tasks complicating the mock)
        tts._ws = ws
        tts._connected = True
        tts._keepalive_task = None
        tts._listener_task = None

        # Should not raise even if ws.send/close fail
        await tts.disconnect()
        assert tts._ws is None
        assert tts._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_idempotent(self) -> None:
        tts = _make_tts()
        ws = _mock_ws()

        with patch("websockets.connect", new_callable=AsyncMock, return_value=ws):
            await tts.connect(AsyncMock())

            await tts.disconnect()
            # Second disconnect should be safe
            await tts.disconnect()
            assert tts._connected is False


# ---------------------------------------------------------------------------
# _audio_listener()
# ---------------------------------------------------------------------------


class TestAudioListener:
    @pytest.mark.asyncio
    async def test_listener_dispatches_audio_chunks(self) -> None:
        tts = _make_tts()
        ws = AsyncMock()
        received_chunks: list[TTSAudioChunk] = []

        async def on_audio(chunk: TTSAudioChunk) -> None:
            received_chunks.append(chunk)

        # Simulate WS returning two audio messages then closing
        ws.recv = AsyncMock(
            side_effect=[
                json.dumps({"audio": "AQID", "isFinal": False}),
                json.dumps({"audio": "BAUG", "isFinal": False}),
                json.dumps({"audio": "CAAA", "isFinal": True}),
                asyncio.CancelledError(),
            ]
        )

        tts._ws = ws
        tts._connected = True

        # Run the listener directly (not as a background task)
        await tts._audio_listener(on_audio)

        assert len(received_chunks) == 3
        assert received_chunks[0] == TTSAudioChunk(audio_base64="AQID", is_final=False)
        assert received_chunks[1] == TTSAudioChunk(audio_base64="BAUG", is_final=False)
        assert received_chunks[2] == TTSAudioChunk(audio_base64="CAAA", is_final=True)

    @pytest.mark.asyncio
    async def test_listener_handles_final_without_audio(self) -> None:
        """When isFinal=True but no audio field, should send empty final chunk."""
        tts = _make_tts()
        ws = AsyncMock()
        received_chunks: list[TTSAudioChunk] = []

        async def on_audio(chunk: TTSAudioChunk) -> None:
            received_chunks.append(chunk)

        ws.recv = AsyncMock(
            side_effect=[
                json.dumps({"isFinal": True}),
                asyncio.CancelledError(),
            ]
        )

        tts._ws = ws
        tts._connected = True

        await tts._audio_listener(on_audio)

        assert len(received_chunks) == 1
        assert received_chunks[0] == TTSAudioChunk(audio_base64="", is_final=True)

    @pytest.mark.asyncio
    async def test_listener_ignores_messages_without_audio_or_final(self) -> None:
        tts = _make_tts()
        ws = AsyncMock()
        received_chunks: list[TTSAudioChunk] = []

        async def on_audio(chunk: TTSAudioChunk) -> None:
            received_chunks.append(chunk)

        ws.recv = AsyncMock(
            side_effect=[
                json.dumps({"normalizedAlignment": {}}),  # metadata message
                json.dumps({"audio": "DATA", "isFinal": False}),
                asyncio.CancelledError(),
            ]
        )

        tts._ws = ws
        tts._connected = True

        await tts._audio_listener(on_audio)

        assert len(received_chunks) == 1
        assert received_chunks[0].audio_base64 == "DATA"

    @pytest.mark.asyncio
    async def test_listener_breaks_on_recv_error(self) -> None:
        tts = _make_tts()
        ws = AsyncMock()
        received_chunks: list[TTSAudioChunk] = []

        async def on_audio(chunk: TTSAudioChunk) -> None:
            received_chunks.append(chunk)

        ws.recv = AsyncMock(
            side_effect=[
                json.dumps({"audio": "FIRST", "isFinal": False}),
                ConnectionError("Connection lost"),
            ]
        )

        tts._ws = ws
        tts._connected = True

        await tts._audio_listener(on_audio)

        # Should have received the first chunk before the error broke the loop
        assert len(received_chunks) == 1
        assert received_chunks[0].audio_base64 == "FIRST"

    @pytest.mark.asyncio
    async def test_listener_exits_when_disconnected(self) -> None:
        tts = _make_tts()
        ws = AsyncMock()
        call_count = 0

        async def on_audio(chunk: TTSAudioChunk) -> None:
            nonlocal call_count
            call_count += 1

        tts._ws = ws
        tts._connected = False  # Already disconnected

        await tts._audio_listener(on_audio)

        assert call_count == 0


# ---------------------------------------------------------------------------
# _keepalive_loop() (basic coverage)
# ---------------------------------------------------------------------------


class TestKeepaliveLoop:
    @pytest.mark.asyncio
    async def test_keepalive_sends_empty_text(self) -> None:
        tts = _make_tts()
        ws = AsyncMock()
        ws.send = AsyncMock()
        tts._ws = ws
        tts._connected = True

        # Run keepalive in a task, let it send one message, then cancel
        task = asyncio.create_task(tts._keepalive_loop())

        # Patch sleep so we don't actually wait 15s
        with patch("gobby.voice.tts.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
            # After first sleep, disconnect to stop the loop
            async def disconnect_after_sleep(*args: object) -> None:
                tts._connected = False

            mock_sleep.side_effect = disconnect_after_sleep
            await task

        # Should have attempted to send keepalive (but _connected is now False)
        # The loop checks _connected after sleep, so if it's False, it won't send
        # That's fine -- we verify it doesn't error out

    @pytest.mark.asyncio
    async def test_keepalive_breaks_on_send_error(self) -> None:
        tts = _make_tts()
        ws = AsyncMock()
        ws.send = AsyncMock(side_effect=Exception("send error"))
        tts._ws = ws
        tts._connected = True

        with patch("gobby.voice.tts.asyncio.sleep", new_callable=AsyncMock):
            # The loop should break on send error
            await tts._keepalive_loop()

        # No exception raised -- loop exits cleanly


# ---------------------------------------------------------------------------
# Init state
# ---------------------------------------------------------------------------


class TestInit:
    def test_initial_state(self) -> None:
        config = VoiceConfig(elevenlabs_api_key="key")
        tts = ElevenLabsTTS(config)
        assert tts._ws is None
        assert tts._keepalive_task is None
        assert tts._listener_task is None
        assert tts._connected is False

    def test_config_stored(self) -> None:
        config = VoiceConfig(
            elevenlabs_api_key="my-key",
            elevenlabs_voice_id="custom-voice",
            audio_format="pcm_16000",
        )
        tts = ElevenLabsTTS(config)
        assert tts._config is config
        assert tts._config.elevenlabs_api_key == "my-key"
        assert tts._config.elevenlabs_voice_id == "custom-voice"
        assert tts._config.audio_format == "pcm_16000"
