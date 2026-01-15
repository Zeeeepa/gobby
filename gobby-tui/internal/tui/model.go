package tui

import (
	"gobby-tui/internal/client"

	tea "github.com/charmbracelet/bubbletea"
)

type MainModel struct {
	client      *client.GobbyClient
	splash      SplashModel
	taskPane    TaskPane
	kanbanPane  KanbanPane
	chatPane    ChatPane
	projectPane ProjectPane
	activeView  string // "splash", "list", "kanban", "chat", "projects"
	quitting    bool
	width       int
	height      int
}

func NewMainModel(c *client.GobbyClient) MainModel {
	return MainModel{
		client:      c,
		splash:      NewSplashModel(),
		taskPane:    NewTaskPane(c),
		kanbanPane:  NewKanbanPane(c),
		chatPane:    NewChatPane(c),
		projectPane: NewProjectPane(c),
		activeView:  "splash",
	}
}

func (m MainModel) Init() tea.Cmd {
	return tea.Batch(
		m.splash.Init(),
		m.taskPane.Init(),
		m.kanbanPane.Init(),
		m.chatPane.Init(),
	)
}

func (m MainModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	var cmd tea.Cmd
	var cmds []tea.Cmd

	switch msg := msg.(type) {
	case tea.KeyMsg:
		if msg.String() == "ctrl+c" {
			m.quitting = true
			return m, tea.Quit
		}

		// Ctrl+p to open project switcher
		if msg.String() == "ctrl+p" {
			m.activeView = "projects"
			// Trigger fetch
			return m, func() tea.Msg {
				projects, err := m.client.ListProjects()
				if err != nil {
					return nil // Log?
				}
				return projects
			}
		}

		// Tab cycling logic (skip splash and projects)
		if msg.String() == "tab" && m.activeView != "splash" && m.activeView != "projects" {
			switch m.activeView {
			case "list":
				m.activeView = "kanban"
				m.kanbanPane.tasks = m.taskPane.tasks
				m.kanbanPane.distributeTasks()
			case "kanban":
				m.activeView = "chat"
				// Chat doesn't need task sync yet
			case "chat":
				m.activeView = "list"
			}
			return m, nil
		}
	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height

		// Update sub-models size
		tableHeight := m.height - 10 // More padding for chat
		if tableHeight < 5 {
			tableHeight = 5
		}
		m.taskPane.table.SetHeight(tableHeight)

		m.kanbanPane.Update(msg)
		m.chatPane.Update(msg)
		m.projectPane.Update(msg)

	case ProjectSelectedMsg:
		// Handle project selection
		m.client.SetProject(msg.ID, msg.Name)
		m.activeView = "list" // specific choice: go to list?

		// Trigger refresh of tasks
		return m, m.taskPane.fetchTasks
	}

	if m.activeView == "splash" {
		updatedSplash, cmd := m.splash.Update(msg)
		m.splash = updatedSplash.(SplashModel)
		if m.splash.done {
			m.activeView = "list"
		}
		return m, cmd
	}

	if m.activeView == "list" {
		m.taskPane, cmd = m.taskPane.Update(msg)
		cmds = append(cmds, cmd)
	} else if m.activeView == "kanban" {
		m.kanbanPane, cmd = m.kanbanPane.Update(msg)
		cmds = append(cmds, cmd)
	} else if m.activeView == "chat" {
		m.chatPane, cmd = m.chatPane.Update(msg)
		cmds = append(cmds, cmd)
	} else if m.activeView == "projects" {
		m.projectPane, cmd = m.projectPane.Update(msg)
		cmds = append(cmds, cmd)
	}

	// Global Quit (allow q in chat if not typing?)
	// Actually chat usually captures all keys.
	// We only allow global quit if NOT in chat, or if input is empty/esc?
	// For now, simpler: ctrl+c is force quit. 'q' only works in list/kanban/splash.
	switch msg := msg.(type) {
	case tea.KeyMsg:
		if m.activeView != "chat" && m.activeView != "projects" && msg.String() == "q" && !m.taskPane.filtering {
			m.quitting = true
			return m, tea.Quit
		}
	}

	return m, tea.Batch(cmds...)
}

func (m MainModel) View() string {
	if m.quitting {
		return "Bye!\n"
	}
	if m.activeView == "splash" {
		return m.splash.View()
	}

	if m.activeView == "projects" {
		return m.projectPane.View()
	}

	header := SplashTitleStyle.Render(" GOBBY TASKS ") + SubtextStyle.Render(" [Tab] Cycle Views | [Ctrl+p] Projects")
	if m.client.ProjectID != "" {
		name := m.client.ProjectName
		if name == "" {
			name = m.client.ProjectID
		}
		header += SubtextStyle.Render(" | Prj: " + name)
	} else {
		header += SubtextStyle.Render(" | Prj: None")
	}

	var content string
	switch m.activeView {
	case "list":
		content = m.taskPane.View()
	case "kanban":
		content = m.kanbanPane.View()
	case "chat":
		content = m.chatPane.View()
	}

	return BaseStyle.Render(
		"\n" + header + "\n" + content,
	)
}
