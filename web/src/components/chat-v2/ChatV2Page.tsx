import './styles.css'
import { useCallback } from 'react'
import type { ChatState, ConversationState, TerminalProps, ProjectProps, VoiceProps } from '../ChatPage'
import { ConversationPicker } from '../ConversationPicker'
import { TerminalPanel } from '../Terminal'
import { useArtifacts } from '../../hooks/useArtifacts'
import { ArtifactContext } from './artifacts/ArtifactContext'
import { ArtifactPanel } from './artifacts/ArtifactPanel'
import { ResizeHandle } from './artifacts/ResizeHandle'
import { MessageList } from './MessageList'
import { ChatV2Input } from './ChatInput'

interface ChatV2PageProps {
  chat: ChatState
  conversations: ConversationState
  terminal: TerminalProps
  project: ProjectProps
  voice: VoiceProps
}

export function ChatV2Page({ chat, conversations, terminal, project, voice }: ChatV2PageProps) {
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
      {/* Conversation Picker - reuse existing */}
      <ConversationPicker
        sessions={conversations.sessions}
        activeSessionId={conversations.activeSessionId}
        onNewChat={conversations.onNewChat}
        onSelectSession={conversations.onSelectSession}
        onDeleteSession={conversations.onDeleteSession}
      />

      {/* Main content area */}
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
              <ChatV2Input
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
          </div>
        </ArtifactContext.Provider>

        {/* Terminal panel - reuse existing */}
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
