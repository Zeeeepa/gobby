import { useState, useCallback, KeyboardEvent, useRef, useEffect } from 'react'
import { CommandPalette } from './CommandPalette'
import type { CommandInfo } from '../hooks/useSlashCommands'

interface ChatInputProps {
  onSend: (message: string) => void
  onStop?: () => void
  isStreaming?: boolean
  disabled?: boolean
  onInputChange?: (value: string) => void
  filteredCommands?: CommandInfo[]
  onCommandSelect?: (command: CommandInfo) => void
}

export function ChatInput({
  onSend,
  onStop,
  isStreaming = false,
  disabled = false,
  onInputChange,
  filteredCommands = [],
  onCommandSelect,
}: ChatInputProps) {
  const [input, setInput] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const textareaRef = useRef<HTMLTextAreaElement>(null)

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
    if (trimmed && !disabled) {
      onSend(trimmed)
      setInput('')
    }
  }, [input, disabled, onSend])

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

  const hasInput = input.trim().length > 0

  return (
    <div className="chat-input-container">
      {showPalette && (
        <CommandPalette
          commands={filteredCommands}
          selectedIndex={selectedIndex}
          onSelect={handleCommandSelect}
        />
      )}
      <textarea
        ref={textareaRef}
        className="chat-input"
        value={input}
        onChange={(e) => handleChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={disabled ? 'Connecting...' : isStreaming ? 'Interrupt...' : 'Message or /command...'}
        disabled={disabled}
        rows={1}
      />
      {isStreaming ? (
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
