import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In Docker l'API si raggiunge come http://api:8000, in locale su http://localhost:8001
const apiTarget = process.env.VITE_API_PROXY || 'http://localhost:8001'
const usePolling = process.env.CHOKIDAR_USEPOLLING === 'true' // serve su Windows + Docker

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
      // documentazione interattiva dell'API (Swagger)
      '/docs': { target: apiTarget, changeOrigin: true },
      '/openapi.json': { target: apiTarget, changeOrigin: true },
    },
    watch: usePolling ? { usePolling: true, interval: 300 } : undefined,
  },
})
