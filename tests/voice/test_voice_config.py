"""Tests for VoiceConfig and its integration with DaemonConfig."""

from gobby.config.voice import VoiceConfig


class TestVoiceConfig:
    def test_defaults(self):
        config = VoiceConfig()
        assert config.enabled is False
        assert config.stt_enabled is True
        assert config.tts_enabled is False
        assert config.whisper_model_size == "base"
        assert config.whisper_device == "auto"
        assert config.whisper_compute_type == "int8"
        assert config.elevenlabs_api_key == ""
        assert config.elevenlabs_voice_id == "21m00Tcm4TlvDq8ikWAM"
        assert config.elevenlabs_model_id == "eleven_flash_v2_5"
        assert config.audio_format == "mp3_44100_128"

    def test_custom_values(self):
        config = VoiceConfig(
            enabled=True,
            whisper_model_size="small",
            elevenlabs_api_key="test-key",
        )
        assert config.enabled is True
        assert config.whisper_model_size == "small"
        assert config.elevenlabs_api_key == "test-key"

    def test_stt_only(self):
        config = VoiceConfig(enabled=True, stt_enabled=True, tts_enabled=False)
        assert config.enabled is True
        assert config.stt_enabled is True
        assert config.tts_enabled is False

    def test_tts_only(self):
        config = VoiceConfig(enabled=True, stt_enabled=False, tts_enabled=True)
        assert config.enabled is True
        assert config.stt_enabled is False
        assert config.tts_enabled is True

    def test_daemon_config_integration(self):
        from gobby.config.app import DaemonConfig

        config = DaemonConfig()
        assert hasattr(config, "voice")
        assert isinstance(config.voice, VoiceConfig)
        assert config.voice.enabled is False

    def test_daemon_config_with_voice(self):
        from gobby.config.app import DaemonConfig

        config = DaemonConfig(voice={"enabled": True, "whisper_model_size": "medium"})
        assert config.voice.enabled is True
        assert config.voice.whisper_model_size == "medium"
