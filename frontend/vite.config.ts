import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  return {
    plugins: [react()],
    resolve: {
      alias: { '@': path.resolve(__dirname, 'src') },
    },
    server: {
      host: '0.0.0.0',
      port: parseInt(env.VITE_PORT || '5173', 10),
      proxy: {
        '/tickora': {
          target: env.VITE_API_PROXY_TARGET || 'http://localhost:5100',
          changeOrigin: true,
        },
      },
    },
  }
})
