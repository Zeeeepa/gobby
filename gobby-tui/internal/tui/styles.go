package tui

import "github.com/charmbracelet/lipgloss"

var (
	// Gobby Brand Colors
	ColorPrimary   = lipgloss.Color("#7D56F4") // Purple
	ColorSecondary = lipgloss.Color("#2DD4BF") // Teal
	ColorDark      = lipgloss.Color("#1e1e2e")
	ColorText      = lipgloss.Color("#cdd6f4")
	ColorSubtext   = lipgloss.Color("#a6adc8")

	// Base Styles
	BaseStyle = lipgloss.NewStyle().
			Foreground(ColorText)

	// Splash Styles
	SplashTitleStyle = lipgloss.NewStyle().
				Foreground(ColorPrimary).
				Bold(true).
				Padding(1, 2)

	SubtextStyle = lipgloss.NewStyle().
			Foreground(ColorSubtext)
)
