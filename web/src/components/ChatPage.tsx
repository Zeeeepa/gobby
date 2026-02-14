import { useState, useCallback } from 'react'
import { ConversationPicker } from './ConversationPicker'
import { ChatMessages } from './ChatMessages'
import { ChatInput } from './ChatInput'
import type { QueuedFile, ProjectOption } from './ChatInput'
import { TerminalPanel } from './Terminal'
import type { ChatMessage } from './Message'
import type { GobbySession } from '../hooks/useSessions'
import type { CommandInfo } from '../hooks/useSlashCommands'

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
}

export interface TerminalProps {
  isOpen: boolean
  onToggle: () => void
  agents: Array<{ run_id: string; provider: string; pid?: number; mode?: string }>
  selectedAgent: string | null
  onSelectAgent: (runId: string | null) => void
  onInput: (runId: string, data: string) => void
  onOutput: (callback: (runId: string, data: string) => void) => void
}

export interface ProjectProps {
  projects: ProjectOption[]
  selectedProjectId: string | null
  onProjectChange: (projectId: string) => void
}

export interface VoiceProps {
  voiceMode?: boolean
  voiceAvailable?: boolean
  isRecording?: boolean
  isTranscribing?: boolean
  isSpeaking?: boolean
  voiceError?: string | null
  onToggleVoice?: () => void
  onStartRecording?: () => void
  onStopRecording?: () => void
  onStopSpeaking?: () => void
}

interface ChatPageProps {
  chat: ChatState
  conversations: ConversationState
  terminal: TerminalProps
  project: ProjectProps
  voice: VoiceProps
}

function MobileChatDrawer({ conversations }: { conversations: ConversationState }) {
  const [isOpen, setIsOpen] = useState(false)

  const handleSelect = useCallback((session: GobbySession) => {
    conversations.onSelectSession(session)
    setIsOpen(false)
  }, [conversations])

  const handleNewChat = useCallback(() => {
    conversations.onNewChat()
    setIsOpen(false)
  }, [conversations])

  return (
    <div className={`mobile-chat-drawer ${isOpen ? 'open' : 'collapsed'}`}>
      <div className="mobile-chat-drawer-header" onClick={() => setIsOpen(prev => !prev)}>
        <span className="mobile-chat-drawer-title">
          <ChatIcon />
          Chats
          <span className="agent-count">{conversations.sessions.length}</span>
        </span>
        <button className="terminal-toggle">
          {isOpen ? '\u25B2' : '\u25BC'}
        </button>
      </div>
      {isOpen && (
        <div className="mobile-chat-drawer-content">
          <button className="mobile-chat-drawer-new" onClick={handleNewChat}>
            + New Chat
          </button>
          <div className="mobile-chat-drawer-list">
            {conversations.sessions.length === 0 && (
              <div className="terminals-empty-sidebar">No conversations</div>
            )}
            {conversations.sessions.map((session) => {
              const title = session.title || `Chat #${session.ref}`
              const isActive = session.external_id === conversations.activeSessionId
              return (
                <div
                  key={session.id}
                  className={`session-item ${isActive ? 'attached' : ''}`}
                  onClick={() => handleSelect(session)}
                  role="button"
                  tabIndex={0}
                  onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); handleSelect(session) } }}
                >
                  <div className="session-item-main">
                    <span className="session-source-dot web-chat" />
                    <span className="session-name" title={title}>{title}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}
    </div>
  )
}

function ChatIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )
}

export function ChatPage({ chat, conversations, terminal, project, voice }: ChatPageProps) {

  return (
    <div className="chat-page">
      <ConversationPicker
        sessions={conversations.sessions}
        activeSessionId={conversations.activeSessionId}
        onNewChat={conversations.onNewChat}
        onSelectSession={conversations.onSelectSession}
      />
      <div className="chat-main">
        <MobileChatDrawer conversations={conversations} />
        <main className="chat-container">
          <ChatMessages
            messages={chat.messages}
            isStreaming={chat.isStreaming}
            isThinking={chat.isThinking}
            onRespondToQuestion={chat.onRespondToQuestion}
          />
          <ChatInput
            onSend={chat.onSend}
            onStop={chat.onStop}
            isStreaming={chat.isStreaming}
            disabled={!chat.isConnected}
            onInputChange={chat.onInputChange}
            filteredCommands={chat.filteredCommands}
            onCommandSelect={chat.onCommandSelect}
            projects={project.projects}
            selectedProjectId={project.selectedProjectId}
            onProjectChange={project.onProjectChange}
            voiceMode={voice.voiceMode}
            voiceAvailable={voice.voiceAvailable}
            isRecording={voice.isRecording}
            isTranscribing={voice.isTranscribing}
            isSpeaking={voice.isSpeaking}
            voiceError={voice.voiceError}
            onToggleVoice={voice.onToggleVoice}
            onStartRecording={voice.onStartRecording}
            onStopRecording={voice.onStopRecording}
            onStopSpeaking={voice.onStopSpeaking}
          />
        </main>

        <TerminalPanel
          isOpen={terminal.isOpen}
          onToggle={terminal.onToggle}
          agents={terminal.agents}
          selectedAgent={terminal.selectedAgent}
          onSelectAgent={terminal.onSelectAgent}
          onInput={terminal.onInput}
          onOutput={terminal.onOutput}
        />
      </div>
    </div>
  )
}
