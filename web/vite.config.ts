import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// GitHub Pages: https://onegee.github.io/indicator-dashboard/
const pagesBase = '/indicator-dashboard/'

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  base: mode === 'production' ? pagesBase : '/',
  build: {
    outDir: mode === 'production' ? '../static' : 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
  },
}))
