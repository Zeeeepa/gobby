import { useState, useCallback, useRef, useEffect } from 'react'

interface VoiceState {
  voiceMode: boolean
  voiceAvailable: boolean
  isRecording: boolean
  isTranscribing: boolean
  isSpeaking: boolean
  voiceError: string | null
}

/** Sequential audio playback queue using HTMLAudioElement (iOS Safari compatible). */
class AudioPlaybackQueue {
  private queue: string[] = []
  private playing = false
  private currentAudio: HTMLAudioElement | null = null

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
    }
    audio.onerror = () => {
      URL.revokeObjectURL(url)
      this.playing = false
      this.currentAudio = null
      this.playNext()
    }
    audio.play().catch(() => {
      URL.revokeObjectURL(url)
      this.playing = false
      this.currentAudio = null
      this.playNext()
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
  }

  get isPlaying() {
    return this.playing || this.queue.length > 0
  }
}

export interface UseVoiceReturn extends VoiceState {
  toggleVoiceMode: () => void
  startRecording: () => void
  stopRecording: () => void
  stopSpeaking: () => void
  handleVoiceMessage: (data: Record<string, unknown>) => void
}

export function useVoice(
  wsRef: React.RefObject<WebSocket | null>,
  conversationId: string,
): UseVoiceReturn {
  const [voiceMode, setVoiceMode] = useState(false)
  const [voiceAvailable, setVoiceAvailable] = useState(false)
  const [isRecording, setIsRecording] = useState(false)
  const [isTranscribing, setIsTranscribing] = useState(false)
  const [isSpeaking, setIsSpeaking] = useState(false)
  const [voiceError, setVoiceError] = useState<string | null>(null)

  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const playbackQueueRef = useRef(new AudioPlaybackQueue())

  // Check voice availability on mount
  useEffect(() => {
    fetch('/api/voice/status')
      .then(res => res.ok ? res.json() : null)
      .then(data => {
        if (data?.enabled && data?.stt_available) {
          setVoiceAvailable(true)
        }
      })
      .catch(() => {})
  }, [])

  // Track speaking state from playback queue
  useEffect(() => {
    const interval = setInterval(() => {
      const playing = playbackQueueRef.current.isPlaying
      setIsSpeaking(playing)
    }, 200)
    return () => clearInterval(interval)
  }, [])

  const toggleVoiceMode = useCallback(() => {
    const newMode = !voiceMode
    setVoiceMode(newMode)
    setVoiceError(null)

    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'voice_mode_toggle',
        conversation_id: conversationId,
        enabled: newMode,
      }))
    }

    if (!newMode) {
      // Cleanup on disable
      playbackQueueRef.current.stop()
      setIsSpeaking(false)
      if (mediaRecorderRef.current?.state === 'recording') {
        mediaRecorderRef.current.stop()
      }
      if (streamRef.current) {
        streamRef.current.getTracks().forEach(t => t.stop())
        streamRef.current = null
      }
      setIsRecording(false)
    }
  }, [voiceMode, wsRef, conversationId])

  const startRecording = useCallback(async () => {
    if (!voiceMode) return
    setVoiceError(null)

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream

      // Stop any current TTS playback when user starts talking
      playbackQueueRef.current.stop()
      setIsSpeaking(false)

      const mimeType = MediaRecorder.isTypeSupported('audio/webm;codecs=opus')
        ? 'audio/webm;codecs=opus'
        : 'audio/webm'

      const recorder = new MediaRecorder(stream, { mimeType })
      mediaRecorderRef.current = recorder
      chunksRef.current = []

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) {
          chunksRef.current.push(e.data)
        }
      }

      recorder.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mimeType })
        chunksRef.current = []

        // Convert to base64 and send
        const reader = new FileReader()
        reader.onload = () => {
          const dataUrl = reader.result as string
          const base64 = dataUrl.split(',')[1]
          if (base64 && wsRef.current?.readyState === WebSocket.OPEN) {
            wsRef.current.send(JSON.stringify({
              type: 'voice_audio',
              conversation_id: conversationId,
              audio_data: base64,
              mime_type: mimeType,
              request_id: crypto.randomUUID?.() || `voice-${Date.now()}`,
            }))
            setIsTranscribing(true)
          }
        }
        reader.readAsDataURL(blob)

        // Stop the media stream tracks
        stream.getTracks().forEach(t => t.stop())
        streamRef.current = null
      }

      recorder.start()
      setIsRecording(true)
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Microphone access denied'
      setVoiceError(msg)
      console.error('Failed to start recording:', err)
    }
  }, [voiceMode, wsRef, conversationId])

  const stopRecording = useCallback(() => {
    if (mediaRecorderRef.current?.state === 'recording') {
      mediaRecorderRef.current.stop()
    }
    setIsRecording(false)
  }, [])

  const stopSpeaking = useCallback(() => {
    playbackQueueRef.current.stop()
    setIsSpeaking(false)
  }, [])

  const handleVoiceMessage = useCallback((data: Record<string, unknown>) => {
    const type = data.type as string

    if (type === 'voice_transcription') {
      setIsTranscribing(false)
    } else if (type === 'voice_audio_chunk') {
      const audioData = data.audio_data as string
      const isFinal = data.is_final as boolean
      const format = (data.format as string) || 'mp3_44100_128'

      if (audioData) {
        playbackQueueRef.current.enqueue(audioData, format)
        setIsSpeaking(true)
      }

      if (isFinal) {
        // Audio stream complete — speaking state will clear when queue drains
      }
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
    isRecording,
    isTranscribing,
    isSpeaking,
    voiceError,
    toggleVoiceMode,
    startRecording,
    stopRecording,
    stopSpeaking,
    handleVoiceMessage,
  }
}
