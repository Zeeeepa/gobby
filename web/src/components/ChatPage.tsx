import { ConversationPicker } from './ConversationPicker'
import { ChatMessages } from './ChatMessages'
import { ChatInput } from './ChatInput'
import type { QueuedFile, ProjectOption } from './ChatInput'
import { TerminalPanel } from './Terminal'
import type { ChatMessage } from './Message'
import type { GobbySession } from '../hooks/useSessions'
import type { CommandInfo } from '../hooks/useSlashCommands'

interface ChatPageProps {
  // Chat state
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
  // ConversationPicker state
  webChatSessions: GobbySession[]
  activeSessionId: string | null
  onNewChat: () => void
  onSelectSession: (session: GobbySession) => void
  // Terminal state
  terminalOpen: boolean
  onTerminalToggle: () => void
  agents: Array<{ run_id: string; provider: string; pid?: number; mode?: string }>
  selectedAgent: string | null
  onSelectAgent: (runId: string | null) => void
  onTerminalInput: (runId: string, data: string) => void
  onTerminalOutput: (callback: (runId: string, data: string) => void) => void
  // Project selector
  projects: ProjectOption[]
  selectedProjectId: string | null
  onProjectChange: (projectId: string) => void
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

export function ChatPage({
  messages,
  isStreaming,
  isThinking,
  isConnected,
  onSend,
  onStop,
  onRespondToQuestion,
  onInputChange,
  filteredCommands,
  onCommandSelect,
  webChatSessions,
  activeSessionId,
  onNewChat,
  onSelectSession,
  terminalOpen,
  onTerminalToggle,
  agents,
  selectedAgent,
  onSelectAgent,
  onTerminalInput,
  onTerminalOutput,
  projects,
  selectedProjectId,
  onProjectChange,
  voiceMode,
  isRecording,
  isTranscribing,
  isSpeaking,
  voiceError,
  onToggleVoice,
  onStartRecording,
  onStopRecording,
  onStopSpeaking,
}: ChatPageProps) {
  return (
    <div className="chat-page">
      <ConversationPicker
        sessions={webChatSessions}
        activeSessionId={activeSessionId}
        onNewChat={onNewChat}
        onSelectSession={onSelectSession}
      />
      <div className="chat-main">
        <main className="chat-container">
          <ChatMessages
            messages={messages}
            isStreaming={isStreaming}
            isThinking={isThinking}
            onRespondToQuestion={onRespondToQuestion}
          />
          <ChatInput
            onSend={onSend}
            onStop={onStop}
            isStreaming={isStreaming}
            disabled={!isConnected}
            onInputChange={onInputChange}
            filteredCommands={filteredCommands}
            onCommandSelect={onCommandSelect}
            projects={projects}
            selectedProjectId={selectedProjectId}
            onProjectChange={onProjectChange}
            voiceMode={voiceMode}
            isRecording={isRecording}
            isTranscribing={isTranscribing}
            isSpeaking={isSpeaking}
            voiceError={voiceError}
            onToggleVoice={onToggleVoice}
            onStartRecording={onStartRecording}
            onStopRecording={onStopRecording}
            onStopSpeaking={onStopSpeaking}
          />
        </main>

        <TerminalPanel
          isOpen={terminalOpen}
          onToggle={onTerminalToggle}
          agents={agents}
          selectedAgent={selectedAgent}
          onSelectAgent={onSelectAgent}
          onInput={onTerminalInput}
          onOutput={onTerminalOutput}
        />
      </div>
    </div>
  )
}
