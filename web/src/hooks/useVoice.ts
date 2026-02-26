import { useState, useCallback, useRef, useEffect } from 'react'
import { MicVAD, utils } from '@ricky0123/vad-web'
import { SentenceBuffer } from '../utils/sentenceBuffer'

interface VoiceState {
  voiceMode: boolean
  voiceAvailable: boolean
  isListening: boolean
  isSpeechDetected: boolean
  isTranscribing: boolean
  isSpeaking: boolean
  voiceError: string | null
}

interface TTSConfig {
  api_key: string
  voice_id: string
  model_id: string
  stability: number
  similarity_boost: number
  style: number
  speed: number
  output_format: string
}

/** Sequential audio playback queue using HTMLAudioElement (iOS Safari compatible). */
class AudioPlaybackQueue {
  private queue: string[] = []
  private playing = false
  private currentAudio: HTMLAudioElement | null = null
  onPlayingChange: ((playing: boolean) => void) | null = null

  enqueue(audioBase64: string, format: string) {
    // Convert base64 to blob URL
    const mimeMap: Record<string, string> = {
      'mp3_44100_128': 'audio/mpeg',
      'mp3_22050_32': 'audio/mpeg',
      'pcm_16000': 'audio/wav',
      'ulaw_8000': 'audio/basic',
    }
    const mime = mimeMap[format] || 'audio/mpeg'
    const binary = atob(audioBase64)
    const bytes = new Uint8Array(binary.length)
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i)
    }
    const blob = new Blob([bytes], { type: mime })
    const url = URL.createObjectURL(blob)
    this.queue.push(url)
    this.playNext()
    this.onPlayingChange?.(this.isPlaying)
  }

  private playNext() {
    if (this.playing || this.queue.length === 0) return
    this.playing = true
    const url = this.queue.shift()!
    const audio = new Audio(url)
    this.currentAudio = audio

    audio.onended = () => {
      URL.revokeObjectURL(url)
      this.playing = false
      this.currentAudio = null
      this.playNext()
      this.onPlayingChange?.(this.isPlaying)
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      this.playing = false
      this.currentAudio = null
      this.playNext()
      this.onPlayingChange?.(this.isPlaying)
    }
    audio.play().catch(() => {
      URL.revokeObjectURL(url)
      this.playing = false
      this.currentAudio = null
      this.playNext()
      this.onPlayingChange?.(this.isPlaying)
    })
  }

  stop() {
    if (this.currentAudio) {
      this.currentAudio.pause()
      this.currentAudio = null
    }
    // Revoke remaining URLs
    for (const url of this.queue) {
      URL.revokeObjectURL(url)
    }
    this.queue = []
    this.playing = false
    this.onPlayingChange?.(false)
  }

  get isPlaying() {
    return this.playing || this.queue.length > 0
  }
}

export interface UseVoiceReturn extends VoiceState {
  toggleVoiceMode: () => void
  stopSpeaking: () => void
  handleVoiceMessage: (data: Record<string, unknown>) => void
  feedTTSText: (text: string) => void
  flushTTS: () => void
}

export function useVoice(
  wsRef: React.RefObject<WebSocket | null>,
  conversationId: string,
): UseVoiceReturn {
  const [voiceMode, setVoiceMode] = useState(false)
  const [voiceAvailable, setVoiceAvailable] = useState(false)
  const [isListening, setIsListening] = useState(false)
  const [isSpeechDetected, setIsSpeechDetected] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [voiceError, setVoiceError] = useState<string | null>(null)

  const vadRef = useRef<MicVAD | null>(null)
  const playbackQueueRef = useRef(new AudioPlaybackQueue())

  // Stable ref for conversationId so long-lived callbacks (e.g. VAD onSpeechEnd)
  // always see the latest value without re-subscribing.
  const conversationIdRef = useRef(conversationId)
  conversationIdRef.current = conversationId

  // TTS WebSocket state
  const ttsWsRef = useRef<WebSocket | null>(null)
  const ttsConfigRef = useRef<TTSConfig | null>(null)
  const sentenceBufferRef = useRef(new SentenceBuffer())
  const ttsKeepaliveRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const ttsReconnectRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const voiceModeRef = useRef(false)

  // Check voice availability on mount (STT availability via /api/voice/status)
  useEffect(() => {
    // getUserMedia requires a secure context (HTTPS or localhost).
    // On plain HTTP (e.g. Tailscale IP), navigator.mediaDevices is undefined.
    if (!window.isSecureContext) {
      console.warn('Voice: disabled — requires secure context (HTTPS or localhost)')
      setVoiceAvailable(false)
      return
    }

    fetch('/api/voice/status')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.enabled && data?.stt_available) {
          setVoiceAvailable(true)
        }
      })
      .catch((err) => { console.error('Voice status check failed:', err); setVoiceAvailable(false) })
  }, [])

  /** Connect to ElevenLabs WebSocket for TTS streaming. */
  const connectTTS = useCallback((config: TTSConfig) => {
    // Close existing connection
    if (ttsWsRef.current) {
      ttsWsRef.current.close()
      ttsWsRef.current = null
    }
    if (ttsKeepaliveRef.current) {
      clearInterval(ttsKeepaliveRef.current)
      ttsKeepaliveRef.current = null
    }

    const url = `wss://api.elevenlabs.io/v1/text-to-speech/${config.voice_id}/stream-input?model_id=${config.model_id}`
    const ws = new WebSocket(url)
    ttsWsRef.current = ws

    ws.onopen = () => {
      // Send Beginning-of-Stream (BOS) message
      ws.send(JSON.stringify({
        text: ' ',
        xi_api_key: config.api_key,
        voice_settings: {
          stability: config.stability,
          similarity_boost: config.similarity_boost,
          style: config.style,
          speed: config.speed,
        },
        output_format: config.output_format,
        generation_config: { chunk_length_schedule: [50, 120, 160, 250] },
      }))

      // Keepalive: send a space every 15s to prevent idle disconnect
      ttsKeepaliveRef.current = setInterval(() => {
        if (ws.readyState === WebSocket.OPEN) {
          ws.send(JSON.stringify({ text: ' ' }))
        }
      }, 15000)
    }

    ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.audio) {
          playbackQueueRef.current.enqueue(data.audio, config.output_format)
        }
      } catch {
        // Ignore unparseable messages
      }
    }

    ws.onclose = () => {
      if (ttsKeepaliveRef.current) {
        clearInterval(ttsKeepaliveRef.current)
        ttsKeepaliveRef.current = null
      }
      ttsWsRef.current = null

      // Auto-reconnect if voice mode is still on
      if (voiceModeRef.current && ttsConfigRef.current) {
        if (ttsReconnectRef.current) clearTimeout(ttsReconnectRef.current)
        ttsReconnectRef.current = setTimeout(() => {
          ttsReconnectRef.current = null
          if (voiceModeRef.current && ttsConfigRef.current) {
            connectTTS(ttsConfigRef.current)
          }
        }, 1000)
      }
    }

    ws.onerror = (err) => {
      console.error('TTS WebSocket error:', err)
    }
  }, [])

  /** Disconnect ElevenLabs TTS WebSocket. */
  const disconnectTTS = useCallback(() => {
    sentenceBufferRef.current.clear()
    if (ttsKeepaliveRef.current) {
      clearInterval(ttsKeepaliveRef.current)
      ttsKeepaliveRef.current = null
    }
    if (ttsReconnectRef.current) {
      clearTimeout(ttsReconnectRef.current)
      ttsReconnectRef.current = null
    }
    if (ttsWsRef.current) {
      // Send End-of-Stream (EOS) message
      if (ttsWsRef.current.readyState === WebSocket.OPEN) {
        ttsWsRef.current.send(JSON.stringify({ text: '' }))
      }
      ttsWsRef.current.close()
      ttsWsRef.current = null
    }
    ttsConfigRef.current = null
  }, [])

  // Track speaking state from playback queue and pause/resume VAD to prevent echo.
  // Uses a debounced resume so VAD doesn't restart between streaming chunks or while
  // speaker audio is still reverberating.
  const resumeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  useEffect(() => {
    if (!voiceMode) return
    const queue = playbackQueueRef.current
    let wasPlaying = false

    queue.onPlayingChange = (playing) => {
      setIsSpeaking(playing)

      if (playing && !wasPlaying && vadRef.current) {
        // Cancel any pending resume — more audio arrived
        if (resumeTimerRef.current) {
          clearTimeout(resumeTimerRef.current)
          resumeTimerRef.current = null
        }
        vadRef.current.pause()
        setIsListening(false)
      } else if (!playing && wasPlaying) {
        // Debounce resume: wait for silence before restarting VAD.
        // This covers the gap between streaming chunks AND lets speaker
        // audio dissipate after TTS finishes.
        if (resumeTimerRef.current) clearTimeout(resumeTimerRef.current)
        resumeTimerRef.current = setTimeout(() => {
          resumeTimerRef.current = null
          if (vadRef.current && !queue.isPlaying) {
            vadRef.current.start()
            setIsListening(true)
          }
        }, 600)
      }
      wasPlaying = playing
    }
    return () => {
      queue.onPlayingChange = null
      if (resumeTimerRef.current) {
        clearTimeout(resumeTimerRef.current)
        resumeTimerRef.current = null
      }
    }
  }, [voiceMode])

  const toggleVoiceMode = useCallback(async () => {
    const newMode = !voiceMode
    setVoiceError(null)

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'voice_mode_toggle',
        conversation_id: conversationId,
        enabled: newMode,
      }))
    }

    if (newMode) {
      // Enable: create VAD, start listening, and connect TTS
      try {
        const vad = await MicVAD.new({
          baseAssetPath: '/',
          onnxWASMBasePath: 'https://cdn.jsdelivr.net/npm/onnxruntime-web@1.24.1/dist/',
          positiveSpeechThreshold: 0.85,
          negativeSpeechThreshold: 0.5,
          minSpeechFrames: 8,
          redemptionFrames: 12,
          preSpeechPadFrames: 10,
          submitUserSpeechOnPause: false,

          onSpeechStart: () => {
            setIsSpeechDetected(true)
            // Interrupt TTS if playing (barge-in)
            playbackQueueRef.current.stop()
            setIsSpeaking(false)
            // Cancel any pending VAD resume — we're already listening
            if (resumeTimerRef.current) {
              clearTimeout(resumeTimerRef.current)
              resumeTimerRef.current = null
            }
          },

          onSpeechEnd: (audio: Float32Array) => {
            setIsSpeechDetected(false)
            setIsTranscribing(true)

            // Encode to WAV (16kHz mono 16-bit) and send
            const wavBuffer = utils.encodeWAV(audio, 1, 16000, 1, 16)
            const base64 = utils.arrayBufferToBase64(wavBuffer)

            const ws = wsRef.current
            if (ws?.readyState === WebSocket.OPEN) {
              ws.send(JSON.stringify({
                type: 'voice_audio',
                conversation_id: conversationIdRef.current,
                audio_data: base64,
                mime_type: 'audio/wav',
                request_id: crypto.randomUUID?.() || `voice-${Date.now()}-${Math.random().toString(36).slice(2)}`,
              }))
            }
          },

          onVADMisfire: () => {
            setIsSpeechDetected(false)
          },
        })

        vadRef.current = vad
        vad.start()
        voiceModeRef.current = true
        setVoiceMode(true)
        setIsListening(true)

        // Fetch TTS config and connect ElevenLabs WebSocket
        try {
          const res = await fetch('/api/voice/tts-config')
          if (res.ok) {
            const config: TTSConfig = await res.json()
            ttsConfigRef.current = config
            connectTTS(config)
          } else {
            console.warn('TTS not available — voice will work without speech output')
          }
        } catch (err) {
          console.warn('Failed to fetch TTS config:', err)
        }
      } catch (err) {
        if (vadRef.current) {
          vadRef.current.destroy()
          vadRef.current = null
        }
        voiceModeRef.current = false
        const msg = err instanceof Error ? err.message : 'Microphone access denied'
        setVoiceError(msg)
        console.error('Failed to start VAD:', err)
      }
    } else {
      // Disable: destroy VAD, disconnect TTS, cleanup
      voiceModeRef.current = false
      if (resumeTimerRef.current) {
        clearTimeout(resumeTimerRef.current)
        resumeTimerRef.current = null
      }
      if (vadRef.current) {
        vadRef.current.destroy()
        vadRef.current = null
      }
      disconnectTTS()
      playbackQueueRef.current.stop()
      setVoiceMode(false)
      setIsListening(false)
      setIsSpeechDetected(false)
      setIsSpeaking(false)
      setIsTranscribing(false)
    }
  }, [voiceMode, wsRef, conversationId, connectTTS, disconnectTTS])

  // Cleanup VAD, TTS, and playback on unmount
  useEffect(() => {
    return () => {
      voiceModeRef.current = false
      if (vadRef.current) {
        vadRef.current.destroy()
        vadRef.current = null
      }
      disconnectTTS()
      playbackQueueRef.current.stop()
    }
  }, [disconnectTTS])

  const stopSpeaking = useCallback(() => {
    playbackQueueRef.current.stop()
    setIsSpeaking(false)
  }, [])

  /** Feed streaming text to TTS. Buffers into sentences before sending. */
  const feedTTSText = useCallback((text: string) => {
    const ws = ttsWsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return

    const sentences = sentenceBufferRef.current.add(text)
    for (const sentence of sentences) {
      ws.send(JSON.stringify({
        text: sentence + ' ',
        try_trigger_generation: true,
      }))
    }
  }, [])

  /** Flush remaining buffered text to TTS and signal generation. */
  const flushTTS = useCallback(() => {
    const ws = ttsWsRef.current
    if (!ws || ws.readyState !== WebSocket.OPEN) return

    const remaining = sentenceBufferRef.current.flush()
    if (remaining) {
      ws.send(JSON.stringify({
        text: remaining + ' ',
        try_trigger_generation: true,
      }))
    }
    // Signal flush to trigger any pending generation
    ws.send(JSON.stringify({ text: '', flush: true }))
  }, [])

  const handleVoiceMessage = useCallback((data: Record<string, unknown>) => {
    const type = data.type as string

    if (type === 'voice_transcription') {
      setIsTranscribing(false)
    } else if (type === 'voice_status') {
      const status = data.status as string
      if (status === 'error') {
        setVoiceError(data.error as string || 'Voice error')
        setIsTranscribing(false)
      } else if (status === 'empty') {
        setIsTranscribing(false)
      } else if (status === 'transcribing') {
        setIsTranscribing(true)
      }
    }
  }, [])

  return {
    voiceMode,
    voiceAvailable,
    isListening,
    isSpeechDetected,
    isTranscribing,
    isSpeaking,
    voiceError,
    toggleVoiceMode,
    stopSpeaking,
    handleVoiceMessage,
    feedTTSText,
    flushTTS,
  }
}
