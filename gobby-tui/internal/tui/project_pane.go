package tui

import (
	"fmt"
	"gobby-tui/internal/client"
	"io"
	"strings"

	"github.com/charmbracelet/bubbles/list"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type projectItem struct {
	id, name string
}

func (i projectItem) FilterValue() string { return i.name }

type projectDelegate struct{}

func (d projectDelegate) Height() int                             { return 1 }
func (d projectDelegate) Spacing() int                            { return 0 }
func (d projectDelegate) Update(_ tea.Msg, _ *list.Model) tea.Cmd { return nil }
func (d projectDelegate) Render(w io.Writer, m list.Model, index int, listItem list.Item) {
	i, ok := listItem.(projectItem)
	if !ok {
		return
	}

	str := fmt.Sprintf("%s", i.name)

	fn := itemStyle.Render
	if index == m.Index() {
		fn = func(s ...string) string {
			return selectedItemStyle.Render("> " + strings.Join(s, " "))
		}
	}

	fmt.Fprint(w, fn(str))
}

var (
	itemStyle         = lipgloss.NewStyle().PaddingLeft(4)
	selectedItemStyle = lipgloss.NewStyle().PaddingLeft(2).Foreground(ColorPrimary)
)

type ProjectPane struct {
	client *client.GobbyClient
	list   list.Model
	err    error
}

func NewProjectPane(c *client.GobbyClient) ProjectPane {
	items := []list.Item{}

	// Create list with default delegate
	// We want simple single line items
	l := list.New(items, projectDelegate{}, 20, 14) // width, height (will be resized)
	l.Title = "Select Project"
	l.SetShowStatusBar(false)
	l.SetFilteringEnabled(true)
	l.Styles.Title = SplashTitleStyle

	return ProjectPane{
		client: c,
		list:   l,
	}
}

func (m ProjectPane) Init() tea.Cmd {
	return nil
}

func (m ProjectPane) Update(msg tea.Msg) (ProjectPane, tea.Cmd) {
	var cmd tea.Cmd
	switch msg := msg.(type) {
	case tea.WindowSizeMsg:
		m.list.SetWidth(msg.Width)
		m.list.SetHeight(msg.Height - 4) // Leave room?

	case []client.Project:
		// Convert to list items
		items := make([]list.Item, len(msg))
		for i, p := range msg {
			items[i] = projectItem{id: p.ID, name: p.Name}
		}
		m.list.SetItems(items)

	case tea.KeyMsg:
		if msg.String() == "enter" {
			// Handled by parent usually, but we can return a specialized msg?
			// Or parent checks selected item.
			// Let's return a "ProjectSelectedMsg"
			i, ok := m.list.SelectedItem().(projectItem)
			if ok {
				return m, func() tea.Msg {
					return ProjectSelectedMsg{ID: i.id, Name: i.name}
				}
			}
		}
	}

	m.list, cmd = m.list.Update(msg)
	return m, cmd
}

func (m ProjectPane) View() string {
	return BaseStyle.Render(m.list.View())
}

type ProjectSelectedMsg struct {
	ID   string
	Name string
}

func (m *ProjectPane) FetchProjects() tea.Msg {
	projects, err := m.client.ListProjects()
	if err != nil {
		return err // Handle error better?
	}
	return projects
}
