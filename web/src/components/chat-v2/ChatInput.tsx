import { useState, useCallback, useRef, useEffect, useMemo, type KeyboardEvent } from 'react'
import type { QueuedFile, ProjectOption } from '../ChatInput'
import type { CommandInfo } from '../../hooks/useSlashCommands'
import { cn } from '../../lib/utils'
import { Button } from './ui/Button'

interface ChatV2InputProps {
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
  voiceMode?: boolean
  voiceAvailable?: boolean
  isListening?: boolean
  isSpeechDetected?: boolean
  isTranscribing?: boolean
  isSpeaking?: boolean
  voiceError?: string | null
  onToggleVoice?: () => void
  onStopSpeaking?: () => void
}

export function ChatV2Input({
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
  voiceAvailable = false,
  isListening = false,
  isSpeechDetected = false,
  isTranscribing = false,
  isSpeaking = false,
  voiceError,
  onToggleVoice,
  onStopSpeaking,
}: ChatV2InputProps) {
  const [input, setInput] = useState('')
  const [selectedIndex, setSelectedIndex] = useState(0)
  const [queuedFiles, setQueuedFiles] = useState<QueuedFile[]>([])
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const showPalette = input.startsWith('/') && filteredCommands.length > 0

  useEffect(() => {
    const textarea = textareaRef.current
    if (textarea) {
      textarea.style.height = 'auto'
      textarea.style.height = `${Math.min(textarea.scrollHeight, 200)}px`
    }
  }, [input])

  useEffect(() => { setSelectedIndex(0) }, [filteredCommands])

  const handleSubmit = useCallback(() => {
    const trimmed = input.trim()
    const hasFiles = queuedFiles.length > 0
    if ((trimmed || hasFiles) && !disabled) {
      onSend(trimmed, hasFiles ? queuedFiles : undefined)
      setInput('')
      setQueuedFiles([])
    }
  }, [input, disabled, onSend, queuedFiles])

  const handleChange = useCallback((value: string) => {
    setInput(value)
    onInputChange?.(value)
  }, [onInputChange])

  const handleCommandSelect = useCallback((cmd: CommandInfo) => {
    onCommandSelect?.(cmd)
    setInput('')
  }, [onCommandSelect])

  const handleFilesSelected = useCallback((files: FileList | null) => {
    if (!files) return
    Array.from(files).forEach((file) => {
      const id = `file-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
      const isImage = file.type.startsWith('image/')
      const previewUrl = isImage ? URL.createObjectURL(file) : null
      const reader = new FileReader()
      reader.onload = () => {
        const result = reader.result as string
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

  const handleKeyDown = useCallback((e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Escape') {
      if (showPalette) { e.preventDefault(); setInput(''); return }
      if (isStreaming && onStop) { e.preventDefault(); onStop(); return }
    }
    if (showPalette) {
      if (e.key === 'ArrowUp') { e.preventDefault(); setSelectedIndex((i) => (i > 0 ? i - 1 : filteredCommands.length - 1)); return }
      if (e.key === 'ArrowDown') { e.preventDefault(); setSelectedIndex((i) => (i < filteredCommands.length - 1 ? i + 1 : 0)); return }
      if (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey)) {
        e.preventDefault()
        const selected = filteredCommands[selectedIndex]
        if (selected) handleCommandSelect(selected)
        return
      }
    }
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSubmit() }
  }, [handleSubmit, isStreaming, onStop, showPalette, filteredCommands, selectedIndex, handleCommandSelect])

  const hasInput = input.trim().length > 0 || queuedFiles.length > 0

  // Project selector
  const personalProject = projects.find(p => p.name === 'Personal')
  const isPersonal = !selectedProjectId || selectedProjectId === personalProject?.id
  const selectedName = !isPersonal ? projects.find(p => p.id === selectedProjectId)?.name : null
  const nonPersonalProjects = useMemo(() => projects.filter(p => p.name !== 'Personal'), [projects])
  const [showProjectSearch, setShowProjectSearch] = useState(false)
  const [projectSearch, setProjectSearch] = useState('')
  const filtered = useMemo(
    () => projectSearch ? nonPersonalProjects.filter(p => p.name.toLowerCase().includes(projectSearch.toLowerCase())) : nonPersonalProjects,
    [nonPersonalProjects, projectSearch]
  )

  return (
    <div className="border-t border-border bg-background px-4 py-3">
      <div className="max-w-[900px] mx-auto">
        {/* Command palette */}
        {showPalette && (
          <div className="mb-2 rounded-lg border border-border bg-muted overflow-hidden max-h-48 overflow-y-auto">
            {filteredCommands.map((cmd, i) => (
              <div
                key={`${cmd.server}.${cmd.tool}`}
                className={cn(
                  'px-3 py-2 text-sm cursor-pointer',
                  i === selectedIndex ? 'bg-accent/20 text-foreground' : 'text-muted-foreground hover:bg-muted'
                )}
                onClick={() => handleCommandSelect(cmd)}
              >
                <span className="font-mono">/{cmd.name}</span>
                {cmd.description && <span className="ml-2 text-xs opacity-60">{cmd.description}</span>}
              </div>
            ))}
          </div>
        )}

        {/* Toolbar */}
        <div className="flex items-center gap-1 mb-2">
          <button
            className="p-1.5 rounded text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            onClick={() => fileInputRef.current?.click()}
            disabled={disabled}
            title="Attach file"
          >
            <PaperclipIcon />
          </button>
          {onToggleVoice && voiceAvailable && (
            <button
              className={cn('p-1.5 rounded transition-colors', voiceMode ? 'text-accent bg-accent/20' : 'text-muted-foreground hover:text-foreground hover:bg-muted')}
              onClick={onToggleVoice}
              disabled={disabled}
              title={voiceMode ? 'Disable voice mode' : 'Enable voice mode'}
            >
              <MicIcon />
            </button>
          )}
          {projects.length > 0 && (
            <div className="relative ml-auto">
              <div className="flex rounded-md border border-border text-xs">
                <button
                  className={cn('px-2 py-1 rounded-l-md transition-colors', isPersonal ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted')}
                  onClick={() => {
                    if (personalProject) onProjectChange?.(personalProject.id)
                    setShowProjectSearch(false)
                  }}
                  disabled={disabled}
                >
                  Personal
                </button>
                <button
                  className={cn('px-2 py-1 rounded-r-md transition-colors', !isPersonal ? 'bg-accent text-accent-foreground' : 'text-muted-foreground hover:bg-muted')}
                  onClick={() => {
                    if (nonPersonalProjects.length === 1) onProjectChange?.(nonPersonalProjects[0].id)
                    else setShowProjectSearch(!showProjectSearch)
                  }}
                  disabled={disabled}
                >
                  {selectedName ?? 'Project'}
                </button>
              </div>
              {showProjectSearch && (
                <div className="absolute bottom-full mb-1 left-0 w-48 rounded-md border border-border bg-background shadow-lg z-10">
                  <input
                    className="w-full px-2 py-1.5 text-xs bg-transparent border-b border-border text-foreground placeholder:text-muted-foreground focus:outline-none"
                    placeholder="Search projects..."
                    value={projectSearch}
                    onChange={(e) => setProjectSearch(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === 'Escape') { setShowProjectSearch(false); setProjectSearch('') }
                      if (e.key === 'Enter' && filtered.length > 0) { onProjectChange?.(filtered[0].id); setShowProjectSearch(false); setProjectSearch('') }
                    }}
                    autoFocus
                  />
                  <div className="max-h-32 overflow-y-auto">
                    {filtered.map((p) => (
                      <button
                        key={p.id}
                        className={cn('w-full text-left px-2 py-1 text-xs hover:bg-muted', p.id === selectedProjectId && 'bg-accent/20 text-accent')}
                        onClick={() => { onProjectChange?.(p.id); setShowProjectSearch(false); setProjectSearch('') }}
                      >
                        {p.name}
                      </button>
                    ))}
                    {filtered.length === 0 && <div className="px-2 py-1 text-xs text-muted-foreground">No projects found</div>}
                  </div>
                </div>
              )}
            </div>
          )}
          <input ref={fileInputRef} type="file" multiple className="hidden" onChange={(e) => { handleFilesSelected(e.target.files); e.target.value = '' }} />
        </div>

        {/* File previews */}
        {queuedFiles.length > 0 && (
          <div className="flex gap-2 mb-2 flex-wrap">
            {queuedFiles.map((qf) => (
              <div key={qf.id} className="relative rounded-md border border-border overflow-hidden bg-muted">
                {qf.previewUrl ? (
                  <img src={qf.previewUrl} alt={qf.file.name} className="w-16 h-16 object-cover" />
                ) : (
                  <div className="flex items-center gap-1 px-2 py-1 text-xs text-muted-foreground">
                    <PaperclipIcon />
                    <span className="max-w-[100px] truncate">{qf.file.name}</span>
                  </div>
                )}
                <button
                  className="absolute top-0 right-0 bg-black/60 rounded-bl text-foreground w-4 h-4 flex items-center justify-center text-xs"
                  onClick={() => removeFile(qf.id)}
                >
                  &times;
                </button>
              </div>
            ))}
          </div>
        )}

        {/* Listening indicator */}
        {voiceMode && isListening && !isSpeaking && !isTranscribing && (
          <div className="flex items-center gap-2 mb-2 px-3 py-2 rounded-lg bg-accent/10">
            {isSpeechDetected ? (
              <>
                <div className="flex gap-0.5 items-end h-4">
                  {[1, 2, 3, 4].map((i) => (
                    <span key={i} className="w-1 bg-green-400 rounded-full animate-pulse" style={{ height: `${8 + Math.random() * 8}px`, animationDelay: `${i * 0.1}s` }} />
                  ))}
                </div>
                <span className="text-sm text-green-400">Listening...</span>
              </>
            ) : (
              <>
                <span className="w-2 h-2 rounded-full bg-accent animate-pulse" />
                <span className="text-sm text-muted-foreground">Ready — speak to send</span>
              </>
            )}
          </div>
        )}

        {/* Transcribing indicator */}
        {voiceMode && isTranscribing && (
          <div className="flex items-center gap-2 mb-2 px-3 py-2 rounded-lg bg-accent/10">
            <SpinnerIcon />
            <span className="text-sm text-muted-foreground">Transcribing...</span>
          </div>
        )}

        {/* Speaking indicator */}
        {voiceMode && isSpeaking && onStopSpeaking && (
          <div
            className="flex items-center gap-2 mb-2 px-3 py-2 rounded-lg bg-accent/10 cursor-pointer"
            onClick={onStopSpeaking}
          >
            <div className="flex gap-0.5 items-end h-4">
              {[1, 2, 3, 4].map((i) => (
                <span key={i} className="w-1 bg-accent rounded-full animate-pulse" style={{ height: `${8 + Math.random() * 8}px`, animationDelay: `${i * 0.1}s` }} />
              ))}
            </div>
            <span className="text-sm text-accent">Speaking... (click to stop)</span>
          </div>
        )}

        {voiceError && (
          <div className="text-sm text-destructive-foreground mb-2">{voiceError}</div>
        )}

        {/* Input row */}
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            className="flex-1 bg-muted rounded-lg px-3 py-2 text-sm text-foreground placeholder:text-muted-foreground resize-none focus:outline-none focus:ring-2 focus:ring-accent min-h-[40px]"
            value={input}
            onChange={(e) => handleChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={disabled ? 'Connecting...' : isStreaming ? 'Interrupt...' : voiceMode ? 'Voice mode on...' : 'Message or /command...'}
            disabled={disabled}
            rows={1}
          />

          {isStreaming ? (
            <div className="flex gap-1">
              {onStop && (
                <Button size="icon" variant="outline" onClick={onStop} title="Stop generating">
                  <StopIcon />
                </Button>
              )}
              {hasInput && (
                <Button size="icon" variant="primary" onClick={handleSubmit}>
                  <SendIcon />
                </Button>
              )}
            </div>
          ) : (
            <Button size="icon" variant="primary" onClick={handleSubmit} disabled={disabled || !hasInput}>
              <SendIcon />
            </Button>
          )}
        </div>
      </div>
    </div>
  )
}

function SendIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="22" y1="2" x2="11" y2="13" />
      <polygon points="22 2 15 22 11 13 2 9 22 2" />
    </svg>
  )
}

function StopIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
      <rect x="3" y="3" width="10" height="10" rx="1" />
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

function PaperclipIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.44 11.05l-9.19 9.19a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  )
}

function SpinnerIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="animate-spin">
      <circle cx="12" cy="12" r="10" strokeDasharray="32" strokeDashoffset="32">
        <animateTransform attributeName="transform" type="rotate" from="0 12 12" to="360 12 12" dur="1s" repeatCount="indefinite" />
      </circle>
    </svg>
  )
}
