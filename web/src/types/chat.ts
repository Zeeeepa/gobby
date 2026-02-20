import type { CommandInfo } from '../hooks/useSlashCommands'
import type { GobbySession } from '../hooks/useSessions'

export type ChatMode = 'accept_edits' | 'bypass' | 'plan'

export interface ChatModeInfo {
  id: ChatMode
  label: string
  description: string
}

export const CHAT_MODES: ChatModeInfo[] = [
  { id: 'plan', label: 'Plan', description: 'Read-only planning mode' },
  { id: 'accept_edits', label: 'Act', description: 'Auto-approve edits, prompt for dangerous commands' },
  { id: 'bypass', label: 'Full Auto', description: 'Auto-approve all tools' },
]

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

export interface ContextUsage {
  inputTokens: number
  outputTokens: number
  contextWindow: number | null
}

export interface ChatState {
  messages: ChatMessage[]
  isStreaming: boolean
  isThinking: boolean
  isConnected: boolean
  contextUsage?: ContextUsage
  onSend: (content: string, files?: QueuedFile[]) => void
  onStop: () => void
  onRespondToQuestion: (toolCallId: string, answers: Record<string, string>) => void
  onInputChange: (value: string) => void
  filteredCommands: CommandInfo[]
  onCommandSelect: (cmd: CommandInfo) => void
  mode: ChatMode
  onModeChange: (mode: ChatMode) => void
}

export interface ConversationState {
  sessions: GobbySession[]
  recentCliSessions?: GobbySession[]
  activeSessionId: string | null
  onNewChat: () => void
  onSelectSession: (session: GobbySession) => void
  onDeleteSession?: (session: GobbySession) => void
  onContinueSession?: (session: GobbySession) => void
  onRenameSession?: (id: string, title: string) => void
  agents: Array<{ run_id: string; provider: string; pid?: number; mode?: string; started_at?: string; tmux_session_name?: string }>
  onNavigateToAgent: (agent: { run_id: string; tmux_session_name?: string }) => void
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
