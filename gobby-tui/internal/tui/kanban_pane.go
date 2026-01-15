package tui

import (
	"fmt"
	"gobby-tui/internal/client"
	"strings"

	"github.com/charmbracelet/bubbles/list"
	tea "github.com/charmbracelet/bubbletea"
	"github.com/charmbracelet/lipgloss"
)

type KanbanPane struct {
	client  *client.GobbyClient
	cols    []list.Model
	focused int
	width   int
	height  int
	tasks   []client.Task
}

// Implement list.Item interface
type kanbanItem struct {
	task client.Task
}

func (i kanbanItem) Title() string { return i.task.Title }
func (i kanbanItem) Description() string {
	displayID := fmt.Sprintf("#%d", i.task.SeqNum)
	return displayID + " - " + "Priority: " + strings.Repeat("!", i.task.Priority)
}
func (i kanbanItem) FilterValue() string { return i.task.Title }

func NewKanbanPane(c *client.GobbyClient) KanbanPane {
	// Initialize 4 columns: Open, In Progress, Review, Closed
	cols := make([]list.Model, 4)
	titles := []string{"Open", "In Progress", "Review", "Closed"}

	for i := range cols {
		cols[i] = list.New([]list.Item{}, list.NewDefaultDelegate(), 30, 20)
		cols[i].Title = titles[i]
		cols[i].SetShowHelp(false)
	}

	return KanbanPane{
		client:  c,
		cols:    cols,
		focused: 0,
	}
}

func (m KanbanPane) Init() tea.Cmd {
	return nil // Tasks loaded via Update from main model usually
}

func (m KanbanPane) Update(msg tea.Msg) (KanbanPane, tea.Cmd) {
	var cmd tea.Cmd
	var cmds []tea.Cmd

	switch msg := msg.(type) {
	case []client.Task:
		// Reload columns
		m.tasks = msg
		m.distributeTasks()

	case tea.WindowSizeMsg:
		m.width = msg.Width
		m.height = msg.Height
		colWidth := m.width / 4
		for i := range m.cols {
			m.cols[i].SetSize(colWidth-2, m.height-5)
		}

	case tea.KeyMsg:
		switch msg.String() {
		case "h", "left":
			m.focused--
			if m.focused < 0 {
				m.focused = 0
			}
		case "l", "right":
			m.focused++
			if m.focused >= len(m.cols) {
				m.focused = len(m.cols) - 1
			}
		case "H": // Move Task Left
			if m.focused > 0 {
				selectedItem := m.cols[m.focused].SelectedItem()
				if selectedItem != nil {
					item := selectedItem.(kanbanItem)
					newStatus := m.getStatusForColumn(m.focused - 1)

					// Optimistic update
					item.task.Status = newStatus
					m.updateTaskStatus(item.task.ID, newStatus)

					// Re-distribute (simplistic, could be optimized)
					for i, t := range m.tasks {
						if t.ID == item.task.ID {
							m.tasks[i].Status = newStatus
							break
						}
					}
					m.distributeTasks()
					m.focused--
				}
			}
		case "L": // Move Task Right
			if m.focused < len(m.cols)-1 {
				selectedItem := m.cols[m.focused].SelectedItem()
				if selectedItem != nil {
					item := selectedItem.(kanbanItem)
					newStatus := m.getStatusForColumn(m.focused + 1)

					// Optimistic update
					item.task.Status = newStatus
					m.updateTaskStatus(item.task.ID, newStatus)

					for i, t := range m.tasks {
						if t.ID == item.task.ID {
							m.tasks[i].Status = newStatus
							break
						}
					}
					m.distributeTasks()
					m.focused++
				}
			}
		case "d": // Delete
			selectedItem := m.cols[m.focused].SelectedItem()
			if selectedItem != nil {
				item := selectedItem.(kanbanItem)
				m.deleteTask(item.task.ID)

				// Remove from local list
				var newTasks []client.Task
				for _, t := range m.tasks {
					if t.ID != item.task.ID {
						newTasks = append(newTasks, t)
					}
				}
				m.tasks = newTasks
				m.distributeTasks()
			}
		}
	}

	m.cols[m.focused], cmd = m.cols[m.focused].Update(msg)
	cmds = append(cmds, cmd)

	return m, tea.Batch(cmds...)
}

func (m KanbanPane) getStatusForColumn(colIndex int) string {
	switch colIndex {
	case 0:
		return "open"
	case 1:
		return "in_progress"
	case 2:
		return "review"
	case 3:
		return "closed"
	default:
		return "open"
	}
}

func (m KanbanPane) updateTaskStatus(id, status string) {
	// Run in background (goroutine) or tea.Cmd?
	// For now, fire and forget in goroutine to not block UI,
	// ideally should be a Cmd that returns Msg on success/fail
	go func() {
		m.client.UpdateTask(id, status)
	}()
}

func (m KanbanPane) deleteTask(id string) {
	go func() {
		m.client.DeleteTask(id)
	}()
}

func (m KanbanPane) View() string {
	var views []string
	for i, col := range m.cols {
		style := lipgloss.NewStyle().
			Border(lipgloss.RoundedBorder()).
			Padding(0, 1).
			Width((m.width / 4) - 2)

		if i == m.focused {
			style = style.BorderForeground(ColorPrimary)
		} else {
			style = style.BorderForeground(ColorSubtext)
		}

		views = append(views, style.Render(col.View()))
	}
	return lipgloss.JoinHorizontal(lipgloss.Top, views...)
}

func (m *KanbanPane) distributeTasks() {
	// Clear lists
	buckets := make([][]list.Item, 4)

	for _, t := range m.tasks {
		item := kanbanItem{task: t}
		switch {
		case strings.Contains(strings.ToLower(t.Status), "open"):
			buckets[0] = append(buckets[0], item)
		case strings.Contains(strings.ToLower(t.Status), "progress"):
			buckets[1] = append(buckets[1], item)
		case strings.Contains(strings.ToLower(t.Status), "review"):
			buckets[2] = append(buckets[2], item)
		case strings.Contains(strings.ToLower(t.Status), "closed"):
			buckets[3] = append(buckets[3], item)
		default:
			buckets[0] = append(buckets[0], item)
		}
	}

	for i := range m.cols {
		m.cols[i].SetItems(buckets[i])
	}
}
