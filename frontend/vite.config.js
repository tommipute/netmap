import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In Docker l'API si raggiunge come http://api:8000, in locale su http://localhost:8001
const apiTarget = process.env.VITE_API_PROXY || 'http://localhost:8001'
const usePolling = process.env.CHOKIDAR_USEPOLLING === 'true' // serve su Windows + Docker
// Vite rifiuta i nomi host sconosciuti (gli IP vanno sempre bene): es. '.azienda.local' (VITE_ALLOWED_HOSTS)
const allowedHosts = (process.env.VITE_ALLOWED_HOSTS || '').split(',').map((h) => h.trim()).filter(Boolean)

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    strictPort: true,
    allowedHosts,
    proxy: {
      '/api': { target: apiTarget, changeOrigin: true },
      // documentazione interattiva dell'API (Swagger)
      '/docs': { target: apiTarget, changeOrigin: true },
      '/openapi.json': { target: apiTarget, changeOrigin: true },
    },
    watch: usePolling ? { usePolling: true, interval: 300 } : undefined,
  },
})
