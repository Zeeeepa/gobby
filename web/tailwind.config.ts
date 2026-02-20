import type { Config } from 'tailwindcss'

export default {
  content: ['./src/**/*.{ts,tsx}'],
  important: true,
  theme: {
    extend: {
      colors: {
        background: 'var(--bg-primary)',
        foreground: 'var(--text-primary)',
        muted: { DEFAULT: 'var(--bg-tertiary)', foreground: 'var(--text-secondary)' },
        accent: { DEFAULT: 'var(--accent)', foreground: 'var(--accent-foreground)', hover: 'var(--accent-hover)' },
        border: 'var(--border)',
        destructive: { DEFAULT: 'var(--color-destructive)', foreground: 'var(--color-destructive-foreground)' },
        warning: { DEFAULT: 'var(--color-warning)', foreground: 'var(--color-warning-foreground)' },
        success: { DEFAULT: 'var(--color-success)', foreground: 'var(--color-success-foreground)' },
      },
    },
  },
} satisfies Config
