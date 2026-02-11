import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  resolve: {
    dedupe: ['@codemirror/state', '@codemirror/view', '@codemirror/language'],
  },
  server: {
    port: 5173,
    allowedHosts: ['localhost', '.ts.net', ...(process.env.VITE_ALLOWED_HOST ? [process.env.VITE_ALLOWED_HOST] : [])],
    proxy: {
      // Proxy API requests to Gobby daemon
      ...Object.fromEntries(
        ['/api', '/mcp', '/admin', '/tasks', '/sessions', '/artifacts', '/memories'].map(
          (path) => [path, { target: 'http://localhost:60887', changeOrigin: true }]
        )
      ),
      // Proxy WebSocket to Gobby WebSocket server
      '/ws': {
        target: 'ws://localhost:60888',
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
