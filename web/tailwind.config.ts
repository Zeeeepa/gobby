export default {
  content: ['./src/components/chat-v2/**/*.{ts,tsx}'],
  important: true,
  corePlugins: { preflight: false },
  theme: {
    extend: {
      colors: {
        background: '#0a0a0a',
        foreground: '#e5e5e5',
        muted: { DEFAULT: '#1a1a1a', foreground: '#a3a3a3' },
        accent: { DEFAULT: '#3b82f6', foreground: '#fff', hover: '#2563eb' },
        border: '#262626',
        destructive: { DEFAULT: '#7f1d1d', foreground: '#f87171' },
        warning: { DEFAULT: '#78350f', foreground: '#f59e0b' },
        success: { DEFAULT: '#14532d', foreground: '#22c55e' },
      },
    },
  },
}
