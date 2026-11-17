import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

const api = `http://127.0.0.1:${process.env.RACEFINDER_API_PORT || 8000}`

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    // subidas de carpetas grandes: sin límite de tiempo en el proxy
    proxy: {
      '/api': {
        target: api,
        changeOrigin: true, // FastAPI espera el host local aunque el navegador entre por la IP de red.
        timeout: 0, // subidas grandes: sin límite mientras la API responda
        configure: (proxy) => {
          proxy.on('error', (_err, _req, res) => {
            // API reiniciándose o caída: 503 inmediato (la interfaz reintenta sola) en vez de dejar la conexión colgada
            if (res && 'writeHead' in res && !res.headersSent) {
              res.writeHead(503, { 'Content-Type': 'application/json', 'Retry-After': '2' })
              res.end(JSON.stringify({ detail: 'RaceFinder se está reiniciando. Reintentando…' }))
            } else res?.destroy?.()
          })
        },
      },
    },
  },
})
