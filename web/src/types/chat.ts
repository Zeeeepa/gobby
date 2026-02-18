import type { CommandInfo } from '../hooks/useSlashCommands'
import type { GobbySession } from '../hooks/useSessions'

export interface ToolCall {
  id: string
  tool_name: string
  server_name: string
  status: 'calling' | 'completed' | 'error' | 'pending_approval'
  arguments?: Record<string, unknown>
  result?: unknown
  error?: string
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: Date
  toolCalls?: ToolCall[]
  thinkingContent?: string
}

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

export interface ChatState {
  messages: ChatMessage[]
  isStreaming: boolean
  isThinking: boolean
  isConnected: boolean
  onSend: (content: string, files?: QueuedFile[]) => void
  onStop: () => void
  onRespondToQuestion: (toolCallId: string, answers: Record<string, string>) => void
  onInputChange: (value: string) => void
  filteredCommands: CommandInfo[]
  onCommandSelect: (cmd: CommandInfo) => void
}

export interface ConversationState {
  sessions: GobbySession[]
  activeSessionId: string | null
  onNewChat: () => void
  onSelectSession: (session: GobbySession) => void
  onDeleteSession?: (session: GobbySession) => void
}

export interface AgentPanelProps {
  isOpen: boolean
  onToggle: () => void
  agents: Array<{ run_id: string; provider: string; pid?: number; mode?: string }>
  selectedAgent: string | null
  onSelectAgent: (runId: string | null) => void
}

export interface ProjectProps {
  projects: ProjectOption[]
  selectedProjectId: string | null
  onProjectChange: (projectId: string) => void
}

export interface VoiceProps {
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
