import "./styles.css";
import { useCallback, useEffect, useRef, useState } from "react";
import { useIsMobile } from "../../hooks/useIsMobile";
import type {
  ChatState,
  ConversationState,
  VoiceProps,
} from "../../types/chat";
import type { AgentDefInfo } from "../../hooks/useAgentDefinitions";
import type { ArtifactType } from "../../types/artifacts";
import { ConversationPicker } from "./ConversationPicker";
import { useArtifacts } from "../../hooks/useArtifacts";
import { ArtifactContext } from "./artifacts/ArtifactContext";
import { ArtifactPanel } from "./artifacts/ArtifactPanel";
import { ResizeHandle } from "./artifacts/ResizeHandle";
import { MessageList, type MessageListHandle } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { MobileChatDrawer } from "./MobileChatDrawer";
import { SessionStatusBar } from "./SessionStatusBar";
import { CanvasPanel } from "../canvas/CanvasPanel";
import { useCanvasPanel } from "../canvas/hooks/useCanvasPanel";

interface ChatPageProps {
  chat: ChatState;
  conversations: ConversationState;
  voice: VoiceProps;
  projectId?: string | null;
  showPlanRef?: React.MutableRefObject<(() => void) | null>;
  agentDefinitions?: AgentDefInfo[];
  agentGlobalDefs?: AgentDefInfo[];
  agentProjectDefs?: AgentDefInfo[];
  agentShowScopeToggle?: boolean;
  agentHasGlobal?: boolean;
  agentHasProject?: boolean;
}

export function ChatPage({
  chat,
  conversations,
  voice,
  projectId,
  showPlanRef,
  agentDefinitions = [],
  agentGlobalDefs = [],
  agentProjectDefs = [],
  agentShowScopeToggle = false,
  agentHasGlobal = false,
  agentHasProject = false,
}: ChatPageProps) {
  const messageListRef = useRef<MessageListHandle>(null);
  const activeSession = conversations.sessions.find(
    (s) => s.external_id === conversations.activeSessionId,
  );
  const activeTitle = activeSession?.title ?? null;
  const effectiveSessionRef =
    chat.sessionRef ??
    (activeSession?.seq_num != null ? `#${activeSession.seq_num}` : null);

  const {
    activeArtifact,
    isPanelOpen,
    panelWidth,
    createArtifact,
    updateArtifact,
    openArtifact,
    closePanel,
    setVersion,
    setPanelWidth,
  } = useArtifacts();

  const isMobile = useIsMobile();
  const canvas = useCanvasPanel();

  // Track container width for dynamic artifact panel max
  const contentRef = useRef<HTMLDivElement>(null)
  const [contentWidth, setContentWidth] = useState(0)
  useEffect(() => {
    const el = contentRef.current
    if (!el) return
    const obs = new ResizeObserver(([entry]) => setContentWidth(entry.contentRect.width))
    obs.observe(el)
    return () => obs.disconnect()
  }, [])
  const MIN_CHAT_WIDTH = 320
  const maxPanelWidth = contentWidth > 0 ? contentWidth - MIN_CHAT_WIDTH : 800

  useEffect(() => {
    if (chat.canvasPanel) {
      canvas.openCanvas(chat.canvasPanel);
    } else {
      canvas.closeCanvas();
    }
  }, [chat.canvasPanel, canvas.openCanvas, canvas.closeCanvas]);

  const planArtifactIdRef = useRef<string | null>(null);

  const openCodeAsArtifact = useCallback(
    (language: string, content: string, title?: string) => {
      createArtifact("code", content, language, title);
    },
    [createArtifact],
  );

  const openFileAsArtifact = useCallback(
    (type: ArtifactType, language: string, content: string, title?: string) => {
      createArtifact(type, content, language, title);
    },
    [createArtifact],
  );

  // Wire plan content to artifact panel when ExitPlanMode fires
  const onPlanReady = useCallback(
    (content: string | null) => {
      if (content) {
        const id = createArtifact(
          "text",
          content,
          "markdown",
          "Implementation Plan",
        );
        planArtifactIdRef.current = id;
      }
    },
    [createArtifact],
  );

  useEffect(() => {
    chat.setOnPlanReady?.(onPlanReady);
  }, [chat.setOnPlanReady, onPlanReady]);

  // Wire artifact events (show_file) to artifact panel
  const validArtifactTypes = new Set<string>(['code', 'text', 'image', 'sheet']);
  const onArtifactEvent = useCallback(
    (type: string, content: string, language?: string, title?: string) => {
      if (validArtifactTypes.has(type)) {
        createArtifact(type as ArtifactType, content, language, title);
      }
    },
    [createArtifact],
  );

  useEffect(() => {
    chat.setOnArtifactEvent?.(onArtifactEvent);
  }, [chat.setOnArtifactEvent, onArtifactEvent]);

  // Wrap approve/reject to also close the artifact panel
  const handleApprovePlan = useCallback(() => {
    chat.onApprovePlan?.();
    closePanel();
  }, [chat.onApprovePlan, closePanel]);

  const handleRequestPlanChanges = useCallback(
    (feedback: string) => {
      chat.onRequestPlanChanges?.(feedback);
      closePanel();
    },
    [chat.onRequestPlanChanges, closePanel],
  );

  // Expose callback for /plan command to reopen plan artifact
  useEffect(() => {
    if (showPlanRef) {
      showPlanRef.current = () => {
        if (planArtifactIdRef.current) {
          openArtifact(planArtifactIdRef.current);
        }
      };
    }
    return () => {
      if (showPlanRef) showPlanRef.current = null;
    };
  }, [showPlanRef, openArtifact]);

  return (
    <div className="flex h-full overflow-hidden bg-background text-foreground">
      <ConversationPicker
        sessions={conversations.sessions}
        activeSessionId={conversations.activeSessionId}
        deletingIds={conversations.deletingIds}
        onNewChat={conversations.onNewChat}
        onSelectSession={conversations.onSelectSession}
        onDeleteSession={conversations.onDeleteSession}
        onRenameSession={conversations.onRenameSession}
        agents={conversations.agents}
        onNavigateToAgent={conversations.onNavigateToAgent}
        onKillAgent={conversations.onKillAgent}
        cliSessions={conversations.cliSessions}
        viewingSessionId={conversations.viewingSessionId}
        attachedSessionId={conversations.attachedSessionId}
        onViewCliSession={conversations.onViewCliSession}
        onDetachFromSession={conversations.onDetachFromSession}
        agentDefinitions={agentDefinitions}
        agentGlobalDefs={agentGlobalDefs}
        agentProjectDefs={agentProjectDefs}
        agentShowScopeToggle={agentShowScopeToggle}
        agentHasGlobal={agentHasGlobal}
        agentHasProject={agentHasProject}
      />

      <div className="flex flex-col flex-1 min-w-0">
        <MobileChatDrawer
          sessions={conversations.sessions}
          activeSessionId={conversations.activeSessionId}
          sessionRef={effectiveSessionRef}
          title={chat.viewingSessionMeta?.title ?? chat.attachedSessionMeta?.title ?? activeTitle}
          onNewChat={conversations.onNewChat}
          onSelectSession={conversations.onSelectSession}
          onDeleteSession={conversations.onDeleteSession}
          agentDefinitions={agentDefinitions}
          agentGlobalDefs={agentGlobalDefs}
          agentProjectDefs={agentProjectDefs}
          agentShowScopeToggle={agentShowScopeToggle}
          agentHasGlobal={agentHasGlobal}
          agentHasProject={agentHasProject}
        />
        <ArtifactContext.Provider value={{ openCodeAsArtifact, openFileAsArtifact }}>
          <div className="flex flex-col flex-1 min-h-0">
            {/* Status bar */}
            <div className={`session-status-desktop${isMobile && ((isPanelOpen && activeArtifact) || (canvas.isPanelOpen && canvas.activeCanvas)) ? " hidden" : ""}`}>
              <SessionStatusBar
                sessionRef={effectiveSessionRef}
                title={chat.viewingSessionMeta?.title ?? chat.attachedSessionMeta?.title ?? activeTitle}
                viewingMeta={chat.viewingSessionMeta ?? chat.attachedSessionMeta}
                isAttached={!!chat.attachedSessionId}
                onAttach={chat.onAttachToViewed}
                onDetach={chat.onDetachFromSession}
              />
            </div>

            {/* Messages + Panel row */}
            <div ref={contentRef} className="flex flex-1 min-h-0">
              {/* Messages column — hidden on mobile when panel is open */}
              <div
                className={`flex flex-col flex-1 min-w-0${isMobile && ((isPanelOpen && activeArtifact) || (canvas.isPanelOpen && canvas.activeCanvas)) ? " hidden" : ""}`}
                style={!isMobile && ((isPanelOpen && activeArtifact) || (canvas.isPanelOpen && canvas.activeCanvas)) ? { minWidth: MIN_CHAT_WIDTH } : undefined}
              >
                <MessageList
                  ref={messageListRef}
                  messages={chat.messages}
                  isStreaming={chat.isStreaming}
                  isThinking={chat.isThinking}
                  isLoadingMessages={chat.isLoadingMessages}
                  onRespondToQuestion={chat.onRespondToQuestion}
                  onRespondToApproval={chat.onRespondToApproval}
                  planPendingApproval={!isPanelOpen && chat.planPendingApproval}
                  onApprovePlan={handleApprovePlan}
                  onRequestPlanChanges={handleRequestPlanChanges}
                  canvasSurfaces={chat.canvasSurfaces}
                  onCanvasInteraction={chat.onCanvasInteraction}
                />
              </div>

              {/* Artifact or Canvas panel */}
              {canvas.isPanelOpen && canvas.activeCanvas ? (
                <CanvasPanel
                  state={canvas.activeCanvas}
                  panelWidth={canvas.panelWidth}
                  onResize={canvas.setPanelWidth}
                  onClose={canvas.closeCanvas}
                  isMobile={isMobile}
                />
              ) : isPanelOpen && activeArtifact ? (
                <>
                  {!isMobile && (
                    <ResizeHandle
                      onResize={setPanelWidth}
                      panelWidth={panelWidth}
                      maxWidth={maxPanelWidth}
                    />
                  )}
                  <ArtifactPanel
                    artifact={activeArtifact}
                    width={isMobile ? undefined : panelWidth}
                    onClose={closePanel}
                    onUpdateContent={updateArtifact}
                    onSetVersion={setVersion}
                    planPendingApproval={chat.planPendingApproval}
                    onApprovePlan={handleApprovePlan}
                    onRequestPlanChanges={handleRequestPlanChanges}
                  />
                </>
              ) : null}
            </div>

            {/* Chat input — full width below messages + panel, hidden on mobile when panel is open */}
            <div className={isMobile && ((isPanelOpen && activeArtifact) || (canvas.isPanelOpen && canvas.activeCanvas)) ? "hidden" : ""}>
              <ChatInput
                onSend={chat.onSend}
                onStop={chat.onStop}
                isStreaming={chat.isStreaming}
                disabled={!chat.isConnected || (!!chat.viewingSessionId && !chat.attachedSessionId)}
                viewingSession={!!chat.viewingSessionId && !chat.attachedSessionId}
                onInputChange={chat.onInputChange}
                paletteItems={chat.paletteItems}
                onPaletteSelect={chat.onPaletteSelect}
                mode={chat.mode}
                onModeChange={chat.onModeChange}
                contextUsage={chat.contextUsage}
                currentBranch={chat.currentBranch}
                worktreePath={chat.worktreePath}
                projectId={projectId ?? null}
                onWorktreeChange={chat.onWorktreeChange}
                agentName={chat.activeAgent}
                onAgentChange={chat.onAgentChange}
                agentDefinitions={agentDefinitions}
                agentGlobalDefs={agentGlobalDefs}
                agentProjectDefs={agentProjectDefs}
                agentShowScopeToggle={agentShowScopeToggle}
                agentHasGlobal={agentHasGlobal}
                agentHasProject={agentHasProject}
                voiceMode={voice.voiceMode}
                voiceAvailable={voice.voiceAvailable}
                isListening={voice.isListening}
                isSpeechDetected={voice.isSpeechDetected}
                isTranscribing={voice.isTranscribing}
                voiceError={voice.voiceError}
                onToggleVoice={voice.onToggleVoice}
                isMobile={isMobile}
                onScrollToBottom={() => messageListRef.current?.scrollToBottom()}
              />
            </div>
          </div>
        </ArtifactContext.Provider>
      </div>
    </div>
  );
}
