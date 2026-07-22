import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig(({ mode }) => ({
  plugins: [react()],
  // 生产构建输出到 Streamlit static 目录，供 Community Cloud 托管
  base: mode === 'production' ? '/app/static/' : '/',
  build: {
    outDir: mode === 'production' ? '../static' : 'dist',
    emptyOutDir: true,
  },
  server: {
    port: 5173,
  },
}))
