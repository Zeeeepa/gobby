import './styles.css'
import { useCallback } from 'react'
import type { ChatState, ConversationState, AgentPanelProps, ProjectProps, VoiceProps } from '../../types/chat'
import { ConversationPicker } from '../ConversationPicker'
import { useArtifacts } from '../../hooks/useArtifacts'
import { ArtifactContext } from './artifacts/ArtifactContext'
import { ArtifactPanel } from './artifacts/ArtifactPanel'
import { ResizeHandle } from './artifacts/ResizeHandle'
import { MessageList } from './MessageList'
import { ChatInput } from './ChatInput'
import { AgentStatusPanel } from './AgentStatusPanel'

interface ChatPageProps {
  chat: ChatState
  conversations: ConversationState
  agents: AgentPanelProps
  project: ProjectProps
  voice: VoiceProps
}

export function ChatPage({ chat, conversations, agents, project, voice }: ChatPageProps) {
  const {
    activeArtifact,
    isPanelOpen,
    panelWidth,
    createArtifact,
    updateArtifact,
    closePanel,
    setVersion,
    setPanelWidth,
  } = useArtifacts()

  const openCodeAsArtifact = useCallback((language: string, content: string, title?: string) => {
    createArtifact('code', content, language, title)
  }, [createArtifact])

  return (
    <div className="flex h-full overflow-hidden" style={{ background: '#0a0a0a', color: '#e5e5e5' }}>
      <ConversationPicker
        sessions={conversations.sessions}
        activeSessionId={conversations.activeSessionId}
        onNewChat={conversations.onNewChat}
        onSelectSession={conversations.onSelectSession}
        onDeleteSession={conversations.onDeleteSession}
      />

      <div className="flex flex-col flex-1 min-w-0">
        <ArtifactContext.Provider value={{ openCodeAsArtifact }}>
          <div className="flex flex-1 min-h-0">
            {/* Chat column */}
            <div className="flex flex-col flex-1 min-w-0">
              <MessageList
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
                isListening={voice.isListening}
                isSpeechDetected={voice.isSpeechDetected}
                isTranscribing={voice.isTranscribing}
                isSpeaking={voice.isSpeaking}
                voiceError={voice.voiceError}
                onToggleVoice={voice.onToggleVoice}
                onStopSpeaking={voice.onStopSpeaking}
              />
            </div>

            {/* Artifact panel */}
            {isPanelOpen && activeArtifact && (
              <>
                <ResizeHandle onResize={setPanelWidth} panelWidth={panelWidth} />
                <ArtifactPanel
                  artifact={activeArtifact}
                  width={panelWidth}
                  onClose={closePanel}
                  onUpdateContent={updateArtifact}
                  onSetVersion={setVersion}
                />
              </>
            )}

            {/* Agent status panel */}
            {agents.isOpen && (
              <AgentStatusPanel
                agents={agents.agents}
                selectedAgent={agents.selectedAgent}
                onSelectAgent={agents.onSelectAgent}
                onClose={agents.onToggle}
              />
            )}
          </div>
        </ArtifactContext.Provider>
      </div>
    </div>
  )
}
