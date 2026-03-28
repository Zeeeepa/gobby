import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, act, waitFor } from '@testing-library/react'
import App from '../App'

// Mock all hooks used by App.tsx
vi.mock('../hooks/useAuth', () => ({
  useAuth: vi.fn(() => ({
    authRequired: false,
    authenticated: true,
    loading: false,
    login: vi.fn(),
    logout: vi.fn(),
  })),
}))

const mockSendProjectChange = vi.fn()
const mockSetProjectIdRef = vi.fn()

vi.mock('../hooks/useChat', () => ({
  useChat: vi.fn(() => ({
    messages: [],
    conversationId: 'conv-123',
    conversationSwitchKey: 0,
    sessionRef: null,
    dbSessionId: null,
    currentBranch: null,
    worktreePath: null,
    isConnected: true,
    isStreaming: false,
    isThinking: false,
    isLoadingMessages: false,
    contextUsage: { totalInputTokens: 0, outputTokens: 0, contextWindow: null },
    sendMessage: vi.fn(),
    sendMode: vi.fn(),
    sendProjectChange: mockSendProjectChange,
    setProjectIdRef: mockSetProjectIdRef,
    sendWorktreeChange: vi.fn(),
    stopStreaming: vi.fn(),
    clearHistory: vi.fn(),
    deleteConversation: vi.fn(),
    respondToQuestion: vi.fn(),
    respondToApproval: vi.fn(),
    planPendingApproval: false,
    approvePlan: vi.fn(),
    requestPlanChanges: vi.fn(),
    switchConversation: vi.fn(),
    startNewChat: vi.fn(),
    continueSessionInChat: vi.fn(),
    setOnModeChanged: vi.fn(),
    setOnPlanReady: vi.fn(),
    addSystemMessage: vi.fn(),
    viewSession: vi.fn(),
    clearViewingSession: vi.fn(),
    viewingSessionId: null,
    viewingSessionMeta: null,
    attachToViewed: vi.fn(),
    detachFromSession: vi.fn(),
    attachedSessionId: null,
    attachedSessionMeta: null,
    wsRef: { current: null },
    handleVoiceMessageRef: { current: null },
    handleBinaryMessageRef: { current: null },
    canvasSurfaces: new Map(),
    canvasPanel: null,
    onCanvasInteraction: vi.fn(),
    setOnChatDeleted: vi.fn(),
    activeAgent: 'default-web-chat',
    sendAgentChange: vi.fn(),
  })),
}))

vi.mock('../hooks/useVoice', () => ({
  useVoice: vi.fn(() => ({})),
}))

vi.mock('../hooks/useSettings', () => ({
  useSettings: vi.fn(() => ({
    settings: { model: 'gpt-4', chatMode: 'plan' },
    updateFontSize: vi.fn(),
    updateModel: vi.fn(),
    updateChatMode: vi.fn(),
    updateTheme: vi.fn(),
    updateDefaultChatMode: vi.fn(),
    resetSettings: vi.fn(),
  })),
}))

vi.mock('../hooks/useTerminal', () => ({
  useTerminal: vi.fn(() => ({ agents: [], refreshAgents: vi.fn() })),
}))

vi.mock('../hooks/useTmuxSessions', () => ({
  useTmuxSessions: vi.fn(() => ({})),
}))

vi.mock('../hooks/useMcp', () => ({
  useMcp: vi.fn(() => ({ servers: [], toolsByServer: {}, fetchToolSchema: vi.fn() })),
}))

vi.mock('../hooks/useSkills', () => ({
  useSkills: vi.fn(() => ({ skills: [] })),
}))

vi.mock('../hooks/useColonAutocomplete', () => ({
  useColonAutocomplete: vi.fn(() => ({
    paletteItems: [],
    filterInput: vi.fn(),
    parseColonCommand: vi.fn(),
    resolveInjectContext: vi.fn(),
  })),
}))

vi.mock('../hooks/useSessions', () => ({
  useSessions: vi.fn(() => ({
    projects: [{ id: 'p1', name: 'Personal' }],
    sessions: [],
    isLoading: false,
    refresh: vi.fn(),
    setFilters: vi.fn(),
    filteredSessions: [],
  })),
}))

vi.mock('../hooks/useAgentDefinitions', () => ({
  useAgentDefinitions: vi.fn(() => ({})),
}))

// Mock CSS imports
vi.mock('./App.css', () => ({}))

// Mock lazy components
vi.mock('./components/dashboard/DashboardPage', () => ({ DashboardPage: () => <div>Dashboard</div> }))
vi.mock('./components/chat/ChatPage', () => ({ ChatPage: () => <div>Chat</div> }))
vi.mock('./components/sessions/SessionsPage', () => ({ SessionsPage: () => <div>Sessions</div> }))

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation(query => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(), // Deprecated
    removeListener: vi.fn(), // Deprecated
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

describe('App wiring', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Mock fetch for UI settings
    globalThis.fetch = vi.fn(() => Promise.resolve({
      ok: true,
      json: () => Promise.resolve({ selectedProjectId: 'p1' })
    })) as any
  })

  it('calls sendProjectChange and setProjectIdRef when effectiveProjectId is set', async () => {
    await act(async () => {
      render(<App />)
    })

    await waitFor(() => {
      expect(mockSetProjectIdRef).toHaveBeenCalled()
      expect(mockSendProjectChange).toHaveBeenCalled()
    })
  })
})
