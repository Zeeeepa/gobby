import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const GOBBY_HTTP_PORT = process.env.GOBBY_DAEMON_PORT || '60887'
const GOBBY_WS_PORT = process.env.GOBBY_WS_PORT || '60888'
const GOBBY_UI_HOST = process.env.GOBBY_UI_HOST || 'localhost'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    dedupe: ['@codemirror/state', '@codemirror/view', '@codemirror/language'],
  },
  server: {
    host: GOBBY_UI_HOST,
    port: 60889,
    allowedHosts: GOBBY_UI_HOST === '0.0.0.0' ? true : ['localhost', '.ts.net', ...(process.env.VITE_ALLOWED_HOST ? [process.env.VITE_ALLOWED_HOST] : [])],
    proxy: {
      // Proxy API requests to Gobby daemon
      ...Object.fromEntries(
        ['/api', '/mcp', '/admin', '/tasks', '/sessions', '/memories', '/skills'].map(
          (path) => [path, { target: `http://localhost:${GOBBY_HTTP_PORT}`, changeOrigin: true }]
        )
      ),
      // Proxy WebSocket to Gobby WebSocket server
      '/ws': {
        target: `ws://localhost:${GOBBY_WS_PORT}`,
        ws: true,
        rewriteWsOrigin: true,
        rewrite: (path) => path.replace(/^\/ws/, ''),
      },
    },
  },
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
