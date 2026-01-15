package tui

import (
	"fmt"
	"gobby-tui/internal/client"
	"strings"

	"github.com/charmbracelet/bubbles/textarea"
	"github.com/charmbracelet/bubbles/viewport"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type ChatPane struct {
	client    *client.GobbyClient
	viewport  viewport.Model
	textarea  textarea.Model
	messages  []string
	sessionID string
	width     int
	height    int
	err       error
}

func NewChatPane(c *client.GobbyClient) ChatPane {
	ta := textarea.New()
	ta.Placeholder = "Ask about your tasks..."
	ta.Focus()
	ta.Prompt = "┃ "
	ta.CharLimit = 280
	ta.SetWidth(30)
	ta.SetHeight(3)
	ta.FocusedStyle.CursorLine = lipgloss.NewStyle()
	ta.ShowLineNumbers = false

	vp := viewport.New(30, 5)
	vp.SetContent("Welcome to Gobby Chat!\nInitializing session...")

	return ChatPane{
		client:   c,
		textarea: ta,
		viewport: vp,
		messages: []string{},
	}
}

type sessionMsg string
type chatResponseMsg string
type chatErrorMsg error

func (m ChatPane) Init() tea.Cmd {
	return tea.Batch(
		textarea.Blink,
		func() tea.Msg {
			sessions, err := m.client.ListSessions()
			if err != nil {
				return chatErrorMsg(err)
			}
			// Pick simple recent session or hardcode parent logic
			// For TUI, we might want to be our own session eventually,
			// but linking to latest active usage is good for now.
			if len(sessions) > 0 {
				return sessionMsg(sessions[0].ID)
			}
			return chatErrorMsg(fmt.Errorf("no active sessions found"))
		},
	)
}

func (m ChatPane) Update(msg tea.Msg) (ChatPane, tea.Cmd) {
	var (
		tiCmd tea.Cmd
		vpCmd tea.Cmd
		cmds  []tea.Cmd
	)

	m.textarea, tiCmd = m.textarea.Update(msg)
	cmds = append(cmds, tiCmd)
	m.viewport, vpCmd = m.viewport.Update(msg)
	cmds = append(cmds, vpCmd)

	switch msg := msg.(type) {
	case sessionMsg:
		m.sessionID = string(msg)
		m.viewport.SetContent("Connected to session: " + m.sessionID[:8] + "...\nAsk me to manage your tasks.")

	case chatResponseMsg:
		m.messages = append(m.messages, "Agent: "+string(msg))
		m.viewport.SetContent(strings.Join(m.messages, "\n"))
		m.viewport.GotoBottom()
		m.textarea.Reset()
		m.textarea.Placeholder = "Ask about your tasks..."
		m.textarea.Focus()

	case chatErrorMsg:
		m.messages = append(m.messages, fmt.Sprintf("Error: %v", msg))
		m.viewport.SetContent(strings.Join(m.messages, "\n"))
		m.viewport.GotoBottom()

	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

		m.viewport.Width = m.width
		m.viewport.Height = m.height - m.textarea.Height() - 4 // Padding
		m.textarea.SetWidth(m.width)

	case tea.KeyMsg:
		switch msg.Type {
		case tea.KeyEnter:
			if m.textarea.Value() != "" {
				userMsg := m.textarea.Value()
				m.messages = append(m.messages, "You: "+userMsg)
				m.viewport.SetContent(strings.Join(m.messages, "\n"))
				m.viewport.GotoBottom()

				// Clear input immediately, but disable until reply?
				// For now, keep it simple.
				m.textarea.Reset()

				// Async chat call
				if m.sessionID != "" {
					cmds = append(cmds, func() tea.Msg {
						resp, err := m.client.Chat(userMsg, m.sessionID)
						if err != nil {
							return chatErrorMsg(err)
						}
						return chatResponseMsg(resp)
					})
				} else {
					m.messages = append(m.messages, "Error: No session ID")
				}
			}
		}
	}

	return m, tea.Batch(cmds...)
}

func (m ChatPane) View() string {
	return fmt.Sprintf(
		"%s\n\n%s",
		m.viewport.View(),
		m.textarea.View(),
	)
}
