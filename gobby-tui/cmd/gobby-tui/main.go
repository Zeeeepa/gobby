package main

import (
	"fmt"
	"os"

	"gobby-tui/internal/client"
	"gobby-tui/internal/tui"

	tea "github.com/charmbracelet/bubbletea"
)

func main() {
	c := client.NewGobbyClient()
	p := tea.NewProgram(tui.NewMainModel(c), tea.WithAltScreen())
	if _, err := p.Run(); err != nil {
		fmt.Printf("Alas, there's been an error: %v", err)
		os.Exit(1)
	}
}
