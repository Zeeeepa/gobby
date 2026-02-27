"""Configuration for the voice chat module."""

from __future__ import annotations

from pydantic import BaseModel, Field


class VoiceConfig(BaseModel):
    """Configuration for voice chat (STT + TTS).

    STT uses local Whisper (faster-whisper) for privacy and low latency.
    TTS uses ElevenLabs streaming WebSocket API for natural speech.

    API key fields use snake_case consistent with other config fields.
    """

    enabled: bool = Field(
        default=False,
        description="Enable voice chat features (master switch).",
    )
    stt_enabled: bool = Field(
        default=True,
        description="Enable speech-to-text (requires enabled=True).",
    )
    tts_enabled: bool = Field(
        default=False,
        description="Enable text-to-speech (requires enabled=True and ElevenLabs API key). Disabled by default.",
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
        default="eleven_flash_v2_5",
        description="ElevenLabs model ID for TTS (must support WebSocket streaming). Note: eleven_v3 does NOT support WebSocket streaming.",
    )
    elevenlabs_stability: float = Field(
        default=0.5,
        ge=0.0,
        le=1.0,
        description="ElevenLabs voice stability (0.0–1.0).",
    )
    elevenlabs_similarity_boost: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="ElevenLabs voice similarity boost (0.0–1.0).",
    )
    elevenlabs_style: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="ElevenLabs style exaggeration (0.0–1.0).",
    )
    elevenlabs_speed: float = Field(
        default=0.9,
        ge=0.5,
        le=2.0,
        description="ElevenLabs TTS speed (0.5–2.0).",
    )
    audio_format: str = Field(
        default="mp3_44100_128",
        description="Audio output format for TTS.",
    )
    whisper_prompt: str = Field(
        default="Gobby",
        description="Initial prompt for Whisper STT to bias vocabulary (e.g. proper nouns).",
    )
    whisper_vocabulary: list[str] = Field(
        default_factory=lambda: [
            # Gobby-specific
            "Gobby",
            "MCP",
            "worktree",
            # Common dev terms Whisper struggles with
            "Kubernetes",
            "PostgreSQL",
            "FastAPI",
            "Pydantic",
            "TypeScript",
            "GraphQL",
            "WebSocket",
            "Redis",
            "MongoDB",
            "SQLite",
            "OAuth",
            "JWT",
            "REST",
            "gRPC",
            "YAML",
            "JSON",
            "Docker",
            "Terraform",
            "GitHub",
            "GitLab",
            "Claude",
            "Anthropic",
            "Gemini",
            "Copilot",
            "npm",
            "pip",
            "pytest",
            "ESLint",
            "webpack",
            "Vite",
        ],
        description="Custom vocabulary terms to bias Whisper STT recognition (proper nouns, technical terms). Pre-loaded with common dev terms.",
    )
