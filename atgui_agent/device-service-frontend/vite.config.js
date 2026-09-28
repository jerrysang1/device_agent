import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

// 代理目标可用环境变量覆盖，默认本机开发地址（不再写死内网 IP）
// 用法：在 device-service-frontend 目录放 .env.local 写 VITE_DEVICE_API_BASE=http://...
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const deviceApiBase = env.VITE_DEVICE_API_BASE || 'http://127.0.0.1:18082'
  const agentApiBase = env.VITE_AGENT_API_BASE || 'http://127.0.0.1:8100'

  return {
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      // Agent 网关：POST /api/chat、GET /api/chat/history
      '/api': {
        target: agentApiBase,
        changeOrigin: true,
      },
      // 设备维修中台：/device/* → 中台根路径
      '/device': {
        target: deviceApiBase,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/device/, ''),
      },
    },
  },
  }
})
