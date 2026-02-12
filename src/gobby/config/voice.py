"""Configuration for the voice chat module."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VoiceConfig(BaseModel):
    """Configuration for voice chat (STT + TTS).

    STT uses local Whisper (faster-whisper) for privacy and low latency.
    TTS uses ElevenLabs streaming WebSocket API for natural speech.
    """

    enabled: bool = Field(
        default=False,
        description="Enable voice chat features (STT + TTS).",
    )
    whisper_model_size: str = Field(
        default="base",
        description="Whisper model size: tiny, base, small, medium.",
    )
    whisper_device: str = Field(
        default="auto",
        description="Device for Whisper inference: auto, cpu, cuda.",
    )
    whisper_compute_type: str = Field(
        default="int8",
        description="Compute type for Whisper: int8, float16, float32.",
    )
    elevenlabs_api_key: str = Field(
        default="",
        description="ElevenLabs API key. Supports ${ELEVENLABS_API_KEY} env var expansion.",
    )
    elevenlabs_voice_id: str = Field(
        default="21m00Tcm4TlvDq8ikWAM",
        description="ElevenLabs voice ID (default: Rachel).",
    )
    elevenlabs_model_id: str = Field(
        default="eleven_turbo_v2_5",
        description="ElevenLabs model ID for TTS.",
    )
    audio_format: str = Field(
        default="mp3_44100_128",
        description="Audio output format for TTS.",
    )
