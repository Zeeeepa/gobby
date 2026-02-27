import { useState, useCallback, useRef, useEffect } from 'react'
import { MicVAD, utils } from '@ricky0123/vad-web'

interface VoiceState {
  voiceMode: boolean
  voiceAvailable: boolean
  isListening: boolean
  isSpeechDetected: boolean
  isTranscribing: boolean
  voiceError: string | null
}

export interface UseVoiceReturn extends VoiceState {
  toggleVoiceMode: () => void
  handleVoiceMessage: (data: Record<string, unknown>) => void
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
  const [voiceError, setVoiceError] = useState<string | null>(null)

  const vadRef = useRef<MicVAD | null>(null)

  // Stable ref for conversationId so long-lived callbacks (e.g. VAD onSpeechEnd)
  // always see the latest value without re-subscribing.
  const conversationIdRef = useRef(conversationId)
  conversationIdRef.current = conversationId

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
      // Enable: create VAD, start listening
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
      // Disable: destroy VAD, cleanup
      voiceModeRef.current = false
      if (vadRef.current) {
        vadRef.current.destroy()
        vadRef.current = null
      }
      setVoiceMode(false)
      setIsListening(false)
      setIsSpeechDetected(false)
      setIsTranscribing(false)
    }
  }, [voiceMode, wsRef, conversationId])

  // Cleanup VAD on unmount
  useEffect(() => {
    return () => {
      voiceModeRef.current = false
      if (vadRef.current) {
        vadRef.current.destroy()
        vadRef.current = null
      }
    }
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
    voiceError,
    toggleVoiceMode,
    handleVoiceMessage,
  }
}
