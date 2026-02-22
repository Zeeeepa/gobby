import './styles.css'
import { useCallback } from 'react'
import type { ChatState, ConversationState, VoiceProps } from '../../types/chat'
import { ConversationPicker } from '../ConversationPicker'
import { useArtifacts } from '../../hooks/useArtifacts'
import { ArtifactContext } from './artifacts/ArtifactContext'
import { ArtifactPanel } from './artifacts/ArtifactPanel'
import { ResizeHandle } from './artifacts/ResizeHandle'
import { MessageList } from './MessageList'
import { ChatInput } from './ChatInput'
import { MobileChatDrawer } from './MobileChatDrawer'
import { SessionStatusBar } from './SessionStatusBar'

interface ChatPageProps {
  chat: ChatState
  conversations: ConversationState
  voice: VoiceProps
}

export function ChatPage({ chat, conversations, voice }: ChatPageProps) {
  const activeSession = conversations.sessions.find(
    s => s.external_id === conversations.activeSessionId
  )
  const activeTitle = activeSession?.title ?? null
  const effectiveSessionRef = chat.sessionRef
    ?? (activeSession?.seq_num != null ? `#${activeSession.seq_num}` : null)

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
    <div className="flex h-full overflow-hidden bg-background text-foreground">
      <ConversationPicker
        sessions={conversations.sessions}
        activeSessionId={conversations.activeSessionId}
        onNewChat={conversations.onNewChat}
        onSelectSession={conversations.onSelectSession}
        onDeleteSession={conversations.onDeleteSession}
        onRenameSession={conversations.onRenameSession}
        agents={conversations.agents}
        onNavigateToAgent={conversations.onNavigateToAgent}
      />

      <div className="flex flex-col flex-1 min-w-0">
        <MobileChatDrawer
          sessions={conversations.sessions}
          activeSessionId={conversations.activeSessionId}
          onNewChat={conversations.onNewChat}
          onSelectSession={conversations.onSelectSession}
          onDeleteSession={conversations.onDeleteSession}
        />
        <ArtifactContext.Provider value={{ openCodeAsArtifact }}>
          <div className="flex flex-1 min-h-0">
            {/* Chat column */}
            <div className="flex flex-col flex-1 min-w-0">
              <SessionStatusBar
                sessionRef={effectiveSessionRef}
                title={activeTitle}
                mode={chat.mode}
              />
              <MessageList
                messages={chat.messages}
                isStreaming={chat.isStreaming}
                isThinking={chat.isThinking}
                onRespondToQuestion={chat.onRespondToQuestion}
                planPendingApproval={chat.planPendingApproval}
                onApprovePlan={chat.onApprovePlan}
                onRequestPlanChanges={chat.onRequestPlanChanges}
              />
              <ChatInput
                onSend={chat.onSend}
                onStop={chat.onStop}
                isStreaming={chat.isStreaming}
                disabled={!chat.isConnected}
                onInputChange={chat.onInputChange}
                filteredCommands={chat.filteredCommands}
                onCommandSelect={chat.onCommandSelect}
                mode={chat.mode}
                onModeChange={chat.onModeChange}
                contextUsage={chat.contextUsage}
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
      </div>
    </div>
  )
}
