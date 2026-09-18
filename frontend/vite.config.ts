import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Port 5174, not Vite's default 5173: reorder-app's own frontend (chapter
// 8) already claims that port, and this book's own Auth0 tenant has
// pkgintel-app's SPA callback URLs registered against 5174 specifically,
// both products' frontends can run side by side against the same tenant.
export default defineConfig({
  plugins: [react()],
  server: { port: 5174 },
})
