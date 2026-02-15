"""Tests for voice API routes with real config objects."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from gobby.config.voice import VoiceConfig
from gobby.servers.routes.voice import create_voice_router

pytestmark = pytest.mark.unit


class TestVoiceRoutes:
    """Tests for voice endpoints using real VoiceConfig objects."""

    @pytest.fixture
    def voice_config(self) -> VoiceConfig:
        """Create a real VoiceConfig with defaults."""
        return VoiceConfig()

    @pytest.fixture
    def server_with_voice(self, voice_config: VoiceConfig) -> MagicMock:
        """Server with real VoiceConfig attached."""
        server = MagicMock()
        config = MagicMock()
        config.voice = voice_config
        server.config = config
        return server

    @pytest.fixture
    def client(self, server_with_voice: MagicMock) -> TestClient:
        app = FastAPI()
        router = create_voice_router(server_with_voice)
        app.include_router(router)
        return TestClient(app)

    # -----------------------------------------------------------------
    # GET /api/voice/status
    # -----------------------------------------------------------------

    def test_status_voice_disabled_by_default(self, client: TestClient) -> None:
        """VoiceConfig defaults: enabled=False, no API key."""
        response = client.get("/api/voice/status")
        assert response.status_code == 200
        data = response.json()
        assert data["enabled"] is False
        assert data["stt_available"] is False
        assert data["stt_reason"] == "Voice not enabled in config"
        assert data["tts_available"] is False
        assert data["tts_reason"] == "No ElevenLabs API key configured"
        assert data["whisper_model"] == "base"
        assert data["audio_format"] == "mp3_44100_128"

    def test_status_no_config(self, client: TestClient, server_with_voice: MagicMock) -> None:
        """When server.config is None."""
        server_with_voice.config = None
        response = client.get("/api/voice/status")
        data = response.json()
        assert data["enabled"] is False
        assert data["stt_available"] is False
        assert data["tts_available"] is False
        assert data["reason"] == "Voice config not found"

    def test_status_no_voice_attr(self, client: TestClient, server_with_voice: MagicMock) -> None:
        """When config exists but has no voice attribute."""
        # Remove the voice attribute from config
        config_obj = MagicMock(spec=[])  # spec=[] means no attributes
        server_with_voice.config = config_obj
        response = client.get("/api/voice/status")
        data = response.json()
        assert data["enabled"] is False
        assert data["reason"] == "Voice config not found"

    def test_status_voice_enabled_no_whisper(
        self, client: TestClient, server_with_voice: MagicMock
    ) -> None:
        """Voice enabled but faster-whisper not installed."""
        server_with_voice.config.voice = VoiceConfig(enabled=True)
        with patch.dict("sys.modules", {"faster_whisper": None}):
            response = client.get("/api/voice/status")
        data = response.json()
        assert data["enabled"] is True
        assert data["stt_available"] is False
        assert "faster-whisper" in data["stt_reason"]

    def test_status_voice_enabled_with_whisper(
        self, client: TestClient, server_with_voice: MagicMock
    ) -> None:
        """Voice enabled and faster-whisper is available."""
        server_with_voice.config.voice = VoiceConfig(enabled=True)
        mock_whisper = MagicMock()
        with patch.dict("sys.modules", {"faster_whisper": mock_whisper}):
            response = client.get("/api/voice/status")
        data = response.json()
        assert data["enabled"] is True
        assert data["stt_available"] is True
        assert data["stt_reason"] == ""

    def test_status_tts_with_api_key(
        self, client: TestClient, server_with_voice: MagicMock
    ) -> None:
        """TTS available when ElevenLabs API key is configured."""
        server_with_voice.config.voice = VoiceConfig(enabled=True, elevenlabs_api_key="sk-test-key")
        response = client.get("/api/voice/status")
        data = response.json()
        assert data["tts_available"] is True
        assert data["tts_reason"] == ""

    def test_status_tts_without_api_key(
        self, client: TestClient, server_with_voice: MagicMock
    ) -> None:
        """TTS unavailable when no API key."""
        server_with_voice.config.voice = VoiceConfig(enabled=True, elevenlabs_api_key="")
        response = client.get("/api/voice/status")
        data = response.json()
        assert data["tts_available"] is False
        assert data["tts_reason"] == "No ElevenLabs API key configured"

    def test_status_custom_whisper_model(
        self, client: TestClient, server_with_voice: MagicMock
    ) -> None:
        """Custom whisper model size is reflected in status."""
        server_with_voice.config.voice = VoiceConfig(enabled=False, whisper_model_size="small")
        response = client.get("/api/voice/status")
        data = response.json()
        assert data["whisper_model"] == "small"

    def test_status_custom_voice_id(self, client: TestClient, server_with_voice: MagicMock) -> None:
        """Custom ElevenLabs voice ID is reflected in status."""
        server_with_voice.config.voice = VoiceConfig(
            enabled=False, elevenlabs_voice_id="custom-voice-42"
        )
        response = client.get("/api/voice/status")
        data = response.json()
        assert data["tts_voice_id"] == "custom-voice-42"

    # -----------------------------------------------------------------
    # POST /api/voice/transcribe
    # -----------------------------------------------------------------

    def test_transcribe_voice_disabled(self, client: TestClient) -> None:
        """Transcribe returns error when voice is disabled."""
        response = client.post(
            "/api/voice/transcribe",
            files={"file": ("test.webm", b"fake audio data", "audio/webm")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["error"] == "Voice not enabled"
        assert data["text"] == ""

    def test_transcribe_no_config(self, client: TestClient, server_with_voice: MagicMock) -> None:
        """Transcribe returns error when config is None."""
        server_with_voice.config = None
        response = client.post(
            "/api/voice/transcribe",
            files={"file": ("test.webm", b"fake audio data", "audio/webm")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["error"] == "Voice not enabled"
        assert data["text"] == ""

    def test_transcribe_no_voice_attr(
        self, client: TestClient, server_with_voice: MagicMock
    ) -> None:
        """Transcribe returns error when config has no voice attribute."""
        config_obj = MagicMock(spec=[])
        server_with_voice.config = config_obj
        response = client.post(
            "/api/voice/transcribe",
            files={"file": ("test.webm", b"audio", "audio/webm")},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["error"] == "Voice not enabled"

    def test_transcribe_stt_not_available(
        self, client: TestClient, server_with_voice: MagicMock
    ) -> None:
        """Transcribe returns error when STT is not available."""
        server_with_voice.config.voice = VoiceConfig(enabled=True)
        mock_stt = MagicMock()
        mock_stt.return_value.is_available = False

        with patch("gobby.voice.stt.WhisperSTT", mock_stt):
            response = client.post(
                "/api/voice/transcribe",
                files={"file": ("test.webm", b"audio data", "audio/webm")},
            )
        assert response.status_code == 200
        data = response.json()
        assert "faster-whisper" in data["error"]
        assert data["text"] == ""

    def test_transcribe_success(self, client: TestClient, server_with_voice: MagicMock) -> None:
        """Successful transcription returns text and metadata."""
        server_with_voice.config.voice = VoiceConfig(enabled=True)
        mock_stt_instance = MagicMock()
        mock_stt_instance.is_available = True
        mock_stt_instance.transcribe = AsyncMock(return_value="Hello world")
        mock_stt_cls = MagicMock(return_value=mock_stt_instance)

        with patch("gobby.voice.stt.WhisperSTT", mock_stt_cls):
            response = client.post(
                "/api/voice/transcribe",
                files={"file": ("test.webm", b"audio data here", "audio/webm")},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "Hello world"
        assert data["bytes"] == len(b"audio data here")
        assert data["content_type"] == "audio/webm"

    def test_transcribe_default_content_type(
        self, client: TestClient, server_with_voice: MagicMock
    ) -> None:
        """When no content_type is provided, defaults to audio/webm."""
        server_with_voice.config.voice = VoiceConfig(enabled=True)
        mock_stt_instance = MagicMock()
        mock_stt_instance.is_available = True
        mock_stt_instance.transcribe = AsyncMock(return_value="Transcribed text")
        mock_stt_cls = MagicMock(return_value=mock_stt_instance)

        with patch("gobby.voice.stt.WhisperSTT", mock_stt_cls):
            # Send without explicit content_type
            response = client.post(
                "/api/voice/transcribe",
                files={"file": ("test.wav", b"wav data")},
            )
        assert response.status_code == 200
        data = response.json()
        assert data["text"] == "Transcribed text"

    def test_transcribe_error_during_transcription(
        self, client: TestClient, server_with_voice: MagicMock
    ) -> None:
        """Transcription error is caught and returned."""
        server_with_voice.config.voice = VoiceConfig(enabled=True)
        mock_stt_instance = MagicMock()
        mock_stt_instance.is_available = True
        mock_stt_instance.transcribe = AsyncMock(side_effect=RuntimeError("Model crashed"))
        mock_stt_cls = MagicMock(return_value=mock_stt_instance)

        with patch("gobby.voice.stt.WhisperSTT", mock_stt_cls):
            response = client.post(
                "/api/voice/transcribe",
                files={"file": ("test.webm", b"audio", "audio/webm")},
            )
        assert response.status_code == 200
        data = response.json()
        assert "Model crashed" in data["error"]
        assert data["text"] == ""
