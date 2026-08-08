import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// In development Vite serves the SPA and proxies the API to the FastAPI
// process. In production `npm run build` writes web/dist, which the API
// process serves itself -- one port, one thing to run on the homelab.
export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    proxy: {
      '/api': {
        target: process.env.CONCORDANCE_API || 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: { outDir: 'dist', emptyOutDir: true },
})
