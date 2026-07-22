import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// GitHub Pages: https://onegee.github.io/indicator-dashboard/
// 本地预览 / Streamlit 跳转均指向 Pages；Streamlit 本身不适合托管 SPA 的 JS/HTML。
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
