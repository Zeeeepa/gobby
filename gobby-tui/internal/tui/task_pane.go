package tui

import (
	"fmt"
	"gobby-tui/internal/client"
	"strings"

	"github.com/charmbracelet/bubbles/table"
	"github.com/charmbracelet/bubbles/textinput"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type TaskPane struct {
	client    *client.GobbyClient
	table     table.Model
	input     textinput.Model
	allTasks  []client.Task
	tasks     []client.Task
	filtering bool
	err       error
}

func NewTaskPane(c *client.GobbyClient) TaskPane {
	columns := []table.Column{
		{Title: "ID", Width: 10},
		{Title: "Title", Width: 40},
		{Title: "Status", Width: 15},
		{Title: "Pri", Width: 5},
	}

	t := table.New(
		table.WithColumns(columns),
		table.WithFocused(true),
		table.WithHeight(10),
	)

	s := table.DefaultStyles()
	s.Header = s.Header.
		BorderStyle(lipgloss.NormalBorder()).
		BorderForeground(ColorSecondary).
		BorderBottom(true).
		Bold(true)
	s.Selected = s.Selected.
		Foreground(ColorText).
		Background(ColorPrimary).
		Bold(false)
	t.SetStyles(s)

	ti := textinput.New()
	ti.Placeholder = "Filter tasks..."
	ti.CharLimit = 20

	return TaskPane{
		client: c,
		table:  t,
		input:  ti,
	}
}

func (m TaskPane) Init() tea.Cmd {
	return m.fetchTasks
}

func (m TaskPane) Update(msg tea.Msg) (TaskPane, tea.Cmd) {
	var cmd tea.Cmd
	switch msg := msg.(type) {
	case []client.Task:
		m.allTasks = msg
		m.filterTasks()

	case tea.KeyMsg:
		if m.filtering {
			switch msg.String() {
			case "enter", "esc":
				m.filtering = false
				m.input.Blur()
				return m, nil
			}
			m.input, cmd = m.input.Update(msg)
			m.filterTasks()
			return m, cmd
		}

		switch msg.String() {
		case "/":
			m.filtering = true
			m.input.Focus()
			return m, textinput.Blink
		case "r":
			return m, m.fetchTasks
		}
	}

	m.table, cmd = m.table.Update(msg)
	return m, cmd
}

func (m TaskPane) View() string {
	if m.err != nil {
		return fmt.Sprintf("Error fetching tasks: %v", m.err)
	}

	view := BaseStyle.Render(m.table.View())

	if m.filtering {
		view += "\n" + m.input.View()
	} else if m.input.Value() != "" {
		view += "\n" + SubtextStyle.Render("Filter: "+m.input.Value())
	}

	return view
}

func (m *TaskPane) filterTasks() {
	term := strings.ToLower(m.input.Value())
	var filtered []client.Task
	for _, t := range m.allTasks {
		if strings.Contains(strings.ToLower(t.Title), term) ||
			strings.Contains(strings.ToLower(t.ID), term) {
			filtered = append(filtered, t)
		}
	}
	m.tasks = filtered

	rows := make([]table.Row, len(m.tasks))
	for i, t := range m.tasks {
		displayID := fmt.Sprintf("#%d", t.SeqNum)
		if t.SeqNum == 0 {
			// Fallback if seq_num missing (unlikely from DB but possible)
			displayID = t.ID[:8]
		}
		rows[i] = table.Row{
			displayID,
			t.Title,
			t.Status,
			fmt.Sprintf("%d", t.Priority),
		}
	}
	m.table.SetRows(rows)
}

func (m TaskPane) fetchTasks() tea.Msg {
	tasks, err := m.client.ListReadyTasks()
	if err != nil {
		return err
	}
	return tasks
}
