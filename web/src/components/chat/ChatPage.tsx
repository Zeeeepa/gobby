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
import { useArtifacts } from "../../hooks/useArtifacts";
import { ArtifactContext } from "./artifacts/ArtifactContext";
import { MessageList, type MessageListHandle } from "./MessageList";
import { ChatInput } from "./ChatInput";
import { CommandBar } from "./CommandBar";
import { CommandPalette, type CommandPaletteAction } from "./CommandPalette";
import { ActiveSessionsModal } from "./ActiveSessionsModal";
import { ActivityPanel, useActivityPanel } from "../activity/ActivityPanel";
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
  // Command palette actions from App.tsx
  paletteActions?: CommandPaletteAction[];
  // Active sessions modal
  onViewAgent?: (agent: { run_id: string; session_id?: string; mode?: string }) => void;
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
  paletteActions = [],
  onViewAgent,
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
    createArtifact,
    updateArtifact,
    openArtifact,
    closePanel: closeArtifactPanel,
    setVersion,
  } = useArtifacts();

  const isMobile = useIsMobile();
  const canvas = useCanvasPanel();
  const activity = useActivityPanel();

  // Modals
  const [showCommandPalette, setShowCommandPalette] = useState(false);
  const [showActiveSessions, setShowActiveSessions] = useState(false);

  useEffect(() => {
    if (chat.canvasPanel) {
      canvas.openCanvas(chat.canvasPanel);
      // Auto-switch to canvas tab
      activity.showTab('canvas');
    } else {
      canvas.closeCanvas();
    }
  }, [chat.canvasPanel, canvas.openCanvas, canvas.closeCanvas]);

  const planArtifactIdRef = useRef<string | null>(null);

  const openCodeAsArtifact = useCallback(
    (language: string, content: string, title?: string) => {
      createArtifact("code", content, language, title);
      activity.showTab('artifacts');
    },
    [createArtifact, activity.showTab],
  );

  const openFileAsArtifact = useCallback(
    (type: ArtifactType, language: string, content: string, title?: string) => {
      createArtifact(type, content, language, title);
      activity.showTab('artifacts');
    },
    [createArtifact, activity.showTab],
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
        activity.showTab('artifacts');
      }
    },
    [createArtifact, activity.showTab],
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
        activity.showTab('artifacts');
      }
    },
    [createArtifact, activity.showTab],
  );

  useEffect(() => {
    chat.setOnArtifactEvent?.(onArtifactEvent);
  }, [chat.setOnArtifactEvent, onArtifactEvent]);

  // Plan approval — in tabbed model, don't close the panel
  const handleApprovePlan = useCallback(() => {
    chat.onApprovePlan?.();
  }, [chat.onApprovePlan]);

  const handleRequestPlanChanges = useCallback(
    (feedback: string) => {
      chat.onRequestPlanChanges?.(feedback);
    },
    [chat.onRequestPlanChanges],
  );

  // Expose callback for /plan command to reopen plan artifact
  useEffect(() => {
    if (showPlanRef) {
      showPlanRef.current = () => {
        if (planArtifactIdRef.current) {
          openArtifact(planArtifactIdRef.current);
          activity.showTab('artifacts');
        }
      };
    }
    return () => {
      if (showPlanRef) showPlanRef.current = null;
    };
  }, [showPlanRef, openArtifact, activity.showTab]);

  // Listen for palette open event from App.tsx Cmd+K handler
  useEffect(() => {
    const handler = () => setShowCommandPalette(true)
    window.addEventListener('gobby:open-command-palette', handler)
    return () => window.removeEventListener('gobby:open-command-palette', handler)
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+K — Command Palette (handled in App.tsx chord, but also direct)
      // Cmd+Shift+A — Active Sessions
      if ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'A') {
        e.preventDefault();
        setShowActiveSessions(true);
        return;
      }
      // Cmd+` — Toggle Activity Panel
      if ((e.metaKey || e.ctrlKey) && e.key === '`') {
        e.preventDefault();
        activity.togglePanel();
        return;
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [activity.togglePanel]);

  return (
    <div className="flex h-full overflow-hidden bg-background text-foreground">
      {/* Main chat column */}
      <div className="flex flex-col flex-1 min-w-[400px]">
        {/* Command Bar */}
        <CommandBar
          sessionRef={effectiveSessionRef}
          title={chat.viewingSessionMeta?.title ?? chat.attachedSessionMeta?.title ?? activeTitle}
          viewingMeta={chat.viewingSessionMeta ?? chat.attachedSessionMeta}
          isAttached={!!chat.attachedSessionId}
          onAttach={chat.onAttachToViewed}
          onDetach={chat.onDetachFromSession}
          onOpenPalette={() => setShowCommandPalette(true)}
          onOpenActiveSessions={() => setShowActiveSessions(true)}
          onNewChat={conversations.onNewChat}
          onTogglePanel={activity.togglePanel}
          agents={conversations.agents ?? []}
          agentDefinitions={agentDefinitions}
          agentGlobalDefs={agentGlobalDefs}
          agentProjectDefs={agentProjectDefs}
          agentShowScopeToggle={agentShowScopeToggle}
          agentHasGlobal={agentHasGlobal}
          agentHasProject={agentHasProject}
          isPanelPinned={activity.isPinned}
        />

        <ArtifactContext.Provider value={{ openCodeAsArtifact, openFileAsArtifact }}>
          {/* Messages */}
          <div className="flex flex-col flex-1 min-h-0">
            <MessageList
              ref={messageListRef}
              messages={chat.messages}
              isStreaming={chat.isStreaming}
              isThinking={chat.isThinking}
              isLoadingMessages={chat.isLoadingMessages}
              onRespondToQuestion={chat.onRespondToQuestion}
              onRespondToApproval={chat.onRespondToApproval}
              planPendingApproval={chat.planPendingApproval}
              onApprovePlan={handleApprovePlan}
              onRequestPlanChanges={handleRequestPlanChanges}
              canvasSurfaces={chat.canvasSurfaces}
              onCanvasInteraction={chat.onCanvasInteraction}
            />
          </div>

          {/* Chat input */}
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
        </ArtifactContext.Provider>
      </div>

      {/* Activity Panel */}
      <ActivityPanel
        isPinned={activity.isPinned}
        onPinnedChange={activity.setIsPinned}
        panelWidth={activity.panelWidth}
        onWidthChange={activity.setPanelWidth}
        activeTab={activity.activeTab}
        onTabChange={activity.setActiveTab}
        activeArtifact={activeArtifact}
        onCloseArtifact={closeArtifactPanel}
        onUpdateArtifactContent={updateArtifact}
        onSetArtifactVersion={setVersion}
        planPendingApproval={chat.planPendingApproval}
        onApprovePlan={handleApprovePlan}
        onRequestPlanChanges={handleRequestPlanChanges}
        canvasState={canvas.activeCanvas}
        onCloseCanvas={canvas.closeCanvas}
        projectId={projectId}
        onKillAgent={conversations.onKillAgent}
        isMobile={isMobile}
      />

      {/* Command Palette Modal */}
      <CommandPalette
        isOpen={showCommandPalette}
        onClose={() => setShowCommandPalette(false)}
        sessions={conversations.sessions}
        activeSessionId={conversations.activeSessionId}
        onSelectSession={conversations.onSelectSession}
        onDeleteSession={conversations.onDeleteSession}
        onRenameSession={conversations.onRenameSession}
        actions={paletteActions}
      />

      {/* Active Sessions Modal */}
      <ActiveSessionsModal
        isOpen={showActiveSessions}
        onClose={() => setShowActiveSessions(false)}
        agents={conversations.agents ?? []}
        cliSessions={conversations.cliSessions}
        onViewAgent={(agent) => {
          onViewAgent?.(agent);
          setShowActiveSessions(false);
        }}
        onKillAgent={conversations.onKillAgent}
        onViewCliSession={conversations.onViewCliSession}
      />
    </div>
  );
}
