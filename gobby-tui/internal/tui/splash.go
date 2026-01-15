package tui

import (
	"fmt"
	"math/rand"
	"strings"
	"time"

	tea "github.com/charmbracelet/bubbletea"
)

type SplashModel struct {
	width      int
	height     int
	asciiArt   []string
	revealed   []string
	percent    float64
	done       bool
	logoLoaded bool
}

type TickMsg time.Time

func NewSplashModel() SplashModel {
	return SplashModel{
		asciiArt: []string{
			"  ________      ___.  ___.          ",
			" /  _____/  ____\\_ |__\\_ |__ ___.__.",
			"/   \\  ___ /  _ \\| __ \\| __ <   |  |",
			"\\    \\_\\  (  <_> ) \\_\\ \\ \\_\\ \\___  |",
			" \\______  /\\____/|___  /___  / ____|",
			"        \\/           \\/    \\/\\/     ",
			"",
			"      [ Gobby Agent Protocol v1.0 ]",
		},
		revealed: make([]string, 8),
		percent:  0.0,
	}
}

func (m SplashModel) Init() tea.Cmd {
	// Initialize revealed lines with random chars of same length
	for i, line := range m.asciiArt {
		m.revealed[i] = randomString(len(line))
	}
	return tickCmd()
}

func (m SplashModel) Update(msg tea.Msg) (tea.Model, tea.Cmd) {
	switch msg := msg.(type) {
	case tea.KeyMsg:
		if msg.String() == "q" || msg.String() == "esc" || msg.String() == "enter" {
			m.done = true
			return m, nil
		}
	case TickMsg:
		if m.percent >= 1.0 {
			m.done = true
			return m, nil
		}

		m.percent += 0.02
		m.updateReveal()
		return m, tickCmd()
	}
	return m, nil
}

func (m *SplashModel) updateReveal() {
	for i, targetLine := range m.asciiArt {
		currentLine := []rune(m.revealed[i])
		targetRunes := []rune(targetLine)

		for j, char := range targetRunes {
			// Randomly lock in characters based on percent
			if rand.Float64() < m.percent || currentLine[j] == char {
				currentLine[j] = char
			} else {
				// Glitch effect
				currentLine[j] = rune(rand.Intn(95) + 32)
			}
		}
		m.revealed[i] = string(currentLine)
	}
}

func (m SplashModel) View() string {
	if m.done {
		return ""
	}

	s := strings.Builder{}
	s.WriteString("\n\n")
	for _, line := range m.revealed {
		s.WriteString("   " + SplashTitleStyle.Render(line) + "\n")
	}
	s.WriteString("\n   " + fmt.Sprintf("Initializing System... [%d%%]", int(m.percent*100)))
	return s.String()
}

func tickCmd() tea.Cmd {
	return tea.Tick(time.Millisecond*50, func(t time.Time) tea.Msg {
		return TickMsg(t)
	})
}

func randomString(n int) string {
	b := make([]byte, n)
	for i := range b {
		b[i] = byte(rand.Intn(95) + 32)
	}
	return string(b)
}
