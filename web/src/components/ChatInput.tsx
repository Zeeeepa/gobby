import { useState, useCallback, KeyboardEvent, useRef, useEffect } from 'react'

interface ChatInputProps {
  onSend: (message: string) => void
  onStop?: () => void
  isStreaming?: boolean
  disabled?: boolean
}

export function ChatInput({ onSend, onStop, isStreaming = false, disabled = false }: ChatInputProps) {
  const [input, setInput] = useState('')
  const textareaRef = useRef<HTMLTextAreaElement>(null)

  // Auto-resize textarea
  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }, [input])

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim()
    if (trimmed && !disabled) {
      onSend(trimmed)
      setInput('')
    }
  }, [input, disabled, onSend])

  const handleKeyDown = useCallback(
    (e: KeyboardEvent<HTMLTextAreaElement>) => {
      // Escape to stop streaming
      if (e.key === 'Escape' && isStreaming && onStop) {
        e.preventDefault()
        onStop()
        return
      }
      // Enter to send, Shift+Enter for newline
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSubmit()
      }
    },
    [handleSubmit, isStreaming, onStop]
  )

  const hasInput = input.trim().length > 0

  return (
    <div className="chat-input-container">
      <textarea
        ref={textareaRef}
        className="chat-input"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? 'Connecting...' : isStreaming ? 'Send a message to interrupt...' : 'Type a message... (Shift+Enter for newline)'}
        disabled={disabled}
        rows={1}
      />
      {isStreaming ? (
        <div className="chat-actions">
          <button
            className="stop-button"
            onClick={() => onStop?.()}
            title="Stop generating"
            aria-label="Stop generating"
          >
            <StopIcon />
          </button>
          {hasInput && (
            <button
              className="send-button"
              onClick={handleSubmit}
              title="Send message (stops current generation)"
              aria-label="Send message (stops current generation)"
            >
              Send
            </button>
          )}
        </div>
      ) : (
        <button
          className="send-button"
          onClick={handleSubmit}
          disabled={disabled || !hasInput}
        >
          Send
        </button>
      )}
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
