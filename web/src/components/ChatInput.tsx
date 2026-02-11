import { useState, useCallback, KeyboardEvent, useRef, useEffect } from 'react'
import { CommandPalette } from './CommandPalette'
import type { CommandInfo } from '../hooks/useSlashCommands'

export interface QueuedFile {
  id: string
  file: File
  previewUrl: string | null
  base64: string | null
}

export interface ProjectOption {
  id: string
  name: string
}

interface ChatInputProps {
  onSend: (message: string, files?: QueuedFile[]) => void
  onStop?: () => void
  isStreaming?: boolean
  disabled?: boolean
  onInputChange?: (value: string) => void
  filteredCommands?: CommandInfo[]
  onCommandSelect?: (command: CommandInfo) => void
  projects?: ProjectOption[]
  selectedProjectId?: string | null
  onProjectChange?: (projectId: string) => void
  // Voice props
  voiceMode?: boolean
  isRecording?: boolean
  isTranscribing?: boolean
  isSpeaking?: boolean
  voiceError?: string | null
  onToggleVoice?: () => void
  onStartRecording?: () => void
  onStopRecording?: () => void
  onStopSpeaking?: () => void
}

export function ChatInput({
  onSend,
  onStop,
  isStreaming = false,
  disabled = false,
  onInputChange,
  filteredCommands = [],
  onCommandSelect,
  projects = [],
  selectedProjectId,
  onProjectChange,
  voiceMode = false,
  isRecording = false,
  isTranscribing = false,
  isSpeaking = false,
  voiceError,
  onToggleVoice,
  onStartRecording,
  onStopRecording,
  onStopSpeaking,
}: ChatInputProps) {
  const [input, setInput] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [queuedFiles, setQueuedFiles] = useState<QueuedFile[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const showPalette = input.startsWith('/') && filteredCommands.length > 0

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }, [input])

  // Reset selection when filtered commands change
  useEffect(() => {
    setSelectedIndex(0)
  }, [filteredCommands])

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim()
    const hasFiles = queuedFiles.length > 0
    if ((trimmed || hasFiles) && !disabled) {
      onSend(trimmed, hasFiles ? queuedFiles : undefined)
      setInput('')
      setQueuedFiles([])
    }
  }, [input, disabled, onSend, queuedFiles])

  const handleChange = useCallback(
    (value: string) => {
      setInput(value)
      onInputChange?.(value)
    },
    [onInputChange]
  )

  const handleCommandSelect = useCallback(
    (cmd: CommandInfo) => {
      onCommandSelect?.(cmd)
      setInput('')
    },
    [onCommandSelect]
  )

  const handleFilesSelected = useCallback((files: FileList | null) => {
    if (!files) return
    Array.from(files).forEach((file) => {
      const id = `file-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const isImage = file.type.startsWith('image/')
      const previewUrl = isImage ? URL.createObjectURL(file) : null

      const reader = new FileReader()
      reader.onload = () => {
        const result = reader.result as string
        // result is "data:<media_type>;base64,<data>"
        const base64 = result.split(',')[1] || null
        setQueuedFiles((prev) => [...prev, { id, file, previewUrl, base64 }])
      }
      reader.readAsDataURL(file)
    })
  }, [])

  const removeFile = useCallback((id: string) => {
    setQueuedFiles((prev) => {
      const removed = prev.find((f) => f.id === id)
      if (removed?.previewUrl) URL.revokeObjectURL(removed.previewUrl)
      return prev.filter((f) => f.id !== id)
    })
  }, [])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // Escape: close palette or stop streaming
      if (e.key === 'Escape') {
        if (showPalette) {
          e.preventDefault()
          setInput('')
          return
        }
        if (isStreaming && onStop) {
          e.preventDefault()
          onStop()
          return
        }
      }

      // Palette navigation
      if (showPalette) {
        if (e.key === 'ArrowUp') {
          e.preventDefault()
          setSelectedIndex((i) => (i > 0 ? i - 1 : filteredCommands.length - 1))
          return
        }
        if (e.key === 'ArrowDown') {
          e.preventDefault()
          setSelectedIndex((i) => (i < filteredCommands.length - 1 ? i + 1 : 0))
          return
        }
        if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
          e.preventDefault()
          const selected = filteredCommands[selectedIndex]
          if (selected) {
            handleCommandSelect(selected)
          }
          return
        }
      }

      // Enter to send, Shift+Enter for newline
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSubmit()
      }
    },
    [handleSubmit, isStreaming, onStop, showPalette, filteredCommands, selectedIndex, handleCommandSelect]
  )

  const hasInput = input.trim().length > 0 || queuedFiles.length > 0

  return (
    <div className="chat-input-container">
      {showPalette && (
        <CommandPalette
          commands={filteredCommands}
          selectedIndex={selectedIndex}
          onSelect={handleCommandSelect}
        />
      )}

      <div className="chat-toolbar">
        <button
          className="chat-toolbar-btn"
          onClick={() => fileInputRef.current?.click()}
          title="Attach file"
          disabled={disabled}
        >
          <PaperclipIcon />
        </button>
        {onToggleVoice && (
          <button
            className={`chat-toolbar-btn${voiceMode ? ' voice-active' : ''}`}
            onClick={onToggleVoice}
            title={voiceMode ? 'Disable voice mode' : 'Enable voice mode'}
            disabled={disabled}
          >
            <MicIcon />
          </button>
        )}
        {projects.length > 0 && (
          <div className="chat-project-toggle" role="group" aria-label="Project scope">
            <button
              className={`chat-project-toggle-btn${!selectedProjectId ? ' active' : ''}`}
              onClick={() => onProjectChange?.('')}
              disabled={disabled}
            >
              Personal
            </button>
            <button
              className={`chat-project-toggle-btn${selectedProjectId ? ' active' : ''}`}
              onClick={() => {
                const target = projects.find(p => p.id === selectedProjectId) || projects[0]
                if (target) onProjectChange?.(target.id)
              }}
              disabled={disabled}
            >
              {projects.find(p => p.id === selectedProjectId)?.name || projects[0]?.name || 'Project'}
            </button>
          </div>
        )}
        <input
          ref={fileInputRef}
          type="file"
          multiple
          style={{ display: 'none' }}
          onChange={(e) => { handleFilesSelected(e.target.files); e.target.value = '' }}
        />
      </div>

      {queuedFiles.length > 0 && (
        <div className="chat-file-previews">
          {queuedFiles.map((qf) => (
            <div key={qf.id} className="chat-file-preview">
              {qf.previewUrl ? (
                <img src={qf.previewUrl} alt={qf.file.name} className="chat-file-preview-img" />
              ) : (
                <div className="chat-file-preview-name">
                  <PaperclipIcon />
                  <span>{qf.file.name}</span>
                </div>
              )}
              <button className="chat-file-remove-btn" onClick={() => removeFile(qf.id)} title="Remove">
                &times;
              </button>
            </div>
          ))}
        </div>
      )}

      {voiceMode && isSpeaking && onStopSpeaking && (
        <div className="speaking-indicator" onClick={onStopSpeaking} title="Click to stop">
          <span className="speaking-bar" />
          <span className="speaking-bar" />
          <span className="speaking-bar" />
          <span className="speaking-bar" />
          <span className="speaking-label">Speaking...</span>
        </div>
      )}

      {voiceError && (
        <div className="voice-error">{voiceError}</div>
      )}

      <div className="chat-input-row">
        <textarea
          ref={textareaRef}
          className="chat-input"
          value={input}
          onChange={(e) => handleChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder={disabled ? 'Connecting...' : isStreaming ? 'Interrupt...' : voiceMode ? 'Voice mode on — hold mic to talk...' : 'Message or /command...'}
          disabled={disabled}
          rows={1}
        />
        {voiceMode && onStartRecording && onStopRecording ? (
          <div className="chat-actions">
            <button
              className={`ptt-button${isRecording ? ' recording' : ''}${isTranscribing ? ' transcribing' : ''}`}
              onMouseDown={onStartRecording}
              onMouseUp={onStopRecording}
              onMouseLeave={isRecording ? onStopRecording : undefined}
              onTouchStart={(e) => { e.preventDefault(); onStartRecording() }}
              onTouchEnd={(e) => { e.preventDefault(); onStopRecording() }}
              disabled={disabled || isTranscribing}
              title={isRecording ? 'Release to send' : isTranscribing ? 'Transcribing...' : 'Hold to talk'}
              aria-label={isRecording ? 'Release to send' : 'Hold to talk'}
            >
              {isTranscribing ? <SpinnerIcon /> : <MicIcon />}
            </button>
            {hasInput && (
              <button
                className="send-button"
                onClick={handleSubmit}
                disabled={disabled || !hasInput}
              >
                <SendIcon />
              </button>
            )}
          </div>
        ) : isStreaming ? (
          <div className="chat-actions">
            {onStop && (
              <button
                className="stop-button"
                onClick={() => onStop()}
                title="Stop generating"
                aria-label="Stop generating"
              >
                <StopIcon />
              </button>
            )}
            {hasInput && (
              <button
                className="send-button"
                onClick={handleSubmit}
                title="Send message (stops current generation)"
                aria-label="Send message (stops current generation)"
              >
                <SendIcon />
              </button>
            )}
          </div>
        ) : (
          <button
            className="send-button"
            onClick={handleSubmit}
            disabled={disabled || !hasInput}
          >
            <SendIcon />
          </button>
        )}
      </div>
    </div>
  )
}

function StopIcon() {
  return (
    <svg
      width="16"
      height="16"
      viewBox="0 0 16 16"
      fill="currentColor"
    >
      <rect x="3" y="3" width="10" height="10" rx="1" />
    </svg>
  )
}

function SendIcon() {
  return (
    <svg
      width="18"
      height="18"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

function MicIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="23" />
      <line x1="8" y1="23" x2="16" y2="23" />
    </svg>
  )
}

function SpinnerIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="spinner-icon">
      <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="32">
        <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite" />
        <animate attributeName="stroke-dashoffset" values="32;0" dur="1s" repeatCount="indefinite" />
      </circle>
    </svg>
  )
}

function PaperclipIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  )
}

