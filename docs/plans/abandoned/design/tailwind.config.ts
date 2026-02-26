/**
 * Gobby Design System - Tailwind Configuration
 *
 * Color palette derived from logo.png:
 * - Primary Green: #6CBF47 (goblin character)
 * - Circuit Purple: #9B59B6
 * - Circuit Blue: #3498DB
 * - Circuit Teal: #4ECDC4
 * - Background Black: #0C0C0C
 *
 * Design Direction: Precision & Density + Utility & Function
 * Inspired by: Linear, Raycast, GitHub
 */

import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./src/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      // ========================================
      // COLOR SYSTEM
      // ========================================
      colors: {
        // Background layers (dark-first)
        background: {
          DEFAULT: "#0C0C0C", // Near-black base
          raised: "#161616", // Cards, panels
          elevated: "#1C1C1C", // Modals, dropdowns
          overlay: "rgba(0, 0, 0, 0.8)", // Backdrop
        },

        // Surface colors for components
        surface: {
          DEFAULT: "#161616",
          hover: "#1E1E1E",
          active: "#252525",
          muted: "#111111",
        },

        // Border system
        border: {
          DEFAULT: "rgba(255, 255, 255, 0.08)",
          subtle: "rgba(255, 255, 255, 0.05)",
          strong: "rgba(255, 255, 255, 0.12)",
          focus: "#6CBF47", // Green focus ring
        },

        // Text hierarchy
        text: {
          primary: "#FAFAFA",
          secondary: "#A0A0A0",
          muted: "#666666",
          faint: "#444444",
          inverse: "#0C0C0C",
        },

        // Primary brand color (Gobby Green)
        primary: {
          DEFAULT: "#6CBF47",
          hover: "#7DCF58",
          active: "#5CAF37",
          muted: "rgba(108, 191, 71, 0.15)",
          50: "#F0F9EC",
          100: "#D9F0CE",
          200: "#B3E19D",
          300: "#8DD26C",
          400: "#6CBF47", // Base
          500: "#5AAF35",
          600: "#489929",
          700: "#38751F",
          800: "#285217",
          900: "#1A3610",
        },

        // Accent colors (from circuit board pattern)
        purple: {
          DEFAULT: "#9B59B6",
          hover: "#A769C0",
          muted: "rgba(155, 89, 182, 0.15)",
          50: "#F5EEF8",
          100: "#E8D5F0",
          200: "#D5ABE0",
          300: "#C182D0",
          400: "#9B59B6",
          500: "#8E4FAA",
          600: "#7B4394",
          700: "#5E3371",
          800: "#42244F",
          900: "#26152D",
        },

        blue: {
          DEFAULT: "#3498DB",
          hover: "#48A6E5",
          muted: "rgba(52, 152, 219, 0.15)",
          50: "#EBF5FC",
          100: "#CEE7F7",
          200: "#9DD0EF",
          300: "#6CB9E7",
          400: "#3498DB",
          500: "#2980B9",
          600: "#216897",
          700: "#1A5075",
          800: "#123853",
          900: "#0B2131",
        },

        teal: {
          DEFAULT: "#4ECDC4",
          hover: "#5FD7CF",
          muted: "rgba(78, 205, 196, 0.15)",
          50: "#EDFBFA",
          100: "#D1F5F2",
          200: "#A3EBE5",
          300: "#75E1D8",
          400: "#4ECDC4",
          500: "#3DBDB4",
          600: "#2F9A93",
          700: "#247772",
          800: "#195451",
          900: "#0F3230",
        },

        // Semantic colors
        success: {
          DEFAULT: "#6CBF47", // Matches primary
          muted: "rgba(108, 191, 71, 0.15)",
        },

        warning: {
          DEFAULT: "#F5A623",
          muted: "rgba(245, 166, 35, 0.15)",
        },

        error: {
          DEFAULT: "#E74C3C",
          muted: "rgba(231, 76, 60, 0.15)",
        },

        info: {
          DEFAULT: "#3498DB",
          muted: "rgba(52, 152, 219, 0.15)",
        },

        // Task status colors
        status: {
          open: "#A0A0A0", // Gray
          "in-progress": "#3498DB", // Blue
          blocked: "#E74C3C", // Red
          closed: "#6CBF47", // Green
          failed: "#E74C3C", // Red
          escalated: "#F5A623", // Orange
        },

        // Task type colors
        taskType: {
          bug: "#E74C3C",
          feature: "#9B59B6",
          task: "#3498DB",
          epic: "#4ECDC4",
          chore: "#666666",
        },

        // Agent provider colors
        provider: {
          claude: "#D97706", // Anthropic orange
          gemini: "#4285F4", // Google blue
          codex: "#00A67E", // OpenAI green
        },

        // Memory type colors (matching viz.py)
        memory: {
          fact: "#4CAF50",
          preference: "#2196F3",
          pattern: "#FF9800",
          context: "#9C27B0",
        },
      },

      // ========================================
      // TYPOGRAPHY
      // ========================================
      fontFamily: {
        sans: [
          "Inter",
          "-apple-system",
          "BlinkMacSystemFont",
          "Segoe UI",
          "Roboto",
          "sans-serif",
        ],
        mono: [
          "JetBrains Mono",
          "Fira Code",
          "Monaco",
          "Consolas",
          "monospace",
        ],
      },

      fontSize: {
        // Using design-principles scale
        "2xs": ["0.6875rem", { lineHeight: "1rem" }], // 11px
        xs: ["0.75rem", { lineHeight: "1rem" }], // 12px
        sm: ["0.8125rem", { lineHeight: "1.25rem" }], // 13px
        base: ["0.875rem", { lineHeight: "1.5rem" }], // 14px
        md: ["1rem", { lineHeight: "1.5rem" }], // 16px
        lg: ["1.125rem", { lineHeight: "1.75rem" }], // 18px
        xl: ["1.5rem", { lineHeight: "2rem" }], // 24px
        "2xl": ["2rem", { lineHeight: "2.5rem" }], // 32px
      },

      letterSpacing: {
        tight: "-0.02em",
        normal: "0",
        wide: "0.02em",
      },

      // ========================================
      // SPACING (4px grid)
      // ========================================
      spacing: {
        px: "1px",
        0: "0",
        0.5: "2px",
        1: "4px",
        1.5: "6px",
        2: "8px",
        2.5: "10px",
        3: "12px",
        4: "16px",
        5: "20px",
        6: "24px",
        7: "28px",
        8: "32px",
        9: "36px",
        10: "40px",
        12: "48px",
        14: "56px",
        16: "64px",
      },

      // ========================================
      // BORDER RADIUS (consistent system)
      // ========================================
      borderRadius: {
        none: "0",
        sm: "4px",
        DEFAULT: "6px",
        md: "8px",
        lg: "12px",
        full: "9999px",
      },

      // ========================================
      // SHADOWS (borders-first approach for dark mode)
      // ========================================
      boxShadow: {
        none: "none",
        // Subtle lift for cards
        sm: "0 1px 2px rgba(0, 0, 0, 0.3)",
        // Standard elevation
        DEFAULT: "0 1px 3px rgba(0, 0, 0, 0.4), 0 1px 2px rgba(0, 0, 0, 0.3)",
        // Modals and dropdowns
        md: "0 4px 6px rgba(0, 0, 0, 0.4), 0 2px 4px rgba(0, 0, 0, 0.3)",
        // Popovers
        lg: "0 10px 15px rgba(0, 0, 0, 0.4), 0 4px 6px rgba(0, 0, 0, 0.3)",
        // Focus rings
        focus: "0 0 0 2px rgba(108, 191, 71, 0.3)",
        "focus-error": "0 0 0 2px rgba(231, 76, 60, 0.3)",
      },

      // ========================================
      // ANIMATION
      // ========================================
      transitionDuration: {
        fast: "100ms",
        DEFAULT: "150ms",
        slow: "250ms",
      },

      transitionTimingFunction: {
        DEFAULT: "cubic-bezier(0.25, 1, 0.5, 1)",
        smooth: "cubic-bezier(0.4, 0, 0.2, 1)",
      },

      animation: {
        "fade-in": "fadeIn 150ms cubic-bezier(0.25, 1, 0.5, 1)",
        "slide-up": "slideUp 150ms cubic-bezier(0.25, 1, 0.5, 1)",
        "slide-down": "slideDown 150ms cubic-bezier(0.25, 1, 0.5, 1)",
        pulse: "pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite",
        spin: "spin 1s linear infinite",
      },

      keyframes: {
        fadeIn: {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        slideUp: {
          "0%": { transform: "translateY(4px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        slideDown: {
          "0%": { transform: "translateY(-4px)", opacity: "0" },
          "100%": { transform: "translateY(0)", opacity: "1" },
        },
        pulse: {
          "0%, 100%": { opacity: "1" },
          "50%": { opacity: "0.5" },
        },
        spin: {
          "0%": { transform: "rotate(0deg)" },
          "100%": { transform: "rotate(360deg)" },
        },
      },

      // ========================================
      // Z-INDEX SYSTEM
      // ========================================
      zIndex: {
        base: "0",
        raised: "10",
        dropdown: "100",
        sticky: "200",
        modal: "300",
        popover: "400",
        tooltip: "500",
        toast: "600",
      },
    },
  },
  plugins: [],
};

export default config;
