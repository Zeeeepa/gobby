import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    allowedHosts: ['localhost', '.ts.net', '100.97.1.54'],
    proxy: {
      // Proxy API requests to Gobby daemon
      '/api': {
        target: 'http://localhost:60887',
        changeOrigin: true,
      },
      '/mcp': {
        target: 'http://localhost:60887',
        changeOrigin: true,
      },
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
