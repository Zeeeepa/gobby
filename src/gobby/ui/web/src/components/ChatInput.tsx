import { useState, useCallback, KeyboardEvent, useRef, useEffect } from 'react'

interface ChatInputProps {
  onSend: (message: string) => void
  disabled?: boolean
}

export function ChatInput({ onSend, disabled = false }: ChatInputProps) {
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
      // Enter to send, Shift+Enter for newline
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault()
        handleSubmit()
      }
    },
    [handleSubmit]
  )

  return (
    <div className="chat-input-container">
      <textarea
        ref={textareaRef}
        className="chat-input"
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? 'Waiting...' : 'Type a message... (Shift+Enter for newline)'}
        disabled={disabled}
        rows={1}
      />
      <button
        className="send-button"
        onClick={handleSubmit}
        disabled={disabled || !input.trim()}
      >
        Send
      </button>
    </div>
  )
}
